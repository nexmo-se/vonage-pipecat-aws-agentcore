"""Vonage env loading — same pattern as tests/c1–c4 (repo-root .env + private.key)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def find_repo_root(start: Path) -> Path:
    """Locate repo root via .env, Docker /workspace mount, or AgentCore /app."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".env").exists():
            return candidate

    workspace_root = Path("/workspace")
    if (workspace_root / ".env").exists():
        return workspace_root

    app_root = Path("/app")
    if app_root.exists() and (app_root / "agentcore_video_agent.py").exists():
        return app_root

    return current


REPO_ROOT = find_repo_root(Path(__file__).parent)
load_dotenv(REPO_ROOT / ".env")


def resolve_private_key_path(private_key_path: str | None = None) -> Path:
    """Resolve VONAGE_PRIVATE_KEY relative to repo root (matches c1/c3/c4)."""
    key_path = (private_key_path or os.getenv("VONAGE_PRIVATE_KEY", "private.key")).strip()
    private_key_file = Path(key_path).expanduser()
    if not private_key_file.is_absolute():
        private_key_file = REPO_ROOT / key_path
    return private_key_file


def load_vonage_credentials() -> tuple[str, Path]:
    """Return (application_id, private_key_file) from standard env vars."""
    application_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    private_key_file = resolve_private_key_path()
    return application_id, private_key_file
