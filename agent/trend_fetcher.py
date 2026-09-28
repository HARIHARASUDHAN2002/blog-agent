"""
trend_fetcher.py — Collect worldwide trending topics from free sources.

Sources:
  1. Hacker News (Firebase API) — tech + AI + finance trends
  2. Google Trends RSS (US/GB/IN) — mainstream search trends
  3. Reddit RSS (personal finance, AI, side hustle subreddits)

Returns a scored list of trending topic strings, deduped and ranked.
"""

import logging
import re
import time
from typing import Optional

import feedparser
import requests

from config.settings import (
    HN_FETCH_COUNT, HN_ITEM_URL, HN_TOP_STORIES_URL,
    GOOGLE_TRENDS_RSS_URLS, REDDIT_RSS_FEEDS,
    REQUEST_HEADERS, REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


# ── Hacker News ────────────────────────────────────────────────────────────────

def _fetch_hn_trends() -> list[dict]:
    """
    Fetch top HN stories, filter for AI/finance/productivity relevance,
    return [{title, score, source}].
    """
    RELEVANT_KEYWORDS = {
        "ai", "gpt", "llm", "gemini", "claude", "openai", "machine learning",
        "automation", "money", "finance", "income", "invest", "startup",
        "productivity", "tool", "app", "free", "earn", "side", "hustle",
        "model", "agent", "chatbot", "revenue", "profit", "budget", "stock",
    }

    try:
        resp = requests.get(HN_TOP_STORIES_URL, timeout=REQUEST_TIMEOUT,
                            headers=REQUEST_HEADERS)
        resp.raise_for_status()
        story_ids = resp.json()[:HN_FETCH_COUNT]
    except Exception as e:
        logger.warning("HN top stories fetch failed: %s", e)
        return []

    results = []
    for sid in story_ids[:HN_FETCH_COUNT]:
        try:
            item_resp = requests.get(
                HN_ITEM_URL.format(sid),
                timeout=REQUEST_TIMEOUT,
                headers=REQUEST_HEADERS,
            )
            item_resp.raise_for_status()
            item = item_resp.json()
            title = item.get("title", "")
            score = item.get("score", 0)
            if not title:
                continue
            title_lower = title.lower()
            if any(kw in title_lower for kw in RELEVANT_KEYWORDS):
                results.append({
                    "title": title,
                    "score": score,
                    "source": "hackernews",
                })
            time.sleep(0.05)   # be polite
        except Exception:
            continue

    logger.info("HN: fetched %d relevant stories", len(results))
    return results


# ── Google Trends RSS ──────────────────────────────────────────────────────────

def _fetch_google_trends() -> list[dict]:
    """
    Parse Google Trends daily RSS for US, GB, IN.
    Returns [{title, score, source}] — score is the approximate traffic number.
    """
    results = []
    for url in GOOGLE_TRENDS_RSS_URLS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                title = entry.get("title", "").strip()
                if not title:
                    continue
                # Extract traffic number from ht:approx_traffic tag if present
                traffic_str = ""
                for tag in entry.get("tags", []):
                    if "traffic" in tag.get("term", "").lower():
                        traffic_str = tag.get("term", "")
                # Parse "1,000,000+" → 1000000
                traffic = int(re.sub(r"[^\d]", "", traffic_str) or "1000")
                results.append({
                    "title": title,
                    "score": min(traffic // 1000, 1000),  # normalise
                    "source": "google_trends",
                })
        except Exception as e:
            logger.warning("Google Trends RSS failed (%s): %s", url, e)

    logger.info("Google Trends: fetched %d topics", len(results))
    return results


# ── Reddit RSS ─────────────────────────────────────────────────────────────────

def _fetch_reddit_trends() -> list[dict]:
    """
    Fetch top posts from relevant subreddits via their public RSS feeds.
    Returns [{title, score, source}].
    """
    SPAM_PATTERNS = re.compile(
        r"\b(rant|meme|funny|off.?topic|vent|confession|embarrassing)\b",
        re.IGNORECASE,
    )
    results = []
    for url in REDDIT_RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                title = entry.get("title", "").strip()
                if not title or SPAM_PATTERNS.search(title):
                    continue
                results.append({
                    "title": title,
                    "score": 50,   # Reddit RSS doesn't expose upvotes
                    "source": "reddit",
                })
        except Exception as e:
            logger.warning("Reddit RSS failed (%s): %s", url, e)

    logger.info("Reddit: fetched %d topics", len(results))
    return results


# ── Main entry point ────────────────────────────────────────────────────────────

def fetch_all_trends() -> list[dict]:
    """
    Aggregate trends from all sources, deduplicate, and return sorted by score.

    Each item: {"title": str, "score": int, "source": str}
    """
    all_trends = []
    all_trends.extend(_fetch_hn_trends())
    all_trends.extend(_fetch_google_trends())
    all_trends.extend(_fetch_reddit_trends())

    # Deduplicate by title similarity (skip near-duplicates)
    seen: list[str] = []
    unique = []
    for item in all_trends:
        title_lower = item["title"].lower()
        words = set(title_lower.split())
        is_dup = any(
            len(words & set(s.split())) / max(len(words), len(set(s.split())), 1) > 0.65
            for s in seen
        )
        if not is_dup:
            seen.append(title_lower)
            unique.append(item)

    unique.sort(key=lambda x: x["score"], reverse=True)
    logger.info("Trends total (deduped): %d", len(unique))
    return unique
