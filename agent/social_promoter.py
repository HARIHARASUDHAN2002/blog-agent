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
