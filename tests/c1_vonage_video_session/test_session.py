#!/usr/bin/env python3
"""
Test C1: Vonage Video API — Session Creation

Verifies:
  1. Authentication with VONAGE_APPLICATION_ID + VONAGE_PRIVATE_KEY
  2. Video session creation via the Vonage Video REST API
  3. Client token generation (publisher role)
  4. Prints credentials to enter manually in the Vonage Playground

Platform: Any (macOS, Linux, Windows)
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
SESSION_PLACEHOLDERS = {
    "",
    "your-vonage-session-id",
    "<your-vonage-session-id>",
}

# Load .env from the repo root (two levels up from this file)
load_dotenv(ENV_FILE)


def resolve_private_key_path(private_key_path: str) -> Path:
    private_key_file = Path(private_key_path).expanduser()
    if not private_key_file.is_absolute():
        private_key_file = REPO_ROOT / private_key_path
    return private_key_file


def load_vonage_bootstrap_config() -> tuple[str, Path, str]:
    application_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    private_key_path = os.getenv("VONAGE_PRIVATE_KEY", "private.key").strip()
    session_id = os.getenv("VONAGE_SESSION_ID", "").strip()

    if not application_id:
        print("ERROR: VONAGE_APPLICATION_ID is not set in .env")
        sys.exit(1)

    private_key_file = resolve_private_key_path(private_key_path)
    if not private_key_file.exists():
        print(f"ERROR: Private key file not found: {private_key_file}")
        print("  Download your application's private.key from the Vonage Dashboard")
        sys.exit(1)

    return application_id, private_key_file, session_id


def is_missing_session_id(session_id: str) -> bool:
    return session_id.strip().lower() in SESSION_PLACEHOLDERS


def persist_session_id_to_env(session_id: str) -> None:
    if not ENV_FILE.exists():
        return

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    replaced = False
    for idx, line in enumerate(lines):
        if line.strip().startswith("VONAGE_SESSION_ID="):
            lines[idx] = f"VONAGE_SESSION_ID={session_id}"
            replaced = True
            break

    if not replaced:
        lines.append(f"VONAGE_SESSION_ID={session_id}")

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✓ Saved VONAGE_SESSION_ID to {ENV_FILE}")


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


def get_or_create_session_id(client, session_id: str) -> str:
    try:
        from vonage_video import SessionOptions
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("  Run: pip install -r requirements.txt")
        sys.exit(1)

    if not is_missing_session_id(session_id):
        print(f"✓ Using existing session: {session_id}")
        return session_id

    print("Creating new Vonage Video session …")
    session = client.video.create_session(SessionOptions(media_mode="routed"))
    session_id = session.session_id
    print(f"✓ Created session: {session_id}")
    persist_session_id_to_env(session_id)
    print(f"  ➜ Added VONAGE_SESSION_ID={session_id} to your .env file\n")
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
    application_id, private_key_file, session_id = load_vonage_bootstrap_config()
    client = create_vonage_client(application_id, private_key_file)
    session_id = get_or_create_session_id(client, session_id)
    token = generate_publisher_token(client, session_id)

    separator = "=" * 60
    print(f"\n{separator}")
    print("Vonage Playground credentials (https://tokbox.com/developer/tools/playground/)")
    print(separator)
    print(f"API Key:    {application_id}")
    print(f"Session ID: {session_id}")
    print(f"Token:      {token}")
    print(separator)
    print("\nTest C1 PASSED ✓")


if __name__ == "__main__":
    main()
