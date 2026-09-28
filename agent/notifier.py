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


def send_whatsapp_notification(title: str, url: str, slot: str, total_posts: int) -> bool:
    """
    Send a WhatsApp notification using CallMeBot (100% Free personal API).
    Requires environment variables:
      - WHATSAPP_PHONE (e.g. +919876543210 or 919876543210)
      - WHATSAPP_APIKEY (obtained by sending 1 message to CallMeBot)
    """
    phone = os.getenv("WHATSAPP_PHONE", "").strip().replace(" ", "").replace("-", "")
    apikey = os.getenv("WHATSAPP_APIKEY", "").strip()

    if not phone or not apikey:
        logger.info("WhatsApp notifications not configured (WHATSAPP_PHONE / WHATSAPP_APIKEY not set).")
        return False

    # Format numbers
    progress_pct = min(int((total_posts / 25) * 100), 100)
    remaining_posts = max(25 - total_posts, 0)

    message = (
        f"🚀 *AI Income Lab — New Article Live!*\n\n"
        f"📌 *Title:* {title}\n"
        f"🕒 *Edition:* {slot.capitalize()}\n"
        f"🔗 *Read Post:* {url}\n\n"
        f"📊 *AdSense Goal Progress:*\n"
        f"• Total Posts: {total_posts} / 25 ({progress_pct}%)\n"
        f"• Remaining for AdSense: {remaining_posts} posts\n\n"
        f"💡 *Action:* Tap the link and share it on your status or social media for instant views!"
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


def send_telegram_notification(title: str, url: str, slot: str, total_posts: int) -> bool:
    """Optional backup: Send instant notification via Telegram Bot."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        return False

    message = (
        f"🚀 <b>AI Income Lab — New Article Live!</b>\n\n"
        f"📌 <b>Title:</b> {title}\n"
        f"🕒 <b>Edition:</b> {slot.capitalize()}\n"
        f"🔗 <a href='{url}'>Read Article</a>\n\n"
        f"📊 <b>Total Published:</b> {total_posts} posts"
    )

    try:
        tg_url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        resp = requests.post(tg_url, json=payload, timeout=15)
        return resp.status_code == 200
    except Exception as e:
        logger.warning("Error sending Telegram notification: %s", e)
        return False


def notify_all(title: str, url: str, slot: str, total_posts: int):
    """Attempt WhatsApp first, then Telegram if configured."""
    send_whatsapp_notification(title, url, slot, total_posts)
    send_telegram_notification(title, url, slot, total_posts)
