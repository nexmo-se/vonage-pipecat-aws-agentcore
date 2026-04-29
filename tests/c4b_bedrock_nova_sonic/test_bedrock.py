#!/usr/bin/env python3
"""
Test C4b: AWS Bedrock — Credentials + Nova Lite Text Conversation

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

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Nova Lite for quick credential/access testing
NOVA_LITE_MODEL_ID = "amazon.nova-lite-v1:0"
TEST_PROMPT = "Say hello in exactly one sentence."


def main() -> None:
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    aws_session_token = os.getenv("AWS_SESSION_TOKEN", "").strip()
    aws_region = os.getenv("AWS_REGION", "us-east-1").strip()
    aws_profile = os.getenv("AWS_PROFILE", os.getenv("AWS_DEFAULT_PROFILE", "")).strip()

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

        bedrock = session.client("bedrock")
        bedrock_runtime = session.client("bedrock-runtime")
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
        reply = result["output"]["message"]["content"][0]["text"]
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

    print("\nTest C4b PASSED ✓")


if __name__ == "__main__":
    main()
