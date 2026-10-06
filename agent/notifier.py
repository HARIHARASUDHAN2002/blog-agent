"""
notifier.py — Instant Notification Service for WhatsApp (and Telegram).

Sends an alert to your WhatsApp phone whenever the blog agent:
  - Publishes a new article
  - Includes the live URL
  - Shows current total article count & AdSense milestone progress
"""

import logging
import os
import urllib.parse
import requests

logger = logging.getLogger(__name__)


def send_whatsapp_notification(title: str, url: str, slot: str, total_posts: int, traffic_stats: dict = None) -> bool:
    """
    Send a WhatsApp notification with live overall view counts.
    """
    phone = os.getenv("WHATSAPP_PHONE", "").strip().replace(" ", "").replace("-", "")
    apikey = os.getenv("WHATSAPP_APIKEY", "").strip()

    if not phone or not apikey:
        logger.info("WhatsApp notifications not configured (WHATSAPP_PHONE / WHATSAPP_APIKEY not set).")
        return False

    stats = traffic_stats or {}
    all_time_views = stats.get("all_time", "N/A")
    last_7d_views  = stats.get("last_7_days", "N/A")
    posts_count    = stats.get("total_posts", total_posts)

    message = (
        f"🚀 *AI Income Lab — New Article Live!*\n\n"
        f"📌 *Title:* {title}\n"
        f"🕒 *Edition:* {slot.capitalize()}\n"
        f"🔗 *Read Post:* {url}\n\n"
        f"📈 *Live Overall Blog Growth & Views:*\n"
        f"• 👁️ *Total Views (All-Time):* {all_time_views} views\n"
        f"• 📊 *Views (Last 7 Days):* {last_7d_views} views\n"
        f"• 📝 *Total Articles Published:* {posts_count} posts\n\n"
        f"💡 *Action:* Tap the link to view your latest article!"
    )

    try:
        encoded_text = urllib.parse.quote(message)
        callmebot_url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={encoded_text}&apikey={apikey}"
        resp = requests.get(callmebot_url, timeout=15)
        if resp.status_code == 200:
            logger.info("✅ WhatsApp notification sent successfully to %s", phone[:5] + "...")
            return True
        else:
            logger.warning("WhatsApp notification failed with status code %d: %s", resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.error("Error sending WhatsApp notification: %s", e)
        return False


import html


def send_telegram_notification(title: str, url: str, slot: str, total_posts: int, traffic_stats: dict = None) -> bool:
    """Send instant notification via Telegram Bot with live traffic stats."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        logger.info("Telegram notification skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.")
        return False

    stats = traffic_stats or {}
    all_time_views = stats.get("all_time", "N/A")
    last_7d_views  = stats.get("last_7_days", "N/A")
    posts_count    = stats.get("total_posts", total_posts)

    safe_title = html.escape(title)

    message = (
        f"🌐 <b>TrendPulse Daily — New Article Live!</b>\n\n"
        f"📌 <b>Title:</b> {safe_title}\n"
        f"🕒 <b>Edition:</b> {slot.capitalize()}\n"
        f"🔗 <a href='{url}'>Read Article on TrendPulse</a>\n\n"
        f"📈 <b>Live Traffic Analytics (Direct from Blogger):</b>\n"
        f"• 👁️ <b>Total Views (All-Time):</b> {all_time_views} views\n"
        f"• 📊 <b>Views (Last 7 Days):</b> {last_7d_views} views\n"
        f"• 📝 <b>Live Published Posts:</b> {posts_count} posts"
    )

    try:
        tg_url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        resp = requests.post(tg_url, json=payload, timeout=15)
        if resp.status_code == 200:
            logger.info("✅ Telegram notification sent successfully to chat %s", chat_id)
            return True
        else:
            logger.warning("❌ Telegram notification failed (HTTP %d): %s", resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.warning("Error sending Telegram notification: %s", e)
        return False


def notify_all(title: str, url: str, slot: str, total_posts: int, traffic_stats: dict = None):
    """Send via Telegram if configured, else WhatsApp."""
    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        logger.info("📱 Sending instant notification to Telegram bot...")
        send_telegram_notification(title, url, slot, total_posts, traffic_stats=traffic_stats)
    elif os.getenv("WHATSAPP_PHONE") and os.getenv("WHATSAPP_APIKEY"):
        logger.info("📱 Sending instant notification to WhatsApp...")
        send_whatsapp_notification(title, url, slot, total_posts, traffic_stats=traffic_stats)
    else:
        logger.info("No notification service configured (TELEGRAM_BOT_TOKEN or WHATSAPP_APIKEY not set).")
