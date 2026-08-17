"""Gemini 기반 분류/요약. API 키가 없으면 비활성화되어 호출자가 규칙 기반으로 대체한다.

모델마다 JSON 출력 형태(객체 vs 배열, 코드펜스/여분 텍스트)가 달라서, 출력은
명시적 id 배열로 요청하고 파싱은 펜스/여분 데이터를 견디도록 한다.
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


def _extract_json(text: str):
    """코드펜스·앞뒤 잡텍스트·여분 데이터를 견디며 첫 JSON 값을 파싱."""
    if not text:
        raise ValueError("빈 응답")
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
        t = t.strip()
    # 첫 '{' 또는 '[' 부터 시작
    starts = [i for i in (t.find("{"), t.find("[")) if i != -1]
    if starts:
        t = t[min(starts):]
    obj, _ = json.JSONDecoder().raw_decode(t)  # 여분 데이터 무시
    return obj


def _as_rows(data) -> list[dict]:
    """응답을 [{id, ...}] 형태의 리스트로 정규화 (배열/객체 모두 허용)."""
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        # {"items":[...]} 또는 {"0":{...}} 형태
        if isinstance(data.get("items"), list):
            return [d for d in data["items"] if isinstance(d, dict)]
        rows = []
        for k, v in data.items():
            if isinstance(v, dict):
                rows.append({"id": k, **v})
        return rows
    return []


class LLM:
    def __init__(self, api_key: str, model: str, enabled: bool = True):
        self.model = model
        self.enabled = bool(api_key) and enabled
        self.client = None
        if self.enabled:
            try:
                from google import genai

                self.client = genai.Client(api_key=api_key)
            except Exception as e:  # SDK 미설치/초기화 실패
                log.warning("Gemini 초기화 실패, 규칙 기반으로 대체: %s", e)
                self.enabled = False

    def _generate_json(self, prompt: str) -> str:
        from google.genai import types

        resp = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        return resp.text

    # --- 분류 -------------------------------------------------------------
    def classify(self, articles, categories, batch_size: int = 50) -> dict | None:
        """index(str) -> {"category": code|"NONE", "importance": 1..5} 반환.

        기사 수가 많으면 응답 잘림을 막기 위해 batch_size 단위로 나눠 호출한다.
        전부 실패하면 None 을 반환해 호출자가 규칙 기반으로 대체하게 한다.
        """
        if not self.enabled or not articles:
            return None

        cat_desc = "\n".join(f'- {c["code"]}: {c["name"]}' for c in categories)
        merged: dict = {}
        ok = False
        for offset in range(0, len(articles), batch_size):
            chunk = articles[offset : offset + batch_size]
            lines = []
            for j, a in enumerate(chunk):
                snippet = (a.summary_src or "")[:150]
                lines.append(f"{j}\t[{a.source}] {a.title} :: {snippet}")
            prompt = (
                "너는 숙련된 뉴스 편집 데스크다. 아래 기사들을 카테고리로 분류하고 "
                "중요도(importance)를 보수적으로 매겨라.\n\n"
                "카테고리:\n"
                f"{cat_desc}\n"
                "- NONE: 위 주제와 무관\n\n"
                "중요도 기준 (보수적으로, 근거가 분명할 때만 높게):\n"
                "  5 = 전국/업계 전체 판도를 바꾸는 핵심 뉴스 "
                "(정부 정책 발표, 주요 기업의 신제품·실적·인수합병, 시장 1위 변동 등)\n"
                "  4 = 업계가 주목할 중요한 동향\n"
                "  3 = 일반적인 동향·소식 (기본값)\n"
                "  2 = 지역 한정·단신·홍보성\n"
                "  1 = 주제와 거의 무관하거나 광고성\n"
                "규칙: 전국적 파급력이 확실할 때만 4~5점을 주고, 애매하면 3점 이하로 내려라. "
                "이 목록 안에서 5점은 최대 2개까지만 허용한다.\n\n"
                "출력은 JSON 배열이며, 각 원소는 "
                '{"id": 기사번호(정수), "category": "코드", "importance": 1~5 정수} '
                "형식이다. 다른 텍스트 없이 JSON 만 출력하라.\n\n"
                "기사 목록:\n" + "\n".join(lines)
            )
            try:
                rows = _as_rows(_extract_json(self._generate_json(prompt)))
                for el in rows:
                    j = int(el.get("id"))
                    merged[str(offset + j)] = {
                        "category": el.get("category", "NONE"),
                        "importance": el.get("importance", 1),
                    }
                ok = True
            except Exception as e:
                log.warning("LLM 분류 배치 실패(offset=%d): %s", offset, e)

        return merged if ok else None

    # --- 중복 판별 ----------------------------------------------------------
    def dedup_groups(self, articles, batch_size: int = 40) -> dict | None:
        """index(str) -> group(int). 서로 다른 언론사가 같은 사건을 보도한 기사에
        동일 group 번호를 매긴다. 제목 유사도로 못 잡는, 표현만 다른 중복을 찾는 2차 필터.

        호출자는 같은 카테고리의 기사만 넘겨야 한다(카테고리 간 병합은 하지 않음).
        """
        if not self.enabled or not articles:
            return None

        merged: dict = {}
        ok = False
        next_group = 0
        for offset in range(0, len(articles), batch_size):
            chunk = articles[offset : offset + batch_size]
            lines = []
            for j, a in enumerate(chunk):
                snippet = (a.summary_src or "")[:150]
                lines.append(f"{j}\t[{a.source}] {a.title} :: {snippet}")
            prompt = (
                "너는 뉴스 편집자다. 아래 기사 목록에서 서로 다른 언론사가 "
                "동일한 실제 사건·발표를 보도한 것을 찾아 같은 group 번호로 묶어라. "
                "제목 표현이 크게 달라도 핵심 사실(누가/무엇을/언제)이 같으면 같은 사건으로 본다. "
                "핵심 사실이 다르면 표현이 비슷해 보여도 다른 group 번호를 준다. "
                "각 기사는 정확히 하나의 group 에 속하고, group 번호는 임의로 매겨도 된다.\n\n"
                "출력은 JSON 배열이며, 각 원소는 "
                '{"id": 기사번호(정수), "group": 그룹번호(정수)} 형식이다. '
                "다른 텍스트 없이 JSON 만 출력하라.\n\n"
                "기사 목록:\n" + "\n".join(lines)
            )
            try:
                rows = _as_rows(_extract_json(self._generate_json(prompt)))
                local: dict[int, int] = {}
                for el in rows:
                    j = int(el.get("id"))
                    g = el.get("group")
                    if g is None:
                        continue
                    local[j] = int(g)
                # 배치마다 그룹 번호가 겹치지 않도록 전역 번호로 재부여
                remap: dict[int, int] = {}
                for j, g in local.items():
                    if g not in remap:
                        remap[g] = next_group
                        next_group += 1
                    merged[str(offset + j)] = remap[g]
                ok = True
            except Exception as e:
                log.warning("LLM 중복판별 배치 실패(offset=%d): %s", offset, e)

        return merged if ok else None

    # --- 요약 -------------------------------------------------------------
    def summarize(self, articles) -> dict | None:
        """index(str) -> 한국어 요약문 반환."""
        if not self.enabled or not articles:
            return None

        lines = []
        for i, a in enumerate(articles):
            body = (a.summary_src or a.title)[:500]
            lines.append(f"{i}\t[{a.source}] {a.title} :: {body}")
        items = "\n".join(lines)

        prompt = (
            "다음 기사들을 각각 한국어 2~3문장으로 요약하라. "
            "영어 기사는 한국어로 번역해 요약한다. "
            "핵심 사실과 '왜 중요한지'가 드러나게 간결히 쓴다.\n"
            "출력은 JSON 배열이며, 각 원소는 "
            '{"id": 기사번호(정수), "summary": "요약문"} 형식이다. '
            "다른 텍스트 없이 JSON 만 출력하라.\n\n"
            f"기사 목록:\n{items}"
        )
        try:
            rows = _as_rows(_extract_json(self._generate_json(prompt)))
            out = {}
            for el in rows:
                out[str(int(el.get("id")))] = el.get("summary", "")
            return out or None
        except Exception as e:
            log.warning("LLM 요약 실패, 원문 스니펫으로 대체: %s", e)
            return None
