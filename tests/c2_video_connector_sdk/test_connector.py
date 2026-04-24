#!/usr/bin/env python3
"""
Test C2: Vonage Video Connector SDK

Verifies that the Video Connector SDK can join an existing Vonage Video
session as a server-side WebRTC participant.

Platform: Linux only (native Linux binary required).
          Run via Docker on macOS — see README.md.
"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".env").exists():
            return candidate
    workspace_root = Path("/workspace")
    if (workspace_root / ".env").exists():
        return workspace_root
    return start.resolve()  # .env not found; env vars come from docker-compose env_file


REPO_ROOT = find_repo_root(Path(__file__).parent)
load_dotenv(REPO_ROOT / ".env")


def main() -> None:
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
        from vonage_video import TokenOptions
        from vonage_video_connector import VonageVideoClient
        from vonage_video_connector.models import (
            LoggingSettings,
            SessionAudioSettings,
            SessionAVSettings,
            SessionSettings,
        )
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
        TokenOptions(
            session_id=session_id,
            role="publisher",
        )
    )
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    print("✓ Generated publisher token")

    # ── Connect via Video Connector SDK ───────────────────────────
    print(f"Connecting to session {session_id} as WebRTC participant …")
    connector = VonageVideoClient()
    connection_state = {"connected": False, "error": None}

    def on_connected(session):
        connection_state["connected"] = True

    def on_disconnected(session):
        pass

    def on_error(session, error_description, error_code):
        connection_state["error"] = f"{error_description} (Code: {error_code})"

    session_settings = SessionSettings(
        enable_migration=False,
        av=SessionAVSettings(
            audio_subscribers_mix=SessionAudioSettings(
                sample_rate=48000,
                number_of_channels=1,
            )
        ),
        logging=LoggingSettings(level="INFO"),
    )

    success = connector.connect(
        application_id=application_id,
        session_id=session_id,
        token=token,
        session_settings=session_settings,
        on_connected_cb=on_connected,
        on_disconnected_cb=on_disconnected,
        on_error_cb=on_error,
    )

    if not success:
        print("ERROR: Connector connect() returned False")
        sys.exit(1)

    connect_deadline = time.time() + 10
    while not connection_state["connected"] and not connection_state["error"] and time.time() < connect_deadline:
        time.sleep(0.05)

    if connection_state["error"]:
        print(f"ERROR: {connection_state['error']}")
        sys.exit(1)
    if not connection_state["connected"]:
        print("ERROR: Timed out waiting for session connection")
        sys.exit(1)

    print("✓ Connected to session as WebRTC participant")

    print("Staying connected for 5 seconds …")
    time.sleep(5)

    connector.disconnect()
    print("✓ Disconnected from session")
    print("\nTest C2 PASSED ✓")


if __name__ == "__main__":
    main()
