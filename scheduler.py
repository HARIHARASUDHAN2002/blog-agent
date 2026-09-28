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
from agent.publisher import publish_article, get_blog_pageviews, get_live_blogger_post_titles
from agent.database import add_article, get_recent_titles, get_all_published_titles, find_duplicate_in_published, get_stats
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
    logger.info("🚀 TrendPulse Daily Blog Agent — Multi-Horizon Edition Run")
    logger.info("   Time: %s UTC", start_time.strftime("%Y-%m-%d %H:%M"))
    logger.info("   Slot: [%s] -> %s", slot.upper(), slot_info.get("name", "Daily Post"))
    logger.info("=" * 60)

    if not _validate_config():
        logger.error("Configuration error — aborting run.")
        return 0

    # ── Gather all previously published titles for strict duplicate prevention ──
    live_blogger_titles = get_live_blogger_post_titles()
    db_titles = get_all_published_titles()
    all_published_titles = list(dict.fromkeys(live_blogger_titles + db_titles))
    logger.info("   Tracked published articles: %d (Live Blogger: %d, DB: %d)", len(all_published_titles), len(live_blogger_titles), len(db_titles))

    recent_titles = get_recent_titles(30)

    # ── Step 1: Fetch trends across 24h, Week, and Month ─────────────────────
    logger.info("\n📈 Step 1/4: Fetching trends across 24h, Week, and Month...")
    try:
        trends = fetch_all_trends()
        logger.info("   Found %d trending topics across all horizons", len(trends))
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

    # ── Step 3: Evaluate all 3 horizons & pick the best unwritten topic ───────
    target_count = ARTICLES_PER_RUN
    logger.info("\n🎯 Step 3/4: Comparing 24h, Week, and Month trends to pick the best topic...")
    try:
        # Request extra ranked candidates so if one matches an existing post, backups are ready
        candidate_pool = select_topics(
            trends=trends,
            competitor_analysis=competitor_data,
            n=max(target_count * 4, 6),
            slot=slot,
            existing_titles=all_published_titles,
        )
        logger.info("   Ranked %d candidate topics across horizons", len(candidate_pool))
    except Exception as e:
        logger.error("Topic selection failed: %s", e)
        return 0

    if not candidate_pool:
        logger.error("No valid topics found — skipping run.")
        return 0

    # ── Step 4: Verify uniqueness, then generate + publish ─────────────────────
    logger.info("\n✍️  Step 4/4: Verifying uniqueness and generating article...")
    published_count = 0
    social_promotions = []

    for cand_idx, topic in enumerate(candidate_pool, 1):
        if published_count >= target_count:
            break

        cand_title = topic["topic"]
        cand_horizon = topic.get("horizon", "all").upper()
        logger.info("\n--- Evaluating Candidate %d/%d [%s] ---", cand_idx, len(candidate_pool), cand_horizon)
        logger.info("Topic: %s", cand_title)
        logger.info("Pillar: %s | Format: %s | Horizon: %s", topic["niche"], topic["format"], cand_horizon)

        # ── Pre-generation duplicate verification ──
        is_dup, matched_title, dup_score = find_duplicate_in_published(cand_title, all_published_titles)
        if is_dup:
            logger.warning(
                "🚫 SKIP: Candidate '%s' was already created! Matches: '%s' (similarity: %.2f)",
                cand_title[:50],
                matched_title[:50],
                dup_score,
            )
            continue

        # Generate article with verified unique topic
        logger.info("✅ Verified unique! Generating article with Gemini...")
        try:
            article = generate_article(
                topic=topic,
                competitor_analysis=competitor_data,
                slot=slot,
                recent_titles=all_published_titles,
            )
        except Exception as e:
            logger.error("Article generation failed: %s", e)
            article = None

        if not article:
            logger.warning("Skipping candidate (generation failed): %s", cand_title)
            time.sleep(3)
            continue

        # ── Post-generation title uniqueness check ──
        generated_title = article.get("title", cand_title)
        is_post_dup, matched_title, dup_score = find_duplicate_in_published(generated_title, all_published_titles)
        if is_post_dup:
            logger.warning(
                "🚫 SKIP: Generated title '%s' is too similar to existing '%s' (similarity: %.2f)",
                generated_title[:50],
                matched_title[:50],
                dup_score,
            )
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
                title=generated_title,
                url=url,
                niche=topic["niche"],
                keywords=topic.get("keywords", []),
            )
            all_published_titles.append(generated_title)
            published_count += 1
            logger.info("✅ Article %d/%d published: %s", published_count, target_count, url)


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
            logger.warning("❌ Candidate %d failed to publish.", cand_idx)

        if published_count < target_count and cand_idx < len(candidate_pool):
            time.sleep(10)

    # ── Summary & GitHub Step Summary ─────────────────────────────────────────
    duration = (datetime.now(timezone.utc) - start_time).seconds
    stats = get_stats()
    logger.info("\n" + "=" * 60)
    logger.info("📊 Run Summary")
    logger.info("   Edition: %s", slot.upper())
    logger.info("   Published: %d/%d articles", published_count, target_count)
    logger.info("   Total articles ever: %d", stats.get("total", 0))
    logger.info("   Duration: %ds", duration)
    logger.info("=" * 60)

    # Write to GitHub Step Summary if running in Actions
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path and os.path.exists(os.path.dirname(summary_path)):
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(f"\n# 🌐 TrendPulse Daily — [{slot.upper()}] Edition Published\n\n")
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
