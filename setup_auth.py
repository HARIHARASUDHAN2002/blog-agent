"""
setup_auth.py — One-time local setup script.

Run this ONCE on your local PC. It will:
  1. Open your browser → you log in with your Google account
  2. Save the OAuth token to token.json
  3. Print the base64-encoded token string to copy into GitHub Secrets

After this, you never need to run it again. GitHub Actions will use
the token to publish forever (it auto-refreshes).

Usage:
  python setup_auth.py
"""

import base64
import json
import sys
from pathlib import Path


def main():
    print("=" * 60)
    print("  AI Income Lab — One-Time Blogger Auth Setup")
    print("=" * 60)
    print()

    # Check for credentials.json
    if not Path("credentials.json").exists():
        print("❌ credentials.json not found!")
        print()
        print("Steps to get it:")
        print("  1. Go to: https://console.cloud.google.com/")
        print("  2. Create a project (or select existing)")
        print("  3. Go to APIs & Services > Library")
        print("  4. Search 'Blogger API v3' → Enable")
        print("  5. Go to APIs & Services > Credentials")
        print("  6. Click 'Create Credentials' > 'OAuth client ID'")
        print("  7. Application type: Desktop app")
        print("  8. Download JSON → rename to credentials.json")
        print("  9. Place credentials.json in this folder")
        print(" 10. Run this script again")
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
    except ImportError:
        print("❌ Required packages not installed.")
        print("Run: pip install -r requirements.txt")
        sys.exit(1)

    SCOPES = ["https://www.googleapis.com/auth/blogger"]

    print("🌐 Opening browser for Google authentication...")
    print("   (Log in with the Google account that owns your Blogger blog)")
    print()

    try:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        sys.exit(1)

    # Save token.json
    token_data = {
        "token":         creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri":     creds.token_uri,
        "client_id":     creds.client_id,
        "client_secret": creds.client_secret,
        "scopes":        list(creds.scopes),
    }

    with open("token.json", "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)

    print("✅ token.json saved successfully!")
    print()

    # Encode for GitHub Secrets
    token_bytes = json.dumps(token_data).encode("utf-8")
    token_b64 = base64.b64encode(token_bytes).decode("utf-8")

    print("=" * 60)
    print("  NEXT STEPS — Copy these into GitHub Secrets")
    print("=" * 60)
    print()
    print("Go to: GitHub repo → Settings → Secrets and variables → Actions")
    print("Add these 3 secrets:")
    print()
    print("Secret 1: GEMINI_API_KEY")
    print("  Value: <your Gemini API key from aistudio.google.com>")
    print()
    print("Secret 2: BLOGGER_BLOG_ID")

    # Try to get blog ID
    try:
        from googleapiclient.discovery import build
        service = build("blogger", "v3", credentials=creds, cache_discovery=False)
        blogs = service.blogs().listByUser(userId="self").execute()
        items = blogs.get("items", [])
        if items:
            print("  Your blogs:")
            for blog in items:
                print(f"    → {blog['name']}  |  ID: {blog['id']}  |  URL: {blog['url']}")
            print("  Value: <copy the ID above for your chosen blog>")
        else:
            print("  Value: <your Blogger blog ID (found in blogger.com URL)>")
    except Exception:
        print("  Value: <your Blogger blog ID (found in blogger.com URL)>")

    print()
    print("Secret 3: BLOGGER_TOKEN_B64")
    print("  Value:")
    print()
    print(token_b64)
    print()
    print("=" * 60)
    print("✅ Setup complete! Push this project to GitHub and the agent")
    print("   will auto-run daily at 9:00 AM IST.")
    print("=" * 60)


if __name__ == "__main__":
    main()
