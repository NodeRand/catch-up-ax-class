"""수집부터 발송까지 파이프라인 전반에서 쓰는 표준 데이터 모델."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Article:
    title: str
    url: str
    source: str
    published_at: datetime
    summary_src: str = ""          # 원본 RSS 요약/스니펫
    category: Optional[str] = None # ADMISSION / AI / JOB / IT / None
    importance: int = 0            # 1~5 (최종 중요도)
    social_score: int = 0          # HN points / Reddit upvotes
    social_comments: int = 0
    is_community: bool = False      # HN/Reddit 등 커뮤니티 소스 여부
    cluster_id: Optional[int] = None
    summary: str = ""              # 최종 한국어 요약 (메일에 노출)
    relevant: bool = True
    rank_score: float = 0.0        # 정렬 전용 점수 (보너스/페널티/추천수 반영, 화면 미표시)

    # 후보 카테고리 (키워드 필터 결과) — 분류 단계 입력용
    candidates: list[str] = field(default_factory=list)
