"""
publisher.py — Publish articles to Blogger via the Blogger API v3.

Authentication:
  Reads token.json (generated once by setup_auth.py).
  The refresh token auto-renews the access token, so no human
  intervention is needed after the initial setup.

In GitHub Actions:
  The token.json is decoded from the BLOGGER_TOKEN_B64 secret.
"""

import json
import logging
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config.settings import BLOGGER_BLOG_ID, BLOGGER_TOKEN_FILE

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/blogger"]


def _get_credentials() -> Credentials | None:
    """Load and auto-refresh Blogger credentials from token.json."""
    token_path = Path(BLOGGER_TOKEN_FILE)
    if not token_path.exists():
        logger.error(
            "token.json not found. Run setup_auth.py locally first, then add "
            "BLOGGER_TOKEN_B64 to GitHub Secrets."
        )
        return None

    try:
        with open(token_path, encoding="utf-8") as f:
            token_data = json.load(f)

        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=SCOPES,
        )

        # Auto-refresh if expired
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            logger.info("Blogger token refreshed successfully.")

        return creds
    except Exception as e:
        logger.error("Failed to load Blogger credentials: %s", e)
        return None


def publish_article(article: dict) -> str | None:
    """
    Publish a single article to Blogger.

    Args:
        article: dict with keys: title, html_content, labels, meta_description

    Returns:
        URL of the published post, or None on failure.
    """
    blog_id = BLOGGER_BLOG_ID or os.getenv("BLOGGER_BLOG_ID", "")
    if not blog_id:
        logger.error("BLOGGER_BLOG_ID not set in environment.")
        return None

    creds = _get_credentials()
    if not creds:
        return None

    try:
        service = build("blogger", "v3", credentials=creds, cache_discovery=False)

        # Build post body
        title       = article.get("title", "Untitled")
        content     = article.get("html_content", "")
        labels      = article.get("labels", [])

        # Blogger uses 'labels' not 'tags'
        post_body = {
            "kind":    "blogger#post",
            "title":   title,
            "content": content,
            "labels":  labels[:10],   # Blogger supports up to 20, keep it clean
        }

        result = service.posts().insert(
            blogId=blog_id,
            body=post_body,
            isDraft=False,           # publish immediately
        ).execute()

        url = result.get("url", "")
        post_id = result.get("id", "")
        logger.info("✅ Published: '%s' → %s", title[:60], url)
        return url

    except HttpError as e:
        logger.error("Blogger API HTTP error: %s", e)
        return None
    except Exception as e:
        logger.error("Blogger publish failed: %s", e)
        return None
