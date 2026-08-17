"""요약: Gemini 로 한국어 요약. 실패/비활성 시 원문 스니펫으로 대체."""
from __future__ import annotations

import logging

from ..models import Article
from ..util import strip_html

log = logging.getLogger(__name__)


def _fallback(a: Article) -> str:
    text = (a.summary_src or "").strip()
    if text:
        return strip_html(text, 200)
    return a.title


def summarize(articles: list[Article], llm) -> list[Article]:
    result = llm.summarize(articles) if llm else None
    for i, a in enumerate(articles):
        summary = None
        if result is not None:
            summary = result.get(str(i))
        a.summary = (summary or "").strip() or _fallback(a)
    return articles
