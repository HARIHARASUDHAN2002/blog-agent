"""
topic_selector.py — Smart topic selection engine.

Combines:
  1. Trending topics (from trend_fetcher)
  2. Competitor coverage (from competitor_analyzer)
  3. Published history (from database)
  4. Niche weights (from niches.json)

Scores each candidate topic and returns the top N unique, fresh topics
that are trending but NOT already covered by competitors this week —
the "content gap" sweet spot.
"""

import json
import logging
import random
import re
from pathlib import Path

from agent.database import get_recent_titles, get_recent_keywords

logger = logging.getLogger(__name__)

NICHES_FILE = "config/niches.json"


def _load_niches() -> dict:
    try:
        with open(NICHES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load niches: %s", e)
        return {}


def _title_to_blog_topic(raw_title: str) -> str:
    """
    Convert a raw trend/news headline into a blog-friendly topic phrase.
    e.g. "OpenAI releases GPT-5 for free" → "How to Use GPT-5 For Free: Complete Guide"
    """
    raw = raw_title.strip()
    # Already looks like a blog title
    if any(raw.lower().startswith(p) for p in ("how to", "best ", "top ", "what is", "why ")):
        return raw
    # News headline → blog topic
    raw = re.sub(r"\s+says\s+.*$", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s+reports?\s+.*$", "", raw, flags=re.IGNORECASE)
    return raw


def _overlap_score(candidate_words: set, competitor_words_list: list[set]) -> float:
    """
    0.0 = totally unique (not covered by competitors — best!)
    1.0 = identical to competitor content (avoid)
    """
    if not competitor_words_list:
        return 0.0
    overlaps = [
        len(candidate_words & cw) / max(len(candidate_words | cw), 1)
        for cw in competitor_words_list
    ]
    return max(overlaps)


def _published_overlap_score(candidate_words: set, recent_titles: list[str]) -> float:
    """Check if we've already written something too similar."""
    for title in recent_titles:
        existing = set(title.lower().split())
        if not existing:
            continue
        score = len(candidate_words & existing) / max(len(candidate_words | existing), 1)
        if score > 0.55:
            return 1.0   # too similar
    return 0.0


def _niche_relevance(title: str, niche_seeds: list[str]) -> float:
    """How relevant is a title to a given niche? 0.0–1.0"""
    title_lower = title.lower()
    matches = sum(1 for seed in niche_seeds if seed.lower() in title_lower)
    return min(matches / 3, 1.0)


from config.settings import SLOT_CONFIGS


def select_topics(
    trends: list[dict],
    competitor_analysis: dict,
    n: int = 1,
    slot: str = "morning",
) -> list[dict]:
    """
    Select the best N topics to write about today.

    Returns list of dicts:
    {
        "topic":   str,       # clean blog topic
        "keywords": [str],    # target SEO keywords
        "niche":   str,       # niche id
        "format":  str,       # suggested format (how_to / market_breakdown / case_study)
        "score":   float,
    }
    """
    niches_cfg = _load_niches()
    niches = niches_cfg.get("niches", [])
    recent_titles = get_recent_titles(40)
    recent_keywords = set(get_recent_keywords(60))

    # Slot configuration
    slot_cfg = SLOT_CONFIGS.get(slot, SLOT_CONFIGS.get("morning", {}))
    preferred_format = slot_cfg.get("format", "how_to")
    preferred_niche  = slot_cfg.get("niche_preference", "ai_finance_overlap")

    # Build competitor word sets for gap analysis
    comp_titles = competitor_analysis.get("recent_titles", [])
    comp_word_sets = [set(t.lower().split()) for t in comp_titles if t]
    hot_keywords = set(competitor_analysis.get("patterns", {}).get("hot_keywords", []))

    # Rotate formats across articles so no two articles ever use the same format
    format_rotation = [preferred_format, "how_to", "market_breakdown", "case_study", "listicle", "review"]
    # Remove duplicates preserving order
    format_rotation = list(dict.fromkeys(format_rotation))

    candidates = []

    for trend in trends:
        raw_title = trend.get("title", "")
        if not raw_title or len(raw_title) < 8:
            continue

        topic = _title_to_blog_topic(raw_title)
        topic_words = set(topic.lower().split())

        # Skip if already published something too similar
        pub_overlap = _published_overlap_score(topic_words, recent_titles)
        if pub_overlap >= 1.0:
            continue

        # Competitor gap score (lower overlap = better opportunity)
        comp_overlap = _overlap_score(topic_words, comp_word_sets)
        gap_score = 1.0 - comp_overlap        # higher = bigger gap

        # Trend score (normalised to 0-1)
        trend_score = min(trend.get("score", 1) / 500, 1.0)

        # Niche relevance
        best_niche = "tech_innovation"
        best_niche_score = 0.0
        for niche in niches:
            rel = _niche_relevance(topic, niche.get("topic_seeds", []))
            if rel > best_niche_score:
                best_niche_score = rel
                best_niche = niche["id"]

        # Keyword freshness (penalise if we've used same keywords recently)
        kw_penalty = sum(1 for w in topic_words if w in recent_keywords) / max(len(topic_words), 1)
        freshness = 1.0 - (kw_penalty * 0.4)

        total_score = (
            trend_score   * 0.30 +
            gap_score     * 0.35 +
            best_niche_score * 0.20 +
            freshness     * 0.15
        )

        # Horizon match bonus (Morning -> 24h, Noon -> Week, Evening -> Month)
        horizon = trend.get("horizon", "24h")
        target_horizon = slot_cfg.get("horizon", "24h")
        if horizon == target_horizon:
            total_score *= 1.25

        # Extract target SEO keywords
        niche_data = next((n for n in niches if n["id"] == best_niche), {})
        niche_keywords = niche_data.get("target_keywords", [])
        topic_keywords = [w for w in topic_words if len(w) > 4 and w not in {
            "about", "their", "these", "those", "there", "where", "which",
        }][:4]
        keywords = list(dict.fromkeys(niche_keywords[:2] + topic_keywords))[:5]

        candidates.append({
            "topic": topic,
            "keywords": keywords,
            "niche": best_niche,
            "format": preferred_format,
            "horizon": horizon,
            "score": round(total_score, 4),
            "source": trend.get("source", "unknown"),
        })

    # Boost candidates matching the slot's preferred niche
    for c in candidates:
        if c["niche"] == preferred_niche:
            c["score"] = round(c["score"] * 1.25, 4)

    # Sort by score, take top N (ensuring niche variety)
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Pick top candidates and assign distinct formats
    selected = []
    used_niches: set = set()
    for c in candidates:
        if len(selected) >= n:
            break
        # Allow max 2 from same niche
        if sum(1 for s in selected if s["niche"] == c["niche"]) >= 2:
            continue
        c["format"] = format_rotation[len(selected) % len(format_rotation)]
        selected.append(c)
        used_niches.add(c["niche"])

    # If not enough scored candidates, pad with niche seed topics
    if len(selected) < n:
        for niche in niches:
            if len(selected) >= n:
                break
            seeds = niche.get("topic_seeds", [])
            random.shuffle(seeds)
            for seed in seeds:
                if len(selected) >= n:
                    break
                if not _published_overlap_score(set(seed.lower().split()), recent_titles):
                    selected.append({
                        "topic": seed,
                        "keywords": niche.get("target_keywords", [])[:3],
                        "niche": niche["id"],
                        "format": "listicle",
                        "score": 0.1,
                        "source": "seed",
                    })

    logger.info("Selected %d topics:", len(selected))
    for i, t in enumerate(selected, 1):
        logger.info("  %d. [%s] %s (score=%.3f)", i, t["niche"], t["topic"][:60], t["score"])

    return selected[:n]
