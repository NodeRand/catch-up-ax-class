"""대표 기사 목록 → 카테고리별 HTML 이메일 본문."""
from __future__ import annotations

from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import ROOT
from ..models import Article
from ..util import now_kst

_env = Environment(
    loader=FileSystemLoader(str(ROOT / "templates")),
    autoescape=select_autoescape(["html"]),
)

_WEEKDAY = ["월", "화", "수", "목", "금", "토", "일"]


def _date_label(dt: datetime) -> str:
    return f"{dt:%Y.%m.%d} ({_WEEKDAY[dt.weekday()]}) {dt:%H:%M}"


def render_email(
    articles: list[Article],
    categories: list[dict],
    window_hours: int,
    max_per_cat: int,
) -> str:
    by_cat: dict[str, list[Article]] = {c["code"]: [] for c in categories}
    for a in articles:
        if a.category in by_cat:
            by_cat[a.category].append(a)

    sections = []
    total = 0
    for c in categories:
        # 선정 단계(_top_per_category)에서 이미 순위·다양성 정렬됨 → 순서 보존
        items = by_cat[c["code"]][:max_per_cat]
        for a in items:
            a.time_label = f"{a.published_at:%m.%d %H:%M}"  # type: ignore[attr-defined]
        total += len(items)
        sections.append({"name": c["name"], "articles": items})

    now = now_kst()
    tmpl = _env.get_template("briefing.html.j2")
    return tmpl.render(
        date_label=_date_label(now),
        generated_label=f"{now:%Y.%m.%d %H:%M}",
        window_hours=window_hours,
        total=total,
        sections=sections,
    )
