"""
social_promoter.py — Automated Social Media Syndication Engine.

Generates ready-to-post promotional content for every published blog post:
  1. Viral Twitter / X Thread (Hook + Breakdown + Link)
  2. Professional LinkedIn / Reddit post with discussion starter
  3. Formats Markdown for the GitHub Actions Step Summary so you can
     copy-paste it in 5 seconds to get instant external traffic.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from config.settings import BLOG_NAME

logger = logging.getLogger(__name__)

PROMOTIONS_FILE = "database/social_promotions.json"


def _generate_social_package(article: dict) -> dict:
    """Generate X thread and LinkedIn/Reddit post for a published article."""
    title = article.get("title", "")
    url = article.get("url", "")
    niche = article.get("niche", "tech_innovation")
    meta = article.get("meta_description", "")
    keywords = article.get("keywords", [])

    hashtag_map = {
        "tech_innovation": "#Technology #TechNews #Innovation #Gadgets #Software",
        "business_money": "#Business #Economy #PersonalFinance #Investing #Money",
        "science_future": "#Science #Discoveries #Future #Space #Innovation",
        "culture_explainers": "#Trends #Culture #Explained #Productivity #WorldNews",
    }
    hashtags = hashtag_map.get(niche, "#Trends #Tech #Business #WorldNews #Innovation")

    # Twitter / X Thread
    tweet_1 = f"🚨 {title}\n\nHere is what you need to know about what's happening and why it matters 👇\n\n[Thread 🧵]"
    tweet_2 = f"💡 Key Takeaway:\n{meta}\n\n3 key takeaways:\n• The underlying context driving this\n• Who is impacted most\n• What to watch next"
    tweet_3 = f"📖 Read our full breakdown on {BLOG_NAME}:\n\n🔗 {url}\n\n{hashtags}"

    # LinkedIn / Reddit Community Post
    community_post = f"""📌 **{title}**

{meta}

We just published a full breakdown on **{BLOG_NAME}** diving into this development.

Here is the quick summary:
1️⃣ **The Context**: Why this is making headlines right now.
2️⃣ **The Impact**: What it means for professionals, consumers, and the industry.
3️⃣ **Looking Ahead**: Where this trend is heading next.

👉 Read the full story here: {url}

💬 **Question for you**: What's your take on this? Let's discuss in the comments!

{hashtags}
"""

    return {
        "title": title,
        "url": url,
        "niche": niche,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "twitter_thread": [tweet_1, tweet_2, tweet_3],
        "community_post": community_post.strip(),
    }


def record_social_promotion(article: dict) -> dict:
    """Generate and record social promotion package to database."""
    pkg = _generate_social_package(article)

    Path("database").mkdir(exist_ok=True)
    existing = []
    if Path(PROMOTIONS_FILE).exists():
        try:
            with open(PROMOTIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                existing = data.get("promotions", [])
        except Exception as e:
            logger.warning("Could not read %s: %s", PROMOTIONS_FILE, e)

    existing.append(pkg)
    # Keep last 50 promotions
    existing = existing[-50:]

    try:
        with open(PROMOTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump({"promotions": existing}, f, indent=2)
    except Exception as e:
        logger.error("Failed to save social promotions: %s", e)

    return pkg


def format_github_step_summary(promotions: list[dict]) -> str:
    """Format promotions as GitHub Step Summary Markdown for 1-click sharing."""
    if not promotions:
        return "No articles published in this run."

    lines = [
        "## 📢 Social Media Syndication Kit",
        "> Copy & paste these to Twitter/X, LinkedIn, or Reddit to drive instant traffic to your blog!\n",
    ]

    for i, p in enumerate(promotions, 1):
        lines.append(f"### Article {i}: [{p['title']}]({p['url']})")
        lines.append("#### 🐦 Twitter / X Thread")
        lines.append("```text")
        for idx, tweet in enumerate(p["twitter_thread"], 1):
            lines.append(f"--- Tweet {idx} ---")
            lines.append(tweet)
            lines.append("")
        lines.append("```\n")

        lines.append("#### 💼 LinkedIn / Reddit Post")
        lines.append("```markdown")
        lines.append(p["community_post"])
        lines.append("```\n")
        lines.append("---\n")

    return "\n".join(lines)


def ping_search_aggregators(title: str, url: str) -> bool:
    """
    Broadcast published blog post URL to search engines and open indexers
    via Ping-O-Matic (covers Google Blog Search, Weblogs, FeedBurner, Syndic8).
    100% free and requires no API keys.
    """
    try:
        import urllib.parse
        import requests
        ping_url = (
            f"https://pingomatic.com/ping/?"
            f"title={urllib.parse.quote(title)}&"
            f"blogurl={urllib.parse.quote(url)}&"
            f"rssurl={urllib.parse.quote(url + '/feeds/posts/default')}&"
            f"chk_weblogscom=on&chk_blogs=on&chk_feedburner=on&chk_syndic8=on"
        )
        resp = requests.get(ping_url, timeout=10)
        logger.info("📡 Ping-O-Matic: broadcasted '%s' to open search indexers (status %d)", title[:45], resp.status_code)
        return True
    except Exception as e:
        logger.warning("Could not ping open search aggregators: %s", e)
        return False


def syndicate_to_devto(article: dict) -> str | None:
    """
    Automatically cross-publish article to open-source platform Dev.to
    if DEVTO_API_KEY is configured in GitHub Secrets / environment.
    Sets canonical_url to your Blogger post, passing 100% SEO credit to your blog.
    """
    api_key = os.getenv("DEVTO_API_KEY", "").strip()
    if not api_key:
        return None

    title = article.get("title", "")
    url = article.get("url", "")
    body_markdown = article.get("meta_description", "") + f"\n\n👉 **Read the full, in-depth breakdown on TrendPulse Daily:** [{url}]({url})"
    tags = [t.lower().replace(" ", "").replace("-", "") for t in article.get("labels", []) if t][:4]

    try:
        import requests
        devto_url = "https://dev.to/api/articles"
        headers = {"api-key": api_key, "Content-Type": "application/json"}
        payload = {
            "article": {
                "title": title,
                "published": True,
                "body_markdown": body_markdown,
                "tags": tags or ["technology", "trends"],
                "canonical_url": url,
            }
        }
        resp = requests.post(devto_url, json=payload, headers=headers, timeout=15)
        if resp.status_code in (200, 201):
            devto_post_url = resp.json().get("url", "")
            logger.info("✅ Auto-syndicated to Dev.to: %s", devto_post_url)
            return devto_post_url
        else:
            logger.warning("Dev.to syndication returned HTTP %d: %s", resp.status_code, resp.text)
            return None
    except Exception as e:
        logger.warning("Error syndicating to Dev.to: %s", e)
        return None

