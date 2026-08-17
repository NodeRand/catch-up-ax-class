"""중복 제거: 제목 유사도 1차 필터 + (가능하면) LLM 으로 표현이 다른 동일 사건 병합."""
from __future__ import annotations

import logging

from rapidfuzz import fuzz

from ..models import Article

log = logging.getLogger(__name__)


def _fuzzy_cluster(articles: list[Article], threshold: int) -> list[list[Article]]:
    # 점수 높은 순으로 처리해 대표가 가장 중요한 기사가 되도록
    ordered = sorted(articles, key=lambda a: (-a.rank_score, -a.social_score))
    clusters: list[list[Article]] = []

    for a in ordered:
        placed = False
        for cl in clusters:
            # 같은 카테고리 안에서만 비교
            if cl[0].category == a.category and fuzz.token_set_ratio(
                a.title, cl[0].title
            ) >= threshold:
                cl.append(a)
                placed = True
                break
        if not placed:
            clusters.append([a])
    return clusters


def _llm_merge(clusters: list[list[Article]], llm) -> list[list[Article]]:
    """제목 유사도로 못 묶은, 표현만 다른 동일 사건 클러스터를 LLM 으로 추가 병합.

    각 클러스터의 대표 기사(제목 유사도 기준 1등)만 LLM 에 넘겨 비용을 줄인다.
    """
    if llm is None or not getattr(llm, "enabled", False) or len(clusters) < 2:
        return clusters

    by_cat: dict[str, list[int]] = {}
    for idx, cl in enumerate(clusters):
        by_cat.setdefault(cl[0].category, []).append(idx)

    parent: dict[int, int] = {}  # 클러스터 idx -> 병합될 idx

    def _root(i: int) -> int:
        while i in parent:
            i = parent[i]
        return i

    for code, idxs in by_cat.items():
        if len(idxs) < 2:
            continue
        reps = [clusters[i][0] for i in idxs]
        try:
            groups = llm.dedup_groups(reps)
        except Exception as e:
            log.warning("LLM 중복판별 실패(카테고리=%s): %s", code, e)
            continue
        if not groups:
            continue
        first_of_group: dict[int, int] = {}
        for pos, idx in enumerate(idxs):
            g = groups.get(str(pos))
            if g is None:
                continue
            if g not in first_of_group:
                first_of_group[g] = idx
            else:
                parent[idx] = first_of_group[g]

    if not parent:
        return clusters

    buckets: dict[int, list[Article]] = {}
    for idx, cl in enumerate(clusters):
        buckets.setdefault(_root(idx), []).extend(cl)
    return list(buckets.values())


def dedup(articles: list[Article], threshold: int = 85, llm=None) -> list[Article]:
    clusters = _fuzzy_cluster(articles, threshold)
    clusters = _llm_merge(clusters, llm)

    reps: list[Article] = []
    for i, cl in enumerate(clusters):
        rep = max(cl, key=lambda a: (a.rank_score, a.social_score))
        rep.cluster_id = i
        reps.append(rep)

    log.info("중복제거: %d건 → 대표 %d건", len(articles), len(reps))
    return reps
