"""Hacker News 수집기 (Algolia Search API, 단일 요청)."""
from __future__ import annotations

import logging

import requests

from ..models import Article
from ..util import epoch_to_kst

log = logging.getLogger(__name__)

API = "https://hn.algolia.com/api/v1/search"


def collect_hackernews(cfg: dict, start, end) -> list[Article]:
    if not cfg.get("enabled", True):
        return []

    ts = int(start.timestamp())
    min_points = cfg.get("min_points", 50)
    # numericFilters 는 created_at 만 사용하고 점수는 클라이언트에서 필터(조합 시 400 회피)
    params = {
        "tags": "story",
        "numericFilters": f"created_at_i>{ts}",
        "hitsPerPage": cfg.get("max_items", 50),
    }
    try:
        r = requests.get(API, params=params, timeout=20)
        r.raise_for_status()
        hits = r.json().get("hits", [])
    except Exception as e:
        log.warning("Hacker News 실패: %s", e)
        return []

    out: list[Article] = []
    for h in hits:
        if (h.get("points") or 0) < min_points:
            continue
        pub = epoch_to_kst(h["created_at_i"])
        if not (start <= pub <= end):
            continue
        url = h.get("url") or f'https://news.ycombinator.com/item?id={h["objectID"]}'
        out.append(
            Article(
                title=(h.get("title") or "").strip(),
                url=url,
                source="Hacker News",
                published_at=pub,
                summary_src=(h.get("story_text") or "")[:300],
                social_score=h.get("points", 0) or 0,
                social_comments=h.get("num_comments", 0) or 0,
                is_community=True,
                candidates=["AI", "IT"],
            )
        )
    log.info("Hacker News %d건", len(out))
    return out
