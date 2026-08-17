"""Reddit 수집기.

- REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET 가 있으면 공식 OAuth API 로 점수(upvote)
  포함 데이터를 가져온다(트렌드 정밀 랭킹).
- 없으면 RSS 피드로 폴백(점수 없음).
"""
from __future__ import annotations

import logging
import time

import feedparser
import requests

from ..models import Article
from ..util import epoch_to_kst, strip_html, struct_to_kst

log = logging.getLogger(__name__)

_UA = "python:news-brief:1.0 (daily trend digest)"
_AI_SUBS = {"MachineLearning", "artificial", "OpenAI", "LocalLLaMA"}
_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_OAUTH_BASE = "https://oauth.reddit.com"


def _candidates(sub: str) -> list[str]:
    return ["AI"] if sub in _AI_SUBS else ["IT"]


# --- OAuth 경로 ----------------------------------------------------------
def _get_token(client_id: str, client_secret: str) -> str | None:
    try:
        r = requests.post(
            _TOKEN_URL,
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": _UA},
            timeout=20,
        )
        r.raise_for_status()
        return r.json().get("access_token")
    except Exception as e:
        log.warning("Reddit OAuth 토큰 발급 실패, RSS 로 폴백: %s", e)
        return None


def _collect_oauth(cfg, env, start, end) -> list[Article]:
    token = _get_token(env["reddit_client_id"], env["reddit_client_secret"])
    if not token:
        return _collect_rss(cfg, start, end)

    headers = {"User-Agent": _UA, "Authorization": f"bearer {token}"}
    period = cfg.get("time", "day")
    limit = cfg.get("limit", 25)
    min_score = cfg.get("min_score", 100)
    out: list[Article] = []

    for sub in cfg.get("subreddits", []):
        try:
            r = requests.get(
                f"{_OAUTH_BASE}/r/{sub}/top",
                params={"t": period, "limit": limit},
                headers=headers,
                timeout=20,
            )
            r.raise_for_status()
            children = r.json()["data"]["children"]
        except Exception as e:
            log.warning("Reddit API 실패 [r/%s]: %s", sub, e)
            time.sleep(1)
            continue

        count = 0
        for c in children:
            d = c["data"]
            pub = epoch_to_kst(d["created_utc"])
            if not (start <= pub <= end) or d.get("score", 0) < min_score:
                continue
            link = d.get("url_overridden_by_dest") or (
                "https://www.reddit.com" + d.get("permalink", "")
            )
            out.append(
                Article(
                    title=(d.get("title") or "").strip(),
                    url=link,
                    source=f"Reddit r/{sub}",
                    published_at=pub,
                    summary_src=(d.get("selftext") or "")[:300],
                    social_score=d.get("score", 0),
                    social_comments=d.get("num_comments", 0),
                    is_community=True,
                    candidates=_candidates(sub),
                )
            )
            count += 1
        log.info("Reddit(API) [r/%s] %d건", sub, count)
        time.sleep(0.5)
    return out


# --- RSS 폴백 경로 -------------------------------------------------------
def _collect_rss(cfg, start, end) -> list[Article]:
    out: list[Article] = []
    period = cfg.get("time", "day")
    for sub in cfg.get("subreddits", []):
        url = f"https://www.reddit.com/r/{sub}/top/.rss?t={period}"
        try:
            feed = feedparser.parse(url, agent="Mozilla/5.0 (news-brief)")
            if getattr(feed, "status", 200) >= 400 or (
                getattr(feed, "bozo", 0) and not feed.entries
            ):
                log.warning(
                    "Reddit RSS 실패 [r/%s]: status=%s",
                    sub,
                    getattr(feed, "status", "?"),
                )
                time.sleep(3)
                continue
        except Exception as e:
            log.warning("Reddit RSS 실패 [r/%s]: %s", sub, e)
            time.sleep(3)
            continue

        count = 0
        for e in feed.entries:
            pub = struct_to_kst(
                getattr(e, "published_parsed", None)
                or getattr(e, "updated_parsed", None)
            )
            if pub is None or not (start <= pub <= end):
                continue
            out.append(
                Article(
                    title=(e.get("title") or "").strip(),
                    url=e.get("link") or "",
                    source=f"Reddit r/{sub}",
                    published_at=pub,
                    summary_src=strip_html(e.get("summary", "")),
                    is_community=True,
                    candidates=_candidates(sub),
                )
            )
            count += 1
        log.info("Reddit(RSS) [r/%s] %d건", sub, count)
        time.sleep(3)
    return out


def collect_reddit(cfg: dict, env: dict, start, end) -> list[Article]:
    if not cfg.get("enabled", True):
        return []
    if env.get("reddit_client_id") and env.get("reddit_client_secret"):
        return _collect_oauth(cfg, env, start, end)
    log.info("Reddit 자격증명 없음 → RSS 폴백 사용")
    return _collect_rss(cfg, start, end)
