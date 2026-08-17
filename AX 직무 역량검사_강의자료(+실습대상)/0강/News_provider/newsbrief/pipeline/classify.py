"""분류: 1차 키워드 필터 → (가능하면) Gemini 2차 분류 + 중요도 산정."""
from __future__ import annotations

import logging

from ..models import Article
from ..util import now_kst

log = logging.getLogger(__name__)

VALID = {"ADMISSION", "AI", "JOB", "IT", "INTL", "ECON"}


def keyword_candidates(article: Article, categories: list[dict]) -> list[str]:
    text = f"{article.title} {article.summary_src}".lower()
    matched: list[str] = []
    for c in categories:
        for kw in c["keywords"]:
            if kw.lower() in text:
                matched.append(c["code"])
                break
    return matched


def _social_bucket(score: int) -> int:
    """커뮤니티 점수 → 1~5 중요도 보정값."""
    if score >= 1000:
        return 5
    if score >= 500:
        return 4
    if score >= 200:
        return 3
    if score >= 100:
        return 2
    return 1


def _rank_score(a: Article, base: int, scoring: dict, now) -> float:
    """정렬 전용 점수. LLM 편집 점수(base) 위에 소스/신선도 가산, 추천수,
    지역·홍보성 감점을 적용한다. 화면의 별점에는 쓰지 않는다."""
    score = float(base)

    # C-1. 주요 소스 가산
    if a.source in set(scoring.get("major_sources", [])):
        score += scoring.get("major_source_bonus", 0)

    # C-2. 신선도 가산
    hrs = scoring.get("freshness_hours", 0)
    if hrs and (now - a.published_at).total_seconds() <= hrs * 3600:
        score += scoring.get("freshness_bonus", 0)

    # 커뮤니티 인기 점수 반영(더 높은 쪽)
    if a.is_community:
        score = max(score, _social_bucket(a.social_score))

    # D. 지역·홍보성 감점 (제목 기준)
    penalty = scoring.get("penalty", 0)
    markers = scoring.get("penalty_keywords", []) + scoring.get("region_keywords", [])
    if penalty and any(kw in a.title for kw in markers):
        score -= penalty

    return score


def classify(
    articles: list[Article], categories: list[dict], llm, scoring: dict | None = None
) -> list[Article]:
    scoring = scoring or {}
    now = now_kst()

    # 1차: 키워드 후보
    for a in articles:
        if not a.candidates:
            a.candidates = keyword_candidates(a, categories)

    result = llm.classify(articles, categories) if llm else None

    kept: list[Article] = []
    for i, a in enumerate(articles):
        if result is not None:
            r = result.get(str(i), {})
            cat = r.get("category", "NONE")
            base = int(r.get("importance", 1) or 1)
        else:
            # 규칙 기반 대체: 첫 후보 카테고리 사용
            cat = a.candidates[0] if a.candidates else "NONE"
            base = 3 if a.candidates else 1

        if cat not in VALID:
            continue

        a.category = cat
        a.importance = max(1, min(5, base))          # 화면 별점 = LLM 편집 점수
        a.rank_score = _rank_score(a, base, scoring, now)  # 정렬 전용
        a.relevant = True
        kept.append(a)

    log.info("분류 결과: 입력 %d → 관심 카테고리 %d건", len(articles), len(kept))
    return kept
