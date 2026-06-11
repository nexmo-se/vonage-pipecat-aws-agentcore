#!/usr/bin/env python3
"""
C6 staged invoke runner — Stages 2–5 against a deployed AgentCore runtime.

Usage:
  python test_agentcore_video.py --stage network
  python test_agentcore_video.py --stage echo
  python test_agentcore_video.py --stage full
  python test_agentcore_video.py --stage status

Requires AGENTCORE_RUNTIME_ARN (after runtime/ deploy) in root .env.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from vonage_env import REPO_ROOT, resolve_private_key_path

load_dotenv(REPO_ROOT / ".env")

STOP_DECISIONS = {
    "fail_imports",
    "fail_https",
}


def _generate_vonage_token(session_id: str) -> str:
    application_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    private_key_file = resolve_private_key_path()
    if not application_id or not private_key_file.exists():
        raise ValueError("VONAGE_APPLICATION_ID and VONAGE_PRIVATE_KEY required to generate token")

    from vonage import Auth, Vonage
    from vonage_video import TokenOptions

    client = Vonage(Auth(application_id=application_id, private_key=str(private_key_file)))
    token = client.video.generate_client_token(
        TokenOptions(session_id=session_id, role="publisher")
    )
    return token.decode("utf-8") if isinstance(token, bytes) else str(token)


def _test_session_credentials() -> tuple[str, str]:
    """C6 test harness: session_id from env/shell; token generated per invoke."""
    session_id = os.getenv("VONAGE_SESSION_ID", "").strip()
    if not session_id:
        raise ValueError(
            "VONAGE_SESSION_ID not set — export in shell for C6 Stages 3–5 only "
            "(production passes session_id + token via invoke payload/context)"
        )
    token = _generate_vonage_token(session_id)
    return session_id, token


def _runtime_arn() -> str:
    return (
        os.getenv("AGENTCORE_RUNTIME_ARN", "").strip()
        or os.getenv("C6_AGENTCORE_RUNTIME_ARN", "").strip()
        or os.getenv("AGENTCORE_AGENT_ARN", "").strip()
    )


def _format_michael_report(result: dict[str, Any], runtime_arn: str) -> str:
    decision = result.get("decision", "unknown")
    passed = decision.startswith("pass")
    stopped = decision in STOP_DECISIONS

    if decision in {"pass_vonage_sdk", "pass_vonage_turn"}:
        verdict = "VIABLE — imports + HTTPS OK; Vonage SDK handles dynamic TURN at join"
        next_step = "Proceed C6 Stage 3 echo (authoritative WebRTC gate)."
    elif passed:
        verdict = "VIABLE — TURN relay confirmed inside AgentCore Runtime"
        next_step = "Proceed C6 Stages 3–5, then scaffold runtime/ + answer/."
    elif stopped:
        verdict = f"NOT VIABLE — Stage 2 failed ({decision})"
        next_step = "Fix blocker or report to Michael; ECS/Fargate fallback if unrecoverable."
    else:
        verdict = "PARTIAL — review probe details before committing to AgentCore hosting"
        next_step = "Run Stage 3 echo test; document constraints for Michael before production."

    lines = [
        "=" * 72,
        "C6 Stage 2 Report — VonageVideoConnectorTransport + TURN in AgentCore",
        "=" * 72,
        f"Runtime ARN:      {runtime_arn}",
        f"Decision:         {decision}",
        f"Verdict:          {verdict}",
        "",
        "Probe summary:",
        f"  imports_ok:           {result.get('imports_ok')}",
        f"  https_vonage_ok:      {result.get('https_vonage_ok')}",
        f"  vonage_media_probe_ok: {result.get('vonage_media_probe_ok')}",
        f"  stun_only_ok:          {result.get('stun_only_ok')} (informational — expected false)",
        "",
        f"Recommendation: {result.get('recommendation', '')}",
        f"Next step:      {next_step}",
        "=" * 72,
    ]
    return "\n".join(lines)


def _read_payload(response: dict[str, Any]) -> Any:
    body = response.get("payload") or response.get("response")
    if body is None:
        return None
    if hasattr(body, "read"):
        body = body.read()
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body
    return body


def _invoke(
    client: Any,
    runtime_arn: str,
    payload: dict[str, Any],
    *,
    runtime_session_id: str | None = None,
) -> Any:
    kwargs: dict[str, Any] = {
        "agentRuntimeArn": runtime_arn,
        "contentType": "application/json",
        "accept": "application/json",
        "payload": json.dumps(payload).encode("utf-8"),
    }
    if runtime_session_id:
        kwargs["runtimeSessionId"] = runtime_session_id
    response = client.invoke_agent_runtime(**kwargs)
    return _read_payload(response)


def _create_client() -> tuple[Any, str]:
    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import NoCredentialsError, ProfileNotFound
    except ImportError as exc:
        print(f"ERROR: missing dependency — {exc}")
        sys.exit(1)

    aws_region = os.getenv("AWS_REGION", "us-east-1").strip()
    aws_profile = os.getenv("AWS_PROFILE", os.getenv("AWS_DEFAULT_PROFILE", "")).strip()
    runtime_arn = _runtime_arn()
    if not runtime_arn:
        print("ERROR: AGENTCORE_RUNTIME_ARN not set — copy ARN from agentcore deploy output")
        print("  Deploy agentcore_video_agent.py first, then set the runtime ARN in .env")
        sys.exit(1)

    config = Config(
        retries={"max_attempts": 4, "mode": "standard"},
        connect_timeout=10,
        read_timeout=120,
        user_agent_extra="vonage-pipecat-aws-agentcore-tests/c6",
    )

    try:
        session = boto3.Session(profile_name=aws_profile or None, region_name=aws_region)
        client = session.client("bedrock-agentcore", config=config)
    except ProfileNotFound as exc:
        print(f"ERROR: AWS profile not found — {exc}")
        sys.exit(1)
    except NoCredentialsError as exc:
        print(f"ERROR: AWS credentials not found — {exc}")
        sys.exit(1)

    return client, runtime_arn


def _print_json(label: str, data: Any) -> None:
    print(f"\n{label}:")
    print(json.dumps(data, indent=2) if isinstance(data, (dict, list)) else data)


def run_stage_network(client: Any, runtime_arn: str, *, report: bool = False) -> int:
    print("C6 Stage 2 — network probe via AgentCore runtime")
    result = _invoke(client, runtime_arn, {"action": "network_probe"})
    _print_json("Network probe result", result)

    if not isinstance(result, dict):
        print("ERROR: unexpected response type")
        return 1

    decision = result.get("decision", "")
    recommendation = result.get("recommendation", "")
    print(f"\nDecision: {decision}")
    print(f"Recommendation: {recommendation}")

    if report:
        print("\n" + _format_michael_report(result, runtime_arn))

    if decision in STOP_DECISIONS:
        print("\nC6 Stage 2 STOP — see --report output for Michael-ready summary.")
        return 1
    if str(decision).startswith("pass"):
        print("\nC6 Stage 2 PASS — proceed to Stage 3 echo test.")
        return 0
    print("\nC6 Stage 2 PARTIAL — review recommendation before continuing.")
    return 2


def run_stage_echo(client: Any, runtime_arn: str) -> int:
    try:
        session_id, token = _test_session_credentials()
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"C6 Stage 3 — echo pipeline join for session {session_id}")
    runtime_session_id = str(uuid.uuid4())
    print(f"Using runtimeSessionId: {runtime_session_id}")
    result = _invoke(
        client,
        runtime_arn,
        {
            "action": "join",
            "session_id": session_id,
            "token": token,
            "mode": "echo",
        },
        runtime_session_id=runtime_session_id,
    )
    _print_json("Join response", result)

    if isinstance(result, dict) and result.get("error"):
        print(f"ERROR: {result['error']}")
        return 1

    timeout = int(os.getenv("C6_WEBRTC_CONNECT_TIMEOUT_SECONDS", "30"))
    print(f"\nWaiting up to {timeout}s for WebRTC connect (poll /status)…")
    deadline = time.time() + timeout
    connected = False
    while time.time() < deadline:
        status = _invoke(
            client,
            runtime_arn,
            {"action": "status"},
            runtime_session_id=runtime_session_id,
        )
        if isinstance(status, dict) and status.get("connected"):
            connected = True
            _print_json("Status", status)
            break
        time.sleep(2)

    if not connected:
        status = _invoke(
            client,
            runtime_arn,
            {"action": "status"},
            runtime_session_id=runtime_session_id,
        )
        _print_json("Final status", status)
        print("\nC6 Stage 3 FAIL — agent did not connect within timeout.")
        print("  Validate manually in Vonage Playground; check CloudWatch logs.")
        return 1

    print("\nC6 Stage 3 connected — validate audio echo in Vonage Playground NOW:")
    print(f"  1. Open https://tokbox.com/developer/tools/playground/")
    print(f"  2. Join existing session (NOT create new): {session_id}")
    print("  3. Enable microphone (Publish) — allow browser mic permission")
    print("  4. Speak — your voice should echo back within 1–2 seconds")
    print(f"  5. runtimeSessionId (for leave): {runtime_session_id}")
    print("\n  Before --stage full or a new test: python test_agentcore_video.py --stage leave")
    print("  (Skipping leave leaves echo + nova agents in the same session.)")
    return 0


def run_stage_full(client: Any, runtime_arn: str) -> int:
    try:
        session_id, token = _test_session_credentials()
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"C6 Stage 5 — Nova Sonic pipeline join for session {session_id}")
    print(
        "\nIMPORTANT: Playground must use this EXACT session + a fresh token from C1.\n"
        "  If you ran C1 again after opening Playground, reconnect Playground first.\n"
        "  (C1 replaces VONAGE_SESSION_ID every run — mismatched sessions hide the agent.)\n"
    )
    runtime_session_id = str(uuid.uuid4())
    print(f"Using runtimeSessionId: {runtime_session_id}")
    result = _invoke(
        client,
        runtime_arn,
        {
            "action": "join",
            "session_id": session_id,
            "token": token,
            "mode": "nova_sonic",
        },
        runtime_session_id=runtime_session_id,
    )
    _print_json("Join response", result)

    if isinstance(result, dict) and result.get("error"):
        print(f"ERROR: {result['error']}")
        return 1

    timeout = int(os.getenv("C6_WEBRTC_CONNECT_TIMEOUT_SECONDS", "30"))
    print(f"\nWaiting up to {timeout}s for WebRTC connect (poll /status)…")
    deadline = time.time() + timeout
    connected = False
    while time.time() < deadline:
        status = _invoke(
            client,
            runtime_arn,
            {"action": "status"},
            runtime_session_id=runtime_session_id,
        )
        if isinstance(status, dict) and status.get("connected"):
            connected = True
            _print_json("Status", status)
            break
        time.sleep(2)

    if not connected:
        status = _invoke(
            client,
            runtime_arn,
            {"action": "status"},
            runtime_session_id=runtime_session_id,
        )
        _print_json("Final status", status)
        print("\nC6 Stage 5 FAIL — agent did not connect within timeout.")
        print(f"  Reconnect Playground to session: {session_id}")
        return 1

    print("\nC6 Stage 5 connected — validate Nova Sonic in Vonage Playground NOW:")
    print(f"  1. Playground → Join existing session: {session_id}")
    print("  2. Enable microphone (Publish)")
    print("  3. You should hear the nurse triage opening, then speak")
    print(f"  4. runtimeSessionId (for leave): {runtime_session_id}")
    print("\n  When done: python test_agentcore_video.py --stage leave")
    return 0


def run_stage_leave(client: Any, runtime_arn: str) -> int:
    result = _invoke(client, runtime_arn, {"action": "leave"})
    _print_json("Leave response", result)
    return 0


def run_stage_status(client: Any, runtime_arn: str) -> int:
    result = _invoke(client, runtime_arn, {"action": "status"})
    _print_json("Status", result)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="C6 AgentCore video transport staged tests")
    parser.add_argument(
        "--stage",
        choices=["network", "echo", "full", "leave", "status"],
        default="network",
        help="Test stage to run (default: network)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print Michael-ready Stage 2 summary (use with --stage network)",
    )
    args = parser.parse_args()

    client, runtime_arn = _create_client()
    print(f"✓ Using runtime: {runtime_arn}")

    stages = {
        "network": lambda c, a: run_stage_network(c, a, report=args.report),
        "echo": run_stage_echo,
        "full": run_stage_full,
        "leave": run_stage_leave,
        "status": run_stage_status,
    }
    exit_code = stages[args.stage](client, runtime_arn)
    if exit_code == 0 and args.stage in {"network", "echo", "full", "leave", "status"}:
        print(f"\nTest C6 stage '{args.stage}' completed ✓")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
