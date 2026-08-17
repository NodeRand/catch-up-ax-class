"""RSS 수집기: 언론사/GeekNews 직접 RSS + 구글뉴스 키워드 RSS."""
from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime

import feedparser

from ..models import Article
from ..util import strip_html, struct_to_kst

log = logging.getLogger(__name__)


def _entry_time(entry) -> datetime | None:
    return struct_to_kst(
        getattr(entry, "published_parsed", None)
        or getattr(entry, "updated_parsed", None)
    )


def _parse_feed(url: str, source: str, start, end, undated: bool = False) -> list[Article]:
    out: list[Article] = []
    feed = feedparser.parse(url, agent="Mozilla/5.0 (news-brief)")
    if getattr(feed, "bozo", 0) and not feed.entries:
        log.warning("RSS 파싱 경고 [%s]: %s", source, getattr(feed, "bozo_exception", ""))
    for e in feed.entries:
        pub = _entry_time(e)
        if pub is None:
            # 날짜 없는 피드(예: 한겨레): 최신글 목록으로 보고 수집 시각을 부여
            if not undated:
                continue
            pub = end
        elif not (start <= pub <= end):
            continue
        title = (e.get("title") or "").strip()
        link = e.get("link") or ""
        if not title or not link:
            continue
        out.append(
            Article(
                title=title,
                url=link,
                source=source,
                published_at=pub,
                summary_src=strip_html(e.get("summary", "")),
            )
        )
    return out


def collect_rss(sources: list[dict], start, end) -> list[Article]:
    articles: list[Article] = []
    for src in sources:
        if not src.get("enabled", True):
            continue
        try:
            got = _parse_feed(
                src["url"], src["name"], start, end, undated=src.get("undated", False)
            )
            log.info("RSS [%s] %d건", src["name"], len(got))
            articles.extend(got)
        except Exception as e:
            log.warning("RSS 실패 [%s]: %s", src.get("name"), e)
    return articles


def collect_google_news(queries: list[dict], start, end) -> list[Article]:
    """구글뉴스 키워드 RSS. 항목의 candidate 카테고리를 query 의 code 로 미리 채운다."""
    articles: list[Article] = []
    for q in queries:
        query = urllib.parse.quote(f'{q["query"]} when:1d')
        url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
        try:
            got = _parse_feed(url, "구글뉴스", start, end)
            for a in got:
                a.candidates = [q["code"]]
            log.info("구글뉴스 [%s] %d건", q["code"], len(got))
            articles.extend(got)
        except Exception as e:
            log.warning("구글뉴스 실패 [%s]: %s", q.get("code"), e)
    return articles
