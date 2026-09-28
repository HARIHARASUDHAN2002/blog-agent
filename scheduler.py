"""
scheduler.py — Main daily orchestrator for AI Income Lab blog agent.

Runs the full pipeline once per day (triggered by GitHub Actions cron):
  1. Fetch trends from HN + Google Trends + Reddit
  2. Analyze competitor blogs to learn what's working
  3. Select today's 3 best topics (trending + gap analysis)
  4. Generate full SEO articles with Gemini
  5. Publish to Blogger
  6. Save results to database (JSON file committed to GitHub)

Exit codes:
  0 = at least 1 article published successfully
  1 = all articles failed
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

# ── Imports after logging is configured ───────────────────────────────────────
from config.settings import ARTICLES_PER_DAY, GEMINI_API_KEY, BLOGGER_BLOG_ID
from agent.trend_fetcher import fetch_all_trends
from agent.competitor_analyzer import analyze_competitors
from agent.topic_selector import select_topics
from agent.article_generator import generate_article
from agent.publisher import publish_article
from agent.database import add_article, get_stats


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
    """
    Run the full daily pipeline. Returns number of articles successfully published.
    """
    start_time = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("🚀 AI Income Lab Blog Agent — Daily Run")
    logger.info("   Time: %s UTC", start_time.strftime("%Y-%m-%d %H:%M"))
    logger.info("=" * 60)

    if not _validate_config():
        logger.error("Configuration error — aborting run.")
        return 0

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

    # ── Step 3: Select today's topics ─────────────────────────────────────────
    logger.info("\n🎯 Step 3/4: Selecting today's %d topics...", ARTICLES_PER_DAY)
    try:
        topics = select_topics(trends, competitor_data, n=ARTICLES_PER_DAY)
        logger.info("   Selected %d topics", len(topics))
    except Exception as e:
        logger.error("Topic selection failed: %s", e)
        return 0

    if not topics:
        logger.error("No topics selected — skipping today's run.")
        return 0

    # ── Step 4: Generate + publish articles ───────────────────────────────────
    logger.info("\n✍️  Step 4/4: Generating and publishing articles...")
    published_count = 0

    for i, topic in enumerate(topics, 1):
        logger.info("\n--- Article %d/%d ---", i, len(topics))
        logger.info("Topic: %s", topic["topic"])
        logger.info("Niche: %s | Format: %s", topic["niche"], topic["format"])

        # Generate article
        try:
            article = generate_article(topic, competitor_data)
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
            # Record in database
            add_article(
                title=article.get("title", topic["topic"]),
                url=url,
                niche=topic["niche"],
                keywords=topic.get("keywords", []),
            )
            published_count += 1
            logger.info("✅ Article %d published: %s", i, url)
        else:
            logger.warning("❌ Article %d failed to publish.", i)

        # Respect Gemini rate limits (free tier: 15 RPM)
        if i < len(topics):
            logger.info("   Waiting 10s before next article (rate limit)...")
            time.sleep(10)

    # ── Summary ───────────────────────────────────────────────────────────────
    duration = (datetime.now(timezone.utc) - start_time).seconds
    stats = get_stats()
    logger.info("\n" + "=" * 60)
    logger.info("📊 Daily Run Summary")
    logger.info("   Published today: %d/%d articles", published_count, len(topics))
    logger.info("   Total articles ever: %d", stats.get("total", 0))
    logger.info("   Duration: %ds", duration)
    logger.info("=" * 60)

    return published_count


if __name__ == "__main__":
    count = run()
    sys.exit(0 if count > 0 else 1)
