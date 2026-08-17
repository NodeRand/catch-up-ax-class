"""설정 로딩: config/*.yaml + .env"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


def load_config() -> dict:
    load_dotenv(ROOT / ".env")

    cfg: dict = {}
    for name in ("settings", "sources", "categories"):
        path = CONFIG_DIR / f"{name}.yaml"
        with open(path, encoding="utf-8") as f:
            cfg[name] = yaml.safe_load(f)

    cfg["env"] = {
        "gemini_api_key": os.getenv("GEMINI_API_KEY", "").strip(),
        "email_user": os.getenv("EMAIL_USER", "").strip(),
        "email_app_password": os.getenv("EMAIL_APP_PASSWORD", "").strip(),
        "email_to": [
            x.strip() for x in os.getenv("EMAIL_TO", "").split(",") if x.strip()
        ],
        "reddit_client_id": os.getenv("REDDIT_CLIENT_ID", "").strip(),
        "reddit_client_secret": os.getenv("REDDIT_CLIENT_SECRET", "").strip(),
    }
    return cfg
