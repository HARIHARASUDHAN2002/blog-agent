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
from agent.database import find_duplicate_in_published, get_all_published_titles, get_all_articles


def select_topics(
    trends: list[dict],
    competitor_analysis: dict,
    n: int = 1,
    slot: str = "morning",
    existing_titles: list[str] | None = None,
    traffic_stats: dict | None = None,
) -> list[dict]:
    """
    Evaluate trends across ALL THREE time horizons (24 Hours, Last Week, Last Month)
    in a single unified pool, strictly verify no duplicate exists, and pick the single best topic.
    Dynamically adapts topic selection based on live blog analytics and niche diversification.
    """
    niches_cfg = _load_niches()
    niches = niches_cfg.get("niches", [])
    
    # Load all published titles from DB and caller (e.g. Blogger live API)
    published_titles = list(dict.fromkeys((existing_titles or []) + get_all_published_titles()))
    recent_keywords = set(get_recent_keywords(60))

    # Analytics feedback: analyze past niche distribution
    past_articles = get_all_articles()

    niche_counts = {}
    for a in past_articles:
        niche_id = a.get("niche", "tech_innovation")
        niche_counts[niche_id] = niche_counts.get(niche_id, 0) + 1

    last_published_niche = past_articles[-1].get("niche") if past_articles else None
    stats = traffic_stats or {}
    last_7d_views = stats.get("last_7_days", 0)

    # Build competitor word sets for gap analysis
    comp_titles = competitor_analysis.get("recent_titles", [])
    comp_word_sets = [set(t.lower().split()) for t in comp_titles if t]

    horizon_format_map = {
        "24h": "market_breakdown",   # Real-time trend pulse & immediate news analysis
        "week": "how_to",            # Weekly deep dive, teardown & practical guide
        "month": "case_study",       # Big picture explainer & future discovery
    }

    candidates = []

    for trend in trends:
        raw_title = trend.get("title", "")
        if not raw_title or len(raw_title) < 8:
            continue

        topic = _title_to_blog_topic(raw_title)
        horizon = trend.get("horizon", "24h")

        # STRICT DUPLICATE CHECK: Verify it has not been published already
        is_dup, matched_title, dup_score = find_duplicate_in_published(topic, published_titles)
        if is_dup:
            logger.info("🚫 Discarding duplicate candidate '%s' (matches: '%s', score=%.2f)", topic[:50], matched_title[:50], dup_score)
            continue

        topic_words = set(topic.lower().split())

        # Competitor gap score (lower overlap = better opportunity)
        comp_overlap = _overlap_score(topic_words, comp_word_sets)
        gap_score = 1.0 - comp_overlap        # higher = bigger gap

        # Trend viral score (normalized 0-1)
        trend_score = min(trend.get("score", 1) / 500, 1.0)

        # Niche relevance across the 4 universal pillars
        best_niche = "tech_innovation"
        best_niche_score = 0.0
        for niche in niches:
            rel = _niche_relevance(topic, niche.get("topic_seeds", []))
            if rel > best_niche_score:
                best_niche_score = rel
                best_niche = niche["id"]

        # Keyword freshness (penalize if we've used same keywords recently)
        kw_penalty = sum(1 for w in topic_words if w in recent_keywords) / max(len(topic_words), 1)
        freshness = 1.0 - (kw_penalty * 0.35)

        # ── Analytics & Niche Rotation Feedback Loop ──────────────────────────
        analytics_mult = 1.0
        # If the blog has active traffic, give a small boost to high-traction pillars
        if last_7d_views > 10 and best_niche in ("tech_innovation", "business_money"):
            analytics_mult *= 1.10
        # Avoid consecutive repetition of the exact same niche
        if best_niche == last_published_niche:
            analytics_mult *= 0.85
        # Exploration bonus for under-covered pillars to test new search queries
        times_covered = niche_counts.get(best_niche, 0)
        if times_covered < max(len(past_articles) // 4, 2):
            analytics_mult *= 1.15

        # Horizon weight: Give balanced chance to 24h breaking news, weekly teardowns, and monthly breakthroughs
        horizon_boost = {
            "24h": 1.10,    # Fresh daily pulse
            "week": 1.05,   # Tested weekly momentum
            "month": 1.00,  # Evergreen monthly depth
        }.get(horizon, 1.00)

        total_score = (
            trend_score      * 0.35 +
            gap_score        * 0.30 +
            best_niche_score * 0.20 +
            freshness        * 0.15
        ) * horizon_boost * analytics_mult

        # Target SEO keywords
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
            "format": horizon_format_map.get(horizon, "how_to"),
            "horizon": horizon,
            "score": round(total_score, 4),
            "source": trend.get("source", "unknown"),
        })

    # Sort all candidates strictly by score across all 3 horizons
    candidates.sort(key=lambda x: x["score"], reverse=True)

    selected = []
    used_niches: set = set()
    for c in candidates:
        if len(selected) >= n:
            break
        # Allow variety if generating multiple articles
        if n > 1 and c["niche"] in used_niches and len(candidates) > n:
            continue
        selected.append(c)
        used_niches.add(c["niche"])

    # Fallback to seeds only if no trend candidate survived
    if len(selected) < n:
        for niche in niches:
            if len(selected) >= n:
                break
            seeds = niche.get("topic_seeds", [])
            random.shuffle(seeds)
            for seed in seeds:
                if len(selected) >= n:
                    break
                is_dup, _, _ = find_duplicate_in_published(seed, published_titles)
                if not is_dup:
                    selected.append({
                        "topic": seed,
                        "keywords": niche.get("target_keywords", [])[:3],
                        "niche": niche["id"],
                        "format": "listicle",
                        "horizon": "month",
                        "score": 0.1,
                        "source": "seed",
                    })

    logger.info("Selected %d best topic(s) across 24h, week, and month horizons:", len(selected))
    for i, t in enumerate(selected, 1):
        logger.info(
            "  %d. [%s | %s | %s] %s (score=%.3f)",
            i,
            t.get("horizon", "all").upper(),
            t["niche"],
            t["format"],
            t["topic"][:60],
            t["score"],
        )

    return selected[:n]

