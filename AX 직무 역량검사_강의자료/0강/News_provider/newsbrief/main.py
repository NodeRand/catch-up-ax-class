"""일일 뉴스 브리핑 오케스트레이션.

사용법:
  python -m newsbrief.main              # 수집→분류→요약→메일 발송
  python -m newsbrief.main --dry-run    # 발송 대신 out/briefing.html 로 저장
  python -m newsbrief.main --no-llm     # LLM 미사용(키워드 규칙만)
"""
from __future__ import annotations

import argparse
import logging
from datetime import timedelta
from pathlib import Path

from .collectors.hackernews_collector import collect_hackernews
from .collectors.reddit_collector import collect_reddit
from .collectors.rss_collector import collect_google_news, collect_rss
from .config import ROOT, load_config
from .delivery.mailer import send_email
from .llm import LLM
from .pipeline.classify import classify
from .pipeline.dedup import dedup
from .pipeline.summarize import summarize
from .render.email_html import render_email
from .store import archive
from .util import now_kst


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def collect_all(cfg: dict, start, end):
    articles = []
    articles += collect_rss(cfg["sources"].get("rss", []), start, end)
    articles += collect_google_news(cfg["sources"].get("google_news", []), start, end)
    articles += collect_hackernews(cfg["settings"].get("hackernews", {}), start, end)
    articles += collect_reddit(cfg["settings"].get("reddit", {}), cfg["env"], start, end)
    return articles


def dedup_by_url(articles):
    seen = set()
    out = []
    for a in articles:
        if a.url in seen or not a.title:
            continue
        seen.add(a.url)
        out.append(a)
    return out


def run(dry_run: bool = False, use_llm: bool | None = None) -> int:
    cfg = load_config()
    settings = cfg["settings"]
    categories = cfg["categories"]["categories"]

    window_hours = settings.get("window_hours", 24)
    end = now_kst()
    start = end - timedelta(hours=window_hours)
    logging.info("수집 구간: %s ~ %s", start.strftime("%m-%d %H:%M"), end.strftime("%m-%d %H:%M"))

    # 1) 수집
    articles = dedup_by_url(collect_all(cfg, start, end))
    logging.info("수집 합계(URL 중복 제거 후): %d건", len(articles))
    if not articles:
        logging.warning("수집된 기사가 없습니다. 종료.")
        return 0

    # LLM 준비
    llm_cfg = settings.get("llm", {})
    enabled = llm_cfg.get("enabled", True) if use_llm is None else use_llm
    llm = LLM(cfg["env"]["gemini_api_key"], llm_cfg.get("model", "gemini-2.0-flash"), enabled)
    logging.info("LLM 사용: %s", llm.enabled)

    # 2) 분류 → 3) 중복제거 → 4) 요약
    articles = classify(articles, categories, llm, settings.get("scoring", {}))
    if not articles:
        logging.warning("관심 카테고리에 해당하는 기사가 없습니다.")
    articles = dedup(articles, settings.get("dedup", {}).get("title_similarity", 85), llm)

    # 이전에 발송한 기사 제외 (며칠에 걸쳐 반복 노출되는 사건 방지)
    archive.prune(days=14)
    articles = archive.filter_unseen(articles)

    # 카테고리별 상위만 요약 (LLM 호출 절감)
    max_per_cat = settings.get("max_items_per_category", 5)
    max_comm = settings.get("max_community_per_category", 2)
    to_summarize = _top_per_category(articles, categories, max_per_cat, max_comm)
    summarize(to_summarize, llm)

    # 5) 렌더
    html = render_email(to_summarize, categories, window_hours, max_per_cat)

    # 6) 발송 또는 저장
    if dry_run:
        out = ROOT / "out"
        out.mkdir(exist_ok=True)
        path = out / "briefing.html"
        path.write_text(html, encoding="utf-8")
        logging.info("[dry-run] 저장: %s (총 %d건)", path, len(to_summarize))
    else:
        env = cfg["env"]
        subject = f'{settings["email"]["subject_prefix"]} {end:%Y.%m.%d}'
        send_email(
            user=env["email_user"],
            app_password=env["email_app_password"],
            recipients=env["email_to"],
            subject=subject,
            html=html,
            sender_name=settings["email"].get("sender_name", "News Brief Bot"),
        )
        # 발송 성공한 기사만 이력에 기록
        archive.mark_sent(to_summarize)
    return 0


def _top_per_category(articles, categories, max_per_cat, max_community):
    """카테고리별 상위 선정. 커뮤니티(HN 등) 노출 수를 제한해 소스 다양성을 확보."""
    out = []
    for c in categories:
        items = sorted(
            (a for a in articles if a.category == c["code"]),
            key=lambda a: (-a.rank_score, -a.social_score),
        )
        chosen, comm = [], 0
        for a in items:
            if a.is_community:
                if comm >= max_community:
                    continue
                comm += 1
            chosen.append(a)
            if len(chosen) >= max_per_cat:
                break
        out.extend(chosen)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="일일 뉴스 브리핑")
    parser.add_argument("--dry-run", action="store_true", help="발송 대신 out/briefing.html 저장")
    parser.add_argument("--no-llm", action="store_true", help="LLM 미사용(키워드 규칙만)")
    args = parser.parse_args()

    setup_logging()
    use_llm = False if args.no_llm else None
    try:
        return run(dry_run=args.dry_run, use_llm=use_llm)
    except Exception:
        logging.exception("실행 실패")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
