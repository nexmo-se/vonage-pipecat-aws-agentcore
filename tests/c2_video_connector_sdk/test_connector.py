#!/usr/bin/env python3
"""
Test C2: Vonage Video Connector SDK

Verifies that the Video Connector SDK can join an existing Vonage Video
session as a server-side WebRTC participant.

Platform: Linux only (native Linux binary required).
          Run via Docker on macOS — see README.md.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".env").exists():
            return candidate
    return start.resolve()  # .env not found; env vars come from docker-compose env_file


REPO_ROOT = find_repo_root(Path(__file__).parent)
load_dotenv(REPO_ROOT / ".env")


async def main() -> None:
    application_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    private_key_path = os.getenv("VONAGE_PRIVATE_KEY", "private.key").strip()
    session_id = os.getenv("VONAGE_SESSION_ID", "").strip()

    # ── Validate env vars ─────────────────────────────────────────
    missing: list[str] = []
    if not application_id:
        missing.append("VONAGE_APPLICATION_ID")
    if not session_id:
        missing.append("VONAGE_SESSION_ID")
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    private_key_file = Path(private_key_path)
    if not private_key_file.is_absolute():
        private_key_file = REPO_ROOT / private_key_path
    if not private_key_file.exists():
        print(f"ERROR: Private key not found: {private_key_file}")
        sys.exit(1)

    # ── Generate publisher token ──────────────────────────────────
    try:
        from vonage import Auth, Vonage
        from vonage_video_connector import VideoConnector
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

    token = client.video.generate_client_token(
        session_id=session_id,
        role="publisher",
        expire_time=3600,
    )
    print("✓ Generated publisher token")

    # ── Connect via Video Connector SDK ───────────────────────────
    print(f"Connecting to session {session_id} as WebRTC participant …")
    connector = VideoConnector(
        session_id=session_id,
        token=token,
        application_id=application_id,
    )

    await connector.connect()
    print("✓ Connected to session as WebRTC participant")

    print("Staying connected for 5 seconds …")
    await asyncio.sleep(5)

    await connector.disconnect()
    print("✓ Disconnected from session")
    print("\nTest C2 PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
