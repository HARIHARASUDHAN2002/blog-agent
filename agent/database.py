"""
database.py — Lightweight JSON-based article tracker.

Uses a plain JSON file (database/published_topics.json) instead of SQLite
so it can be committed back to the GitHub repo after each run, giving the
agent persistent memory across cloud runs.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DB_FILE = os.getenv("DB_FILE", "database/published_topics.json")


def _load() -> dict:
    """Load the database from disk, returning empty structure if missing."""
    path = Path(DB_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return {"articles": [], "stats": {"total": 0, "last_run": None}}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("DB load error: %s — starting fresh", e)
        return {"articles": [], "stats": {"total": 0, "last_run": None}}


def _save(data: dict) -> None:
    """Persist the database to disk."""
    path = Path(DB_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_published(title: str) -> bool:
    """
    Check if a topic with a similar title has already been published.
    Uses fuzzy matching — if 70%+ of words overlap, treat it as duplicate.
    """
    data = _load()
    title_words = set(title.lower().split())
    for article in data["articles"]:
        existing_words = set(article["title"].lower().split())
        if not title_words or not existing_words:
            continue
        overlap = len(title_words & existing_words) / max(len(title_words), len(existing_words))
        if overlap >= 0.70:
            return True
    return False


def add_article(title: str, url: str, niche: str, keywords: list[str]) -> None:
    """Record a published article in the database."""
    data = _load()
    data["articles"].append({
        "title": title,
        "url": url,
        "niche": niche,
        "keywords": keywords,
        "published_at": datetime.now(timezone.utc).isoformat(),
    })
    data["stats"]["total"] = len(data["articles"])
    data["stats"]["last_run"] = datetime.now(timezone.utc).isoformat()
    _save(data)
    logger.info("DB: recorded article #%d — %s", data["stats"]["total"], title[:60])


def get_recent_titles(n: int = 30) -> list[str]:
    """Return the N most recently published article titles (to avoid repetition)."""
    data = _load()
    articles = data.get("articles", [])
    return [a["title"] for a in articles[-n:]]


def get_recent_keywords(n: int = 50) -> list[str]:
    """Return recently used keywords (to encourage topic variety)."""
    data = _load()
    keywords = []
    for article in data.get("articles", [])[-n:]:
        keywords.extend(article.get("keywords", []))
    return list(set(keywords))


def get_stats() -> dict:
    """Return summary stats for logging."""
    data = _load()
    return data.get("stats", {})
