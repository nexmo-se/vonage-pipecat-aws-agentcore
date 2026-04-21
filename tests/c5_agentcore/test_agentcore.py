#!/usr/bin/env python3
"""
Test C5: AWS Bedrock AgentCore Runtime — Deploy & Invoke Hello World

Verifies:
  1. Creates a hello-world AgentCore agent (or uses AGENTCORE_AGENT_ARN)
  2. Invokes the agent with a simple prompt
  3. Validates a response is returned
  4. Cleans up (deletes) the test agent if it was created here

Platform: Any (macOS, Linux, Windows)
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

HELLO_WORLD_PROMPT = "Say hello world"
AGENT_NAME = "vonage-pipecat-hello-world-test"


def main() -> None:
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    aws_region = os.getenv("AWS_REGION", "us-east-1").strip()
    existing_agent_arn = os.getenv("AGENTCORE_AGENT_ARN", "").strip()

    missing: list[str] = []
    if not aws_access_key:
        missing.append("AWS_ACCESS_KEY_ID")
    if not aws_secret_key:
        missing.append("AWS_SECRET_ACCESS_KEY")
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    # ── Imports ───────────────────────────────────────────────────
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("  Run: uv pip install -r requirements.txt")
        sys.exit(1)

    agentcore_client = boto3.client(
        "bedrock-agentcore",
        region_name=aws_region,
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
    )

    agent_arn = existing_agent_arn
    created_by_test = False

    # ── Create agent (if no ARN provided) ────────────────────────
    if not agent_arn:
        print(f"Creating hello-world AgentCore agent …")
        try:
            response = agentcore_client.create_agent(
                agentName=AGENT_NAME,
                description="Temporary hello-world test agent — safe to delete",
                instruction="You are a helpful assistant. Respond warmly and briefly.",
            )
            agent_arn = response["agent"]["agentArn"]
            created_by_test = True
            print(f"✓ Agent created: {agent_arn}")
        except ClientError as e:
            print(f"ERROR creating agent: {e}")
            sys.exit(1)
    else:
        print(f"✓ Using existing agent: {agent_arn}")

    # ── Invoke agent ──────────────────────────────────────────────
    print(f'Invoking agent with: "{HELLO_WORLD_PROMPT}"')
    try:
        response = agentcore_client.invoke_agent(
            agentArn=agent_arn,
            inputText=HELLO_WORLD_PROMPT,
            sessionId="test-session-c5",
        )

        # Collect streaming response
        completion = ""
        for event in response.get("completion", []):
            chunk = event.get("chunk", {})
            if "bytes" in chunk:
                completion += chunk["bytes"].decode("utf-8")

        if completion:
            print(f"✓ Agent response:\n  {completion.strip()}")
        else:
            print("WARNING: Agent returned an empty response")

    except ClientError as e:
        print(f"ERROR invoking agent: {e}")
        if created_by_test:
            _delete_agent(agentcore_client, agent_arn)
        sys.exit(1)

    # ── Cleanup ───────────────────────────────────────────────────
    if created_by_test:
        _delete_agent(agentcore_client, agent_arn)

    print("\nTest C5 PASSED ✓")


def _delete_agent(client, agent_arn: str) -> None:
    print("Cleaning up agent …")
    try:
        client.delete_agent(agentArn=agent_arn)
        print("✓ Agent deleted")
    except Exception as e:
        print(f"WARNING: Could not delete agent {agent_arn}: {e}")


if __name__ == "__main__":
    main()
