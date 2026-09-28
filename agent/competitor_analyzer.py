"""
competitor_analyzer.py — Monitor competitor blogs via RSS to learn what's
working and find content gaps.

For each competitor, we:
  1. Fetch their recent RSS entries
  2. Extract title patterns, topic keywords, format signals (list/how-to/review)
  3. Build a "this week's coverage" map to identify gaps our blog can fill
  4. Extract writing patterns (avg title length, popular formats) that perform well

This data feeds into topic_selector.py and article_generator.py so the agent
continuously improves its content strategy based on what top blogs are doing.
"""

import json
import logging
import re
from collections import Counter
from pathlib import Path

import feedparser

from config.settings import REQUEST_HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

COMPETITORS_FILE = "config/competitors.json"


def _load_competitors() -> list[dict]:
    try:
        with open(COMPETITORS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("competitors", [])
    except Exception as e:
        logger.error("Failed to load competitors config: %s", e)
        return []


def _detect_format(title: str) -> str:
    """Detect the article format from the title."""
    title_lower = title.lower()
    if re.search(r"\b(\d+)\s+(best|top|ways|tips|tools|ideas|tricks|steps)\b", title_lower):
        return "listicle"
    if title_lower.startswith("how to") or title_lower.startswith("how i"):
        return "how_to"
    if any(w in title_lower for w in ["review", "vs", "versus", "compared", "comparison"]):
        return "review"
    if any(w in title_lower for w in ["what is", "what are", "guide to", "beginners"]):
        return "educational"
    if any(w in title_lower for w in ["2024", "2025", "2026", "this year", "latest"]):
        return "roundup"
    return "general"


def _extract_keywords(title: str) -> list[str]:
    """Extract meaningful content keywords from a title."""
    STOP_WORDS = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "be", "this", "that",
        "it", "its", "you", "your", "we", "our", "my", "i", "how", "what",
        "why", "when", "where", "which", "who", "not", "no", "can", "will",
        "do", "does", "did", "have", "has", "had", "would", "could", "should",
    }
    words = re.findall(r"[a-zA-Z]{3,}", title.lower())
    return [w for w in words if w not in STOP_WORDS]


def analyze_competitors() -> dict:
    """
    Analyze all competitor feeds and return a structured insight dict:

    {
        "recent_titles":    [str, ...]         # all titles published this week
        "covered_keywords": Counter({kw: n})   # most covered keywords
        "format_counts":    Counter({fmt: n})  # format popularity
        "patterns": {
            "avg_title_words": float,
            "top_formats":     [str, ...]
            "hot_keywords":    [str, ...]
        }
        "by_niche": {
            "ai_tools":        [titles...],
            "personal_finance": [titles...]
        }
    }
    """
    competitors = _load_competitors()
    recent_titles: list[str] = []
    all_keywords: list[str] = []
    format_counts: Counter = Counter()
    by_niche: dict = {"ai_tools": [], "personal_finance": [], "ai_finance_overlap": []}

    for comp in competitors:
        name = comp.get("name", "unknown")
        rss_url = comp.get("rss", "")
        niche = comp.get("niche", "general")

        if not rss_url:
            continue

        try:
            feed = feedparser.parse(
                rss_url,
                request_headers=REQUEST_HEADERS,
            )
            entries = feed.entries[:15]   # last ~15 articles per blog
            for entry in entries:
                title = entry.get("title", "").strip()
                if not title or len(title) < 10:
                    continue
                recent_titles.append(title)
                all_keywords.extend(_extract_keywords(title))
                fmt = _detect_format(title)
                format_counts[fmt] += 1
                if niche in by_niche:
                    by_niche[niche].append(title)
            logger.info("Competitor [%s]: %d entries read", name, len(entries))
        except Exception as e:
            logger.warning("Competitor RSS failed [%s]: %s", name, e)

    covered_keywords = Counter(all_keywords)
    avg_title_words = (
        sum(len(t.split()) for t in recent_titles) / len(recent_titles)
        if recent_titles else 8
    )

    patterns = {
        "avg_title_words": round(avg_title_words, 1),
        "top_formats": [fmt for fmt, _ in format_counts.most_common(3)],
        "hot_keywords": [kw for kw, _ in covered_keywords.most_common(20)],
    }

    result = {
        "recent_titles": recent_titles,
        "covered_keywords": dict(covered_keywords.most_common(50)),
        "format_counts": dict(format_counts),
        "patterns": patterns,
        "by_niche": by_niche,
    }

    logger.info(
        "Competitor analysis done: %d titles, top format=%s, hot_kw=%s",
        len(recent_titles),
        patterns["top_formats"][:2] if patterns["top_formats"] else "?",
        patterns["hot_keywords"][:5],
    )
    return result
