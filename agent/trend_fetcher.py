"""
trend_fetcher.py — Multi-Horizon Worldwide Trend Intelligence Engine.

Aggregates trending stories across 3 time horizons:
  1. Last 24 Hours: Real-time breaking tech, business, and world news (HN Top, Google Daily Trends, BBC Breaking)
  2. Last Week: High-momentum weekly stories & guides (HN Best, BBC Science/World, The Verge)
  3. Last Month: Long-term breakout stories, discoveries & deep dives (HN Evergreen Best, Longform Analysis)

Universal Pillars:
  - Technology & Innovation
  - Business, Money & Economy
  - Science & Future Discoveries
  - Global Trends & Explainers
"""

import logging
import re
import time
from typing import Optional

import feedparser
import requests

from config.settings import (
    GLOBAL_HORIZON_FEEDS, GOOGLE_TRENDS_RSS_URLS, HN_BEST_STORIES_URL,
    HN_FETCH_COUNT, HN_ITEM_URL, HN_TOP_STORIES_URL, REQUEST_HEADERS,
    REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


# ── Hacker News Multi-Horizon (24h, Week, Month) ──────────────────────────────

def _fetch_hn_stories() -> list[dict]:
    """
    Fetch both topstories (24h) and beststories (week & month) from Hacker News.
    """
    results = []

    # 1. Real-time 24h Top Stories
    try:
        resp = requests.get(HN_TOP_STORIES_URL, timeout=REQUEST_TIMEOUT, headers=REQUEST_HEADERS)
        if resp.status_code == 200:
            story_ids = resp.json()[:HN_FETCH_COUNT]
            for sid in story_ids[:25]:
                try:
                    item_resp = requests.get(HN_ITEM_URL.format(sid), timeout=REQUEST_TIMEOUT, headers=REQUEST_HEADERS)
                    if item_resp.status_code == 200:
                        item = item_resp.json()
                        title = item.get("title", "")
                        score = item.get("score", 0)
                        if title and score >= 20:
                            results.append({
                                "title": title,
                                "score": score,
                                "source": "hackernews_24h",
                                "horizon": "24h",
                            })
                    time.sleep(0.02)
                except Exception:
                    continue
    except Exception as e:
        logger.warning("HN top stories fetch failed: %s", e)

    # 2. Curated Best Stories (Week & Month)
    try:
        resp = requests.get(HN_BEST_STORIES_URL, timeout=REQUEST_TIMEOUT, headers=REQUEST_HEADERS)
        if resp.status_code == 200:
            story_ids = resp.json()[:30]
            for sid in story_ids[:20]:
                try:
                    item_resp = requests.get(HN_ITEM_URL.format(sid), timeout=REQUEST_TIMEOUT, headers=REQUEST_HEADERS)
                    if item_resp.status_code == 200:
                        item = item_resp.json()
                        title = item.get("title", "")
                        score = item.get("score", 0)
                        if title:
                            horizon = "month" if score >= 450 else "week"
                            results.append({
                                "title": title,
                                "score": score,
                                "source": f"hackernews_{horizon}",
                                "horizon": horizon,
                            })
                    time.sleep(0.02)
                except Exception:
                    continue
    except Exception as e:
        logger.warning("HN best stories fetch failed: %s", e)

    logger.info("HN: fetched %d stories across horizons", len(results))
    return results


# ── Google Trends RSS (Last 24 Hours) ─────────────────────────────────────────

def _fetch_google_trends() -> list[dict]:
    """Parse Google Trends daily RSS for US, GB, IN."""
    results = []
    for url in GOOGLE_TRENDS_RSS_URLS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                title = entry.get("title", "").strip()
                if not title:
                    continue
                traffic_str = ""
                for tag in entry.get("tags", []):
                    if "traffic" in tag.get("term", "").lower():
                        traffic_str = tag.get("term", "")
                traffic = int(re.sub(r"[^\d]", "", traffic_str) or "1000")
                results.append({
                    "title": title,
                    "score": min(traffic // 1000, 1000),
                    "source": "google_trends",
                    "horizon": "24h",
                })
        except Exception as e:
            logger.warning("Google Trends RSS failed (%s): %s", url, e)

    logger.info("Google Trends: fetched %d topics (24h)", len(results))
    return results


# ── Global Multi-Horizon Feeds (BBC, Ars Technica, The Verge) ─────────────────

def _fetch_global_horizon_feeds() -> list[dict]:
    """Fetch stories from BBC, Ars Technica, and The Verge categorized by time horizon."""
    results = []

    for horizon, urls in GLOBAL_HORIZON_FEEDS.items():
        base_score = 65 if horizon == "24h" else (80 if horizon == "week" else 95)
        for url in urls:
            try:
                # Use requests with proper desktop headers
                r = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
                if r.status_code == 200:
                    feed = feedparser.parse(r.content)
                    for entry in feed.entries[:8]:
                        title = entry.get("title", "").strip()
                        if not title or len(title) < 15:
                            continue
                        results.append({
                            "title": title,
                            "score": base_score,
                            "source": f"feed_{horizon}",
                            "horizon": horizon,
                        })
            except Exception as e:
                logger.warning("Feed failed (%s): %s", url, e)

    logger.info("Global feeds: fetched %d stories across horizons", len(results))
    return results


# ── Main Entry Point ──────────────────────────────────────────────────────────

def fetch_all_trends() -> list[dict]:
    """
    Aggregate trends from all sources across 24h, week, and month horizons.
    Deduplicates and returns ranked candidates.
    """
    all_trends = []
    all_trends.extend(_fetch_hn_stories())
    all_trends.extend(_fetch_google_trends())
    all_trends.extend(_fetch_global_horizon_feeds())

    # Deduplicate by title similarity
    seen: list[str] = []
    unique = []
    for item in all_trends:
        title_lower = item["title"].lower()
        words = set(title_lower.split())
        is_dup = any(
            len(words & set(s.split())) / max(len(words), len(set(s.split())), 1) > 0.60
            for s in seen
        )
        if not is_dup:
            seen.append(title_lower)
            unique.append(item)

    unique.sort(key=lambda x: x["score"], reverse=True)
    logger.info(
        "Trends total (deduped): %d (24h: %d, week: %d, month: %d)",
        len(unique),
        sum(1 for x in unique if x.get("horizon") == "24h"),
        sum(1 for x in unique if x.get("horizon") == "week"),
        sum(1 for x in unique if x.get("horizon") == "month"),
    )
    return unique
