#!/usr/bin/env python3
"""
Test C4a: AWS Bedrock — Credentials + Nova Lite Text Conversation

Verifies:
  1. AWS credentials are correctly configured
  2. Bedrock API access (ListFoundationModels)
  3. Nova Lite text inference with a simple prompt

Platform: Any (macOS, Linux, Windows)
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _find_env() -> Path:
    """Locate .env: check /workspace (Docker mount), then walk up from script."""
    docker_env = Path("/workspace/.env")
    if docker_env.exists():
        return docker_env
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
    return Path(".env")


load_dotenv(_find_env())

# Nova Lite for quick credential/access testing
NOVA_LITE_MODEL_ID = "amazon.nova-lite-v1:0"
TEST_PROMPT = "Say hello in exactly one sentence."


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _extract_reply_text(result: dict) -> str:
    content = result.get("output", {}).get("message", {}).get("content", [])
    if isinstance(content, list):
        for item in content:
            text = item.get("text") if isinstance(item, dict) else None
            if text:
                return text
    fallback_text = result.get("outputText")
    if isinstance(fallback_text, str) and fallback_text.strip():
        return fallback_text
    raise ValueError(f"Unexpected Bedrock response format: {result}")


def main() -> None:
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    aws_session_token = os.getenv("AWS_SESSION_TOKEN", "").strip()
    aws_region = os.getenv("AWS_REGION", "us-east-1").strip()
    aws_profile = os.getenv("AWS_PROFILE", os.getenv("AWS_DEFAULT_PROFILE", "")).strip()
    bedrock_connect_timeout_seconds = _env_int("BEDROCK_CONNECT_TIMEOUT_SECONDS", 10)
    bedrock_read_timeout_seconds = _env_int("BEDROCK_READ_TIMEOUT_SECONDS", 60)
    bedrock_max_attempts = _env_int("BEDROCK_MAX_ATTEMPTS", 4)

    # ── Resolve credential source ─────────────────────────────────
    has_explicit_env_creds = bool(aws_access_key and aws_secret_key)
    if aws_profile:
        print(f"✓ Using AWS profile: {aws_profile} (region: {aws_region})")
    elif has_explicit_env_creds:
        print(f"✓ Using AWS key/secret from env (region: {aws_region})")
    else:
        print(f"✓ Using boto3 default credential chain (region: {aws_region})")

    # ── Initialise Bedrock client ─────────────────────────────────
    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("  Run: pip install -r requirements.txt")
        sys.exit(1)

    try:
        if aws_profile:
            session = boto3.Session(profile_name=aws_profile, region_name=aws_region)
        elif has_explicit_env_creds:
            session = boto3.Session(
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                aws_session_token=aws_session_token or None,
                region_name=aws_region,
            )
        else:
            session = boto3.Session(region_name=aws_region)

        client_config = Config(
            retries={"max_attempts": max(1, bedrock_max_attempts), "mode": "standard"},
            connect_timeout=max(1, bedrock_connect_timeout_seconds),
            read_timeout=max(1, bedrock_read_timeout_seconds),
            user_agent_extra="vonage-pipecat-aws-agentcore-tests/c4a-bedrock",
        )

        bedrock = session.client("bedrock", config=client_config)
        bedrock_runtime = session.client("bedrock-runtime", config=client_config)
    except (NoCredentialsError, ProfileNotFound):
        print("ERROR: AWS credentials are invalid or missing")
        sys.exit(1)

    print("✓ Bedrock client initialised")

    # ── Verify model access ───────────────────────────────────────
    try:
        response = bedrock.list_foundation_models(byOutputModality="TEXT")
        model_ids = [m["modelId"] for m in response.get("modelSummaries", [])]
        if NOVA_LITE_MODEL_ID not in model_ids:
            print(
                f"WARNING: {NOVA_LITE_MODEL_ID} not found in listed models.\n"
                "  Enable model access in the Bedrock console:\n"
                "  https://console.aws.amazon.com/bedrock/home#/modelaccess"
            )
        else:
            print(f"✓ Model access verified: {NOVA_LITE_MODEL_ID}")
    except ClientError as e:
        print(f"ERROR listing models: {e}")
        sys.exit(1)

    # ── Run a simple text inference ───────────────────────────────
    print(f'\nSending test prompt: "{TEST_PROMPT}"')

    request_body = {
        "messages": [
            {
                "role": "user",
                "content": [{"text": TEST_PROMPT}],
            }
        ],
        "inferenceConfig": {
            "maxTokens": 100,
            "temperature": 0.5,
        },
    }

    try:
        response = bedrock_runtime.invoke_model(
            modelId=NOVA_LITE_MODEL_ID,
            body=json.dumps(request_body),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        reply = _extract_reply_text(result)
        print(f"✓ Response received:\n  {reply}")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "AccessDeniedException":
            print(
                f"ERROR: Access denied to model {NOVA_LITE_MODEL_ID}.\n"
                "  Enable model access in the Bedrock console."
            )
        else:
            print(f"ERROR calling Bedrock: {e}")
        sys.exit(1)

    print("\nTest C4a PASSED ✓")


if __name__ == "__main__":
    main()
