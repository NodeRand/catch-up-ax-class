"""SQLite 기반 발송 이력. 이미 보낸 기사를 다음 날 다시 보내지 않도록 한다."""
from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import timedelta

from ..config import ROOT
from ..models import Article
from ..util import now_kst

log = logging.getLogger(__name__)

DB_PATH = ROOT / "data" / "archive.db"


def _url_hash(url: str) -> str:
    return hashlib.sha1(url.strip().encode("utf-8")).hexdigest()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sent_articles (
            url_hash TEXT PRIMARY KEY,
            url      TEXT,
            title    TEXT,
            category TEXT,
            sent_at  TEXT
        )
        """
    )
    return conn


def filter_unseen(articles: list[Article]) -> list[Article]:
    """이미 발송한 URL 을 제외한 기사만 반환."""
    if not articles:
        return []
    conn = _connect()
    try:
        seen = {
            row[0]
            for row in conn.execute("SELECT url_hash FROM sent_articles")
        }
    finally:
        conn.close()

    fresh = [a for a in articles if _url_hash(a.url) not in seen]
    dropped = len(articles) - len(fresh)
    if dropped:
        log.info("발송 이력 중복 제외: %d건", dropped)
    return fresh


def mark_sent(articles: list[Article]) -> None:
    if not articles:
        return
    ts = now_kst().isoformat()
    rows = [
        (_url_hash(a.url), a.url, a.title, a.category, ts) for a in articles
    ]
    conn = _connect()
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO sent_articles "
            "(url_hash, url, title, category, sent_at) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    log.info("발송 이력 기록: %d건", len(rows))


def prune(days: int = 14) -> None:
    """오래된 이력 정리(기본 14일)."""
    cutoff = (now_kst() - timedelta(days=days)).isoformat()
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM sent_articles WHERE sent_at < ?", (cutoff,))
        conn.commit()
        if cur.rowcount:
            log.info("발송 이력 정리: %d건 삭제(%d일 경과)", cur.rowcount, days)
    finally:
        conn.close()
