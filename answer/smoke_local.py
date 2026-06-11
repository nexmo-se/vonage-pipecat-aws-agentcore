#!/usr/bin/env python3
"""
Phase 1 local smoke test — answer/ orchestrator against deployed AgentCore runtime.

Prerequisites:
  1. answer/server.py running (port 8080)
  2. C1 ran once → VONAGE_SESSION_ID in root .env
  3. Playground joined existing session, mic published

Usage:
  python smoke_local.py              # nova_sonic (default)
  python smoke_local.py --mode echo
  python smoke_local.py --leave
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

BASE_URL = os.getenv("ANSWER_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
CONNECT_TIMEOUT = int(os.getenv("C6_WEBRTC_CONNECT_TIMEOUT_SECONDS", "30"))


def _request(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code} {path}: {detail}", file=sys.stderr)
        raise


def _session_id() -> str:
    sid = os.getenv("VONAGE_SESSION_ID", "").strip()
    if not sid:
        print("ERROR: VONAGE_SESSION_ID not set — run C1 first", file=sys.stderr)
        sys.exit(1)
    return sid


def _generate_vonage_token(session_id: str) -> str:
    """Mint agent publisher token locally (private.key) — same as C6 harness."""
    application_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    key_path = os.getenv("VONAGE_PRIVATE_KEY", "private.key").strip()
    private_key_file = Path(key_path)
    if not private_key_file.is_absolute():
        private_key_file = REPO_ROOT / key_path
    if not application_id or not private_key_file.exists():
        print(
            "WARN: cannot mint token locally — App Runner will generate token (needs VONAGE_PRIVATE_KEY_B64)",
            file=sys.stderr,
        )
        return ""

    from vonage import Auth, Vonage
    from vonage_video import TokenOptions

    client = Vonage(Auth(application_id=application_id, private_key=str(private_key_file)))
    token = client.video.generate_client_token(
        TokenOptions(session_id=session_id, role="publisher")
    )
    return token.decode("utf-8") if isinstance(token, bytes) else str(token)


def cmd_start(mode: str) -> int:
    session_id = _session_id()
    token = _generate_vonage_token(session_id)
    payload: dict[str, str] = {"session_id": session_id, "mode": mode}
    if token:
        payload["token"] = token
        print(f"  token: minted locally ({len(token)} chars)")
    else:
        print("  token: not set — App Runner must generate (needs VONAGE_PRIVATE_KEY_B64)")
    print(f"POST /start-agent  session={session_id[:24]}…  mode={mode}")
    result = _request("POST", "/start-agent", payload)
    print(json.dumps(result, indent=2))

    runtime_session_id = result.get("runtime_session_id")
    print(f"\nWaiting up to {CONNECT_TIMEOUT}s for connected: true …")
    deadline = time.time() + CONNECT_TIMEOUT
    while time.time() < deadline:
        status = _request("GET", "/status")
        agentcore = status.get("agentcore") or {}
        if isinstance(agentcore, dict) and agentcore.get("connected"):
            print("\nStatus (connected):")
            print(json.dumps(status, indent=2))
            print("\nPhase 1 PASS — agent connected via answer/ orchestrator.")
            print("  Validate in Playground: agent participant visible + audio.")
            print(f"  runtime_session_id: {runtime_session_id}")
            print(f"  When done: ANSWER_BASE_URL={BASE_URL} .venv/bin/python answer/smoke_local.py --leave")
            return 0
        time.sleep(2)

    status = _request("GET", "/status")
    print("\nFinal status:")
    print(json.dumps(status, indent=2))
    print("\nPhase 1 FAIL — not connected within timeout.")
    print("  Check Playground is on the same VONAGE_SESSION_ID with mic published.")
    return 1


def cmd_leave() -> int:
    try:
        result = _request("POST", "/leave")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print("No active session (already left).")
            return 0
        raise
    print(json.dumps(result, indent=2))
    print("\nLeave complete.")
    return 0


def cmd_health() -> int:
    result = _request("GET", "/")
    print(json.dumps(result, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="answer/ local smoke test")
    parser.add_argument("--mode", default="nova_sonic", choices=["nova_sonic", "echo"])
    parser.add_argument("--leave", action="store_true", help="POST /leave")
    parser.add_argument("--health", action="store_true", help="GET / health only")
    args = parser.parse_args()

    try:
        if args.health:
            sys.exit(cmd_health())
        if args.leave:
            sys.exit(cmd_leave())
        sys.exit(cmd_start(args.mode))
    except urllib.error.HTTPError:
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"ERROR: cannot reach {BASE_URL} — is the service running?\n  {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
