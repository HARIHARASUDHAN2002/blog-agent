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


STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
    "but", "by", "can", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does",
    "doesn't", "doing", "don't", "down", "during", "each", "few", "for", "from", "further", "had",
    "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "how's", "i", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "just", "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor",
    "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves",
    "out", "over", "own", "same", "shan't", "she", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there",
    "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", "through",
    "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're",
    "we've", "were", "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would", "wouldn't", "you",
    "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves",
    # Common generic blog boilerplate words
    "complete", "guide", "breakdown", "explained", "teardown", "secrets", "everything", "need",
    "know", "simple", "step", "steps", "ways", "best", "top", "real", "truth", "future", "daily",
    "look", "inside", "overview", "revealed", "what's", "why's", "how's", "edition", "review",
}

import re


def extract_content_tokens(text: str) -> set[str]:
    """Extract substantive, lower-cased keywords with stopwords and punctuation stripped."""
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    tokens = clean.split()
    return {t for t in tokens if len(t) >= 3 and t not in STOP_WORDS}


def is_duplicate_topic(candidate: str, existing_title: str) -> tuple[bool, float, str]:
    """
    Determine if candidate topic is too similar to an existing title.
    Returns: (is_duplicate: bool, similarity_score: float, reason: str)
    """
    cand_tokens = extract_content_tokens(candidate)
    exist_tokens = extract_content_tokens(existing_title)

    if not cand_tokens or not exist_tokens:
        return False, 0.0, "empty_tokens"

    # Shared substantive tokens
    shared = cand_tokens & exist_tokens
    min_len = min(len(cand_tokens), len(exist_tokens))
    overlap = len(shared) / max(min_len, 1)

    # Substring check of cleaned phrases
    cand_clean = " " + re.sub(r"[^a-zA-Z0-9\s]", " ", candidate.lower()) + " "
    exist_clean = " " + re.sub(r"[^a-zA-Z0-9\s]", " ", existing_title.lower()) + " "

    # 1. Direct overlap of 45%+ of content words
    if overlap >= 0.45 and len(shared) >= 2:
        return True, overlap, f"shared_keywords: {list(shared)}"

    # 2. Key phrases in common (e.g. 'owed billion stock' or 'nvidia stock')
    if len(shared) >= 3:
        return True, overlap, f"high_token_match: {list(shared)}"

    # 3. Direct substring containment of 3+ words
    for i in range(len(cand_tokens) - 2):
        chunk = list(cand_tokens)[i:i+3]
        if all(w in exist_tokens for w in chunk):
            return True, 0.8, f"phrase_overlap: {chunk}"

    return False, overlap, "distinct"


def find_duplicate_in_published(candidate: str, published_titles: list[str]) -> tuple[bool, str, float]:
    """
    Scan all published titles to verify candidate hasn't already been covered.
    Returns (is_duplicate, matched_title, score).
    """
    for title in published_titles:
        is_dup, score, reason = is_duplicate_topic(candidate, title)
        if is_dup:
            return True, title, score
    return False, "", 0.0


def is_published(title: str) -> bool:
    """Check if a topic has already been published in local DB."""
    titles = get_all_published_titles()
    is_dup, _, _ = find_duplicate_in_published(title, titles)
    return is_dup


def get_all_published_titles() -> list[str]:
    """Return all published article titles from the database."""
    data = _load()
    articles = data.get("articles", [])
    return [a["title"].strip() for a in articles if a.get("title")]



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


def get_all_articles() -> list[dict]:
    """Return all recorded article objects with metadata and niches."""
    data = _load()
    return data.get("articles", [])

