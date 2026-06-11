#!/usr/bin/env python3
"""
Test C1: Vonage Video API — Session Creation

Verifies:
  1. Authentication with VONAGE_APPLICATION_ID + VONAGE_PRIVATE_KEY
  2. Video session creation via the Vonage Video REST API (always creates a new session)
  3. Client token generation (publisher role)
  4. Updates VONAGE_SESSION_ID in root .env and prints Playground credentials

Platform: Any (macOS, Linux, Windows)
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"

# Load .env from the repo root (two levels up from this file)
load_dotenv(ENV_FILE)


def resolve_private_key_path(private_key_path: str) -> Path:
    private_key_file = Path(private_key_path).expanduser()
    if not private_key_file.is_absolute():
        private_key_file = REPO_ROOT / private_key_path
    return private_key_file


def load_vonage_bootstrap_config() -> tuple[str, Path]:
    application_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    private_key_path = os.getenv("VONAGE_PRIVATE_KEY", "private.key").strip()

    if not application_id:
        print("ERROR: VONAGE_APPLICATION_ID is not set in .env")
        sys.exit(1)

    private_key_file = resolve_private_key_path(private_key_path)
    if not private_key_file.exists():
        print(f"ERROR: Private key file not found: {private_key_file}")
        print("  Download your application's private.key from the Vonage Dashboard")
        sys.exit(1)

    return application_id, private_key_file


def _persist_env_var(key: str, value: str) -> None:
    if not ENV_FILE.exists():
        return

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    assignment = f'{key}="{value}"' if key == "VONAGE_PUBLISHER_TOKEN" else f"{key}={value}"
    replaced = False
    for idx, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[idx] = assignment
            replaced = True
            break

    if not replaced:
        lines.append(assignment)

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def persist_session_id_to_env(session_id: str) -> None:
    _persist_env_var("VONAGE_SESSION_ID", session_id)
    print(f"✓ Saved VONAGE_SESSION_ID to {ENV_FILE}")


def persist_publisher_token_to_env(token: str) -> None:
    _persist_env_var("VONAGE_PUBLISHER_TOKEN", token)
    print(f"✓ Saved VONAGE_PUBLISHER_TOKEN to {ENV_FILE}")


def playground_url(application_id: str, session_id: str, token: str) -> str:
    from urllib.parse import quote

    return (
        "https://tokbox.com/developer/tools/playground/"
        f"?apiKey={quote(application_id, safe='')}"
        f"&sessionId={quote(session_id, safe='')}"
        f"&token={quote(token, safe='')}"
    )


def create_vonage_client(application_id: str, private_key_file: Path):
    try:
        from vonage import Auth, Vonage
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("  Run: pip install -r requirements.txt")
        sys.exit(1)

    return Vonage(
        Auth(
            application_id=application_id,
            private_key=str(private_key_file),
        )
    )


def create_session_id(client) -> str:
    try:
        from vonage_video import SessionOptions
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("  Run: pip install -r requirements.txt")
        sys.exit(1)

    previous_session_id = os.getenv("VONAGE_SESSION_ID", "").strip()
    if previous_session_id:
        print(f"Replacing existing VONAGE_SESSION_ID: {previous_session_id}")

    print("Creating new Vonage Video session …")
    session = client.video.create_session(SessionOptions(media_mode="routed"))
    session_id = session.session_id
    print(f"✓ Created session: {session_id}")
    persist_session_id_to_env(session_id)
    print(f"  ➜ Updated VONAGE_SESSION_ID={session_id} in your .env file\n")
    return session_id


def generate_publisher_token(client, session_id: str, expire_time: int = 86400) -> str:
    try:
        from vonage_video import TokenOptions
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("  Run: pip install -r requirements.txt")
        sys.exit(1)

    token = client.video.generate_client_token(
        TokenOptions(
            session_id=session_id,
            role="publisher",
        )
    )
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    print(f"✓ Generated client token (publisher, {expire_time // 3600} h)")
    return token


def main() -> None:
    application_id, private_key_file = load_vonage_bootstrap_config()
    client = create_vonage_client(application_id, private_key_file)
    session_id = create_session_id(client)
    token = generate_publisher_token(client, session_id)
    persist_publisher_token_to_env(token)

    separator = "=" * 60
    print(f"\n{separator}")
    print("Playground (https://tokbox.com/developer/tools/playground/)")
    print(separator)
    print("1. Choose  Join existing session  (NOT Create new session)")
    print(f"2. Session ID: {session_id}")
    print(f"   (same value as VONAGE_SESSION_ID in root .env)")
    print(f"3. API Key (if asked): {application_id}")
    print("4. Connect → Publish (mic on)")
    print("5. Then run C6 (--stage echo|full) or answer/smoke_local.py to start the agent")
    print(separator)
    print("\nTest C1 PASSED ✓")


if __name__ == "__main__":
    main()
