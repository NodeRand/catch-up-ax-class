"""공통 유틸: 시간대 변환, HTML 제거 등."""
from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def now_kst() -> datetime:
    return datetime.now(KST)


def struct_to_kst(st) -> datetime | None:
    """feedparser 의 *_parsed (UTC struct_time) 를 KST aware datetime 으로."""
    if not st:
        return None
    return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc).astimezone(KST)


def epoch_to_kst(seconds: float) -> datetime:
    return datetime.fromtimestamp(seconds, tz=timezone.utc).astimezone(KST)


def strip_html(text: str, limit: int = 400) -> str:
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text[:limit]
