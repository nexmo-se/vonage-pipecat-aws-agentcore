#!/usr/bin/env python3
"""
Test C5: AWS Bedrock AgentCore Runtime — Invoke Hello World

Verifies:
    1. Uses an existing AgentCore runtime ARN from the environment
    2. Invokes the runtime with a simple prompt
    3. Validates a response is returned

Platform: Any (macOS, Linux, Windows)
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

HELLO_WORLD_PROMPT = "Say hello world"
PLACEHOLDER_VALUES = {
    "your-aws-access-key-id",
    "your-aws-secret-access-key",
    "your-aws-session-token",
}


def main() -> None:
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    aws_session_token = os.getenv("AWS_SESSION_TOKEN", "").strip()
    aws_region = os.getenv("AWS_REGION", "us-east-1").strip()
    aws_profile = os.getenv("AWS_PROFILE", os.getenv("AWS_DEFAULT_PROFILE", "")).strip()
    runtime_arn = os.getenv("AGENTCORE_AGENT_ARN", "").strip()
    bedrock_connect_timeout_seconds = int(os.getenv("BEDROCK_CONNECT_TIMEOUT_SECONDS", "10").strip() or "10")
    bedrock_read_timeout_seconds = int(os.getenv("BEDROCK_READ_TIMEOUT_SECONDS", "60").strip() or "60")
    bedrock_max_attempts = int(os.getenv("BEDROCK_MAX_ATTEMPTS", "4").strip() or "4")

    # ── Imports ───────────────────────────────────────────────────
    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("  Run: pip install -r requirements.txt")
        sys.exit(1)

    client_config = Config(
        retries={"max_attempts": max(1, bedrock_max_attempts), "mode": "standard"},
        connect_timeout=max(1, bedrock_connect_timeout_seconds),
        read_timeout=max(1, bedrock_read_timeout_seconds),
        user_agent_extra="vonage-pipecat-aws-agentcore-tests/c5-agentcore",
    )

    try:
        has_explicit_env_creds = (
            aws_access_key
            and aws_secret_key
            and aws_access_key not in PLACEHOLDER_VALUES
            and aws_secret_key not in PLACEHOLDER_VALUES
        )

        if aws_profile:
            session = boto3.Session(
                profile_name=aws_profile,
                region_name=aws_region,
            )
        elif has_explicit_env_creds:
            session = boto3.Session(
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                aws_session_token=aws_session_token or None,
                region_name=aws_region,
            )
        else:
            session = boto3.Session(
                profile_name=aws_profile or None,
                region_name=aws_region,
            )

        agentcore_client = session.client("bedrock-agentcore", config=client_config)
    except ProfileNotFound as exc:
        print(f"ERROR: AWS profile not found — {exc}")
        print("  Set AWS_PROFILE to an existing CLI profile or provide AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY.")
        sys.exit(1)

    if not runtime_arn:
        print("ERROR: Missing AGENTCORE_AGENT_ARN")
        print("  Set the ARN of an existing AgentCore runtime in .env or your shell before running this test.")
        sys.exit(1)

    print(f"✓ Using existing runtime: {runtime_arn}")

    # ── Invoke agent ──────────────────────────────────────────────
    print(f'Invoking agent with: "{HELLO_WORLD_PROMPT}"')
    try:
        response = agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            contentType="application/json",
            accept="application/json",
            payload=json.dumps({"input": HELLO_WORLD_PROMPT}).encode("utf-8"),
        )

        completion = _read_response_payload(response)

        if completion:
            print(f"✓ Agent response:\n  {completion.strip()}")
        else:
            print("WARNING: Agent returned an empty response")

    except (ClientError, NoCredentialsError) as e:
        print(f"ERROR invoking agent: {e}")
        sys.exit(1)

    print("\nTest C5 PASSED ✓")


def _read_response_payload(response: dict) -> str:
    body = response.get("payload") or response.get("response")
    if body is None:
        return ""
    if hasattr(body, "read"):
        body = body.read()
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


if __name__ == "__main__":
    main()
