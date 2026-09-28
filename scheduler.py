"""
scheduler.py — Main daily orchestrator for AI Income Lab blog agent.

Supports staggered publishing (Morning, Noon, Evening editions):
  1. Fetch trends from HN + Google Trends + Reddit
  2. Analyze competitor blogs to find content gaps
  3. Detect current slot (Morning: Market Signal, Noon: Masterclass, Evening: Case Study)
  4. Select unique topic & format avoiding recent titles
  5. Generate full SEO article with Gemini using slot archetype & anti-AI rules
  6. Publish to Blogger
  7. Generate social media syndication kit (X thread & LinkedIn/Reddit post)
  8. Save database and write to GitHub Actions Step Summary
"""

import logging
import os
import sys
import time
from datetime import datetime, timezone

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scheduler")

# ── Imports ───────────────────────────────────────────────────────────────────
from config.settings import ARTICLES_PER_RUN, BLOGGER_BLOG_ID, GEMINI_API_KEY, SLOT_CONFIGS
from agent.trend_fetcher import fetch_all_trends
from agent.competitor_analyzer import analyze_competitors
from agent.topic_selector import select_topics
from agent.article_generator import generate_article
from agent.publisher import publish_article, get_blog_pageviews
from agent.database import add_article, get_recent_titles, get_stats
from agent.social_promoter import format_github_step_summary, record_social_promotion
from agent.notifier import notify_all


def _detect_slot() -> str:
    """Detect whether this run is morning, noon, or evening based on UTC hour or env var."""
    override = os.getenv("BLOG_SLOT", "").lower().strip()
    if override in ("morning", "noon", "evening"):
        return override

    hour = datetime.now(timezone.utc).hour
    # UTC 00:00 - 06:00 (05:30 - 11:30 IST) -> Morning
    # UTC 06:00 - 11:00 (11:30 - 16:30 IST) -> Noon
    # UTC 11:00 - 23:59 (16:30 - 05:29 IST) -> Evening
    if hour < 6:
        return "morning"
    elif hour < 11:
        return "noon"
    else:
        return "evening"


def _validate_config() -> bool:
    """Check that all required secrets are set."""
    ok = True
    if not GEMINI_API_KEY:
        logger.error("❌ GEMINI_API_KEY is not set.")
        ok = False
    if not BLOGGER_BLOG_ID:
        logger.error("❌ BLOGGER_BLOG_ID is not set.")
        ok = False
    if not os.path.exists("token.json"):
        logger.error("❌ token.json not found. See setup instructions.")
        ok = False
    return ok


def run() -> int:
    """Run the staggered edition pipeline. Returns number of articles published."""
    start_time = datetime.now(timezone.utc)
    slot = _detect_slot()
    slot_info = SLOT_CONFIGS.get(slot, {})

    logger.info("=" * 60)
    logger.info("🚀 AI Income Lab Blog Agent — Staggered Edition Run")
    logger.info("   Time: %s UTC", start_time.strftime("%Y-%m-%d %H:%M"))
    logger.info("   Slot: [%s] -> %s", slot.upper(), slot_info.get("name", "Daily Post"))
    logger.info("=" * 60)

    if not _validate_config():
        logger.error("Configuration error — aborting run.")
        return 0

    recent_titles = get_recent_titles(30)

    # ── Step 1: Fetch trends ──────────────────────────────────────────────────
    logger.info("\n📈 Step 1/4: Fetching worldwide trends...")
    try:
        trends = fetch_all_trends()
        logger.info("   Found %d trending topics", len(trends))
    except Exception as e:
        logger.error("Trend fetching failed: %s", e)
        trends = []

    # ── Step 2: Analyze competitors ───────────────────────────────────────────
    logger.info("\n🔍 Step 2/4: Analyzing competitor blogs...")
    try:
        competitor_data = analyze_competitors()
        logger.info(
            "   Analyzed %d competitor articles. Top formats: %s",
            len(competitor_data.get("recent_titles", [])),
            competitor_data.get("patterns", {}).get("top_formats", []),
        )
    except Exception as e:
        logger.error("Competitor analysis failed: %s", e)
        competitor_data = {"recent_titles": [], "patterns": {}, "covered_keywords": {}, "by_niche": {}}

    # ── Step 3: Select topic for this slot ────────────────────────────────────
    target_count = ARTICLES_PER_RUN
    logger.info("\n🎯 Step 3/4: Selecting %d topic(s) for [%s] edition...", target_count, slot.upper())
    try:
        topics = select_topics(trends, competitor_data, n=target_count, slot=slot)
        logger.info("   Selected %d topic(s)", len(topics))
    except Exception as e:
        logger.error("Topic selection failed: %s", e)
        return 0

    if not topics:
        logger.error("No topics selected — skipping run.")
        return 0

    # ── Step 4: Generate + publish articles ───────────────────────────────────
    logger.info("\n✍️  Step 4/4: Generating and publishing article(s)...")
    published_count = 0
    social_promotions = []

    for i, topic in enumerate(topics, 1):
        logger.info("\n--- Article %d/%d ---", i, len(topics))
        logger.info("Topic: %s", topic["topic"])
        logger.info("Niche: %s | Format: %s | Slot: %s", topic["niche"], topic["format"], slot)

        # Generate article with slot archetype and anti-AI filter
        try:
            article = generate_article(
                topic=topic,
                competitor_analysis=competitor_data,
                slot=slot,
                recent_titles=recent_titles,
            )
        except Exception as e:
            logger.error("Article generation failed: %s", e)
            article = None

        if not article:
            logger.warning("Skipping topic (generation failed): %s", topic["topic"])
            time.sleep(3)
            continue

        # Publish to Blogger
        try:
            url = publish_article(article)
        except Exception as e:
            logger.error("Publishing failed: %s", e)
            url = None

        if url:
            article["url"] = url
            # Record in database
            add_article(
                title=article.get("title", topic["topic"]),
                url=url,
                niche=topic["niche"],
                keywords=topic.get("keywords", []),
            )
            published_count += 1
            logger.info("✅ Article %d published: %s", i, url)

            # Generate social media syndication kit
            try:
                promo_pkg = record_social_promotion(article)
                social_promotions.append(promo_pkg)
                logger.info("📣 Social promotion kit generated for Twitter and LinkedIn/Reddit")
            except Exception as e:
                logger.warning("Could not generate social promo: %s", e)

            # Send instant WhatsApp notification with live overall view counts
            try:
                current_stats = get_stats()
                traffic_stats = get_blog_pageviews()
                notify_all(
                    title=article.get("title", topic["topic"]),
                    url=url,
                    slot=slot,
                    total_posts=current_stats.get("total", published_count),
                    traffic_stats=traffic_stats,
                )
            except Exception as e:
                logger.warning("Notification error: %s", e)
        else:
            logger.warning("❌ Article %d failed to publish.", i)

        if i < len(topics):
            time.sleep(10)

    # ── Summary & GitHub Step Summary ─────────────────────────────────────────
    duration = (datetime.now(timezone.utc) - start_time).seconds
    stats = get_stats()
    logger.info("\n" + "=" * 60)
    logger.info("📊 Run Summary")
    logger.info("   Edition: %s", slot.upper())
    logger.info("   Published: %d/%d articles", published_count, len(topics))
    logger.info("   Total articles ever: %d", stats.get("total", 0))
    logger.info("   Duration: %ds", duration)
    logger.info("=" * 60)

    # Write to GitHub Step Summary if running in Actions
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path and os.path.exists(os.path.dirname(summary_path)):
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(f"\n# 🤖 AI Income Lab — [{slot.upper()}] Edition Published\n\n")
                f.write(f"- **Edition**: `{slot.capitalize()}` ({slot_info.get('name', '')})\n")
                f.write(f"- **Published Today**: `{published_count}` article(s)\n")
                f.write(f"- **Total Blog Posts**: `{stats.get('total', 0)}`\n\n")
                if social_promotions:
                    f.write(format_github_step_summary(social_promotions))
        except Exception as e:
            logger.warning("Could not write GITHUB_STEP_SUMMARY: %s", e)

    return published_count


if __name__ == "__main__":
    count = run()
    sys.exit(0 if count > 0 else 1)
