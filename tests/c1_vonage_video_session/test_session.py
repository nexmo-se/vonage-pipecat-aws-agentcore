#!/usr/bin/env python3
"""
Test C1: Vonage Video API — Session Creation

Verifies:
  1. Authentication with VONAGE_APPLICATION_ID + VONAGE_PRIVATE_KEY
  2. Video session creation via the Vonage Video REST API
  3. Client token generation (publisher role)
  4. Prints a Vonage playground URL for browser verification

Platform: Any (macOS, Linux, Windows)
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the repo root (two levels up from this file)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def main() -> None:
    application_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    private_key_path = os.getenv("VONAGE_PRIVATE_KEY", "private.key").strip()
    session_id = os.getenv("VONAGE_SESSION_ID", "").strip()

    # ── Validate required env vars ────────────────────────────────
    if not application_id:
        print("ERROR: VONAGE_APPLICATION_ID is not set in .env")
        sys.exit(1)

    private_key_file = Path(private_key_path)
    if not private_key_file.is_absolute():
        # Resolve relative to repo root
        private_key_file = Path(__file__).resolve().parents[2] / private_key_path
    if not private_key_file.exists():
        print(f"ERROR: Private key file not found: {private_key_file}")
        print("  Download your application's private.key from the Vonage Dashboard")
        sys.exit(1)

    # ── Initialise Vonage client ──────────────────────────────────
    try:
        from vonage import Auth, Vonage
        from vonage_video import CreateSessionRequest
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("  Run: pip install -r requirements.txt")
        sys.exit(1)

    client = Vonage(
        Auth(
            application_id=application_id,
            private_key=str(private_key_file),
        )
    )

    # ── Create or reuse session ───────────────────────────────────
    if not session_id:
        print("Creating new Vonage Video session …")
        session = client.video.create_session(
            CreateSessionRequest(media_mode="routed")
        )
        session_id = session.session_id
        print(f"✓ Created session: {session_id}")
        print(f"  ➜ Add VONAGE_SESSION_ID={session_id} to your .env file\n")
    else:
        print(f"✓ Using existing session: {session_id}")

    # ── Generate a client token ───────────────────────────────────
    token = client.video.generate_client_token(
        session_id=session_id,
        role="publisher",
        expire_time=86400,  # 24 hours
    )
    print("✓ Generated client token (publisher, 24 h)")

    # ── Print browser demo URL ────────────────────────────────────
    demo_url = (
        "https://tokbox.com/developer/tools/playground/"
        f"?apiKey={application_id}"
        f"&sessionId={session_id}"
        f"&token={token}"
    )
    separator = "=" * 60
    print(f"\n{separator}")
    print("Browser Demo URL:")
    print(demo_url)
    print(separator)
    print("\nOpen the URL above in a browser to join the video session.")
    print("\nTest C1 PASSED ✓")


if __name__ == "__main__":
    main()
