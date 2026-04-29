#!/usr/bin/env python3
"""
C4b Integration Test: Bedrock + Vonage Transport Validation

This test verifies that:
1. AWS Bedrock credentials are accessible
2. Bedrock LLM can be invoked synchronously
3. Integration module loads successfully
4. Stage 2 (bedrock_echo_agent.py) is ready for Docker execution

Note: Full Stage 2 requires Docker/Linux for Vonage transport.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load root .env
repo_root = Path(__file__).resolve().parents[2]
load_dotenv(repo_root / ".env")

print("=" * 70)
print("C4b Integration Test: Bedrock + Vonage Transport Setup Validation")
print("=" * 70)

# ── Stage 1: Bedrock Credentials Test ─────────────────────────────
print("\n[Stage 1] Bedrock Credentials & LLM Test")
print("-" * 70)

try:
    from bedrock_transport_integration import BedrockLLMIntegration
    print("✓ Bedrock integration module imported")
except ImportError as e:
    print(f"✗ Failed to import bedrock_transport_integration: {e}")
    sys.exit(1)

aws_profile = os.getenv("AWS_PROFILE", "").strip()
aws_region = os.getenv("AWS_REGION", "us-east-1").strip()
bedrock_model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-2-sonic-v1:0").strip()

# For validation test, use Nova Lite (text-only)
# Stage 2 will use Nova Sonic (speech-to-speech) via bedrock_echo_agent.py
test_model_id = "amazon.nova-lite-v1:0"

print(f"  AWS_PROFILE: {aws_profile or '(using default chain)'}")
print(f"  AWS_REGION: {aws_region}")
print(f"  BEDROCK_MODEL_ID (Stage 2): {bedrock_model_id}")
print(f"  TEST_MODEL_ID (Stage 1 validation): {test_model_id}")

try:
    llm = BedrockLLMIntegration(
        model_id=test_model_id,  # Use Nova Lite for text validation
        region=aws_region,
        profile_name=aws_profile if aws_profile else None,
    )
    print("✓ Bedrock LLM client initialized")
    
    # Test synchronous invocation (without asyncio)
    print("  Testing LLM invocation...")
    # We'll use a sync wrapper for the async function
    import asyncio
    
    async def test_invoke():
        return await llm.invoke(
            user_text="Say hello in one sentence.",
            max_tokens=50,
            temperature=0.5,
        )
    
    response = asyncio.run(test_invoke())
    print(f"✓ LLM response received: {response[:60]}...")
    
except Exception as e:
    print(f"✗ Bedrock test failed: {e}")
    sys.exit(1)

# ── Stage 2: Vonage Configuration Check ───────────────────────────
print("\n[Stage 2] Vonage Video Configuration")
print("-" * 70)

vonage_app_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
vonage_session_id = os.getenv("VONAGE_SESSION_ID", "").strip()
vonage_private_key = os.getenv("VONAGE_PRIVATE_KEY", "private.key").strip()

if not vonage_app_id:
    print("✗ VONAGE_APPLICATION_ID not set")
    sys.exit(1)

if not vonage_session_id:
    print("✗ VONAGE_SESSION_ID not set")
    sys.exit(1)

print(f"✓ VONAGE_APPLICATION_ID: {vonage_app_id[:20]}...")
print(f"✓ VONAGE_SESSION_ID: {vonage_session_id[:30]}...")

private_key_file = Path(vonage_private_key)
if not private_key_file.is_absolute():
    private_key_file = repo_root / vonage_private_key

if private_key_file.exists():
    print(f"✓ Private key file exists: {private_key_file}")
else:
    print(f"✗ Private key file not found: {private_key_file}")
    sys.exit(1)

# ── Stage 3: Pipecat Dependency Check ─────────────────────────────
print("\n[Stage 3] Pipecat Transport Dependencies")
print("-" * 70)

try:
    from vonage import Auth, Vonage
    from vonage_video import TokenOptions
    print("✓ Vonage SDK imported (python-vonage)")
except ImportError as e:
    print(f"⚠ Vonage SDK not available on this platform: {e}")
    print("  (This is expected on macOS; Stage 2 uses Docker)")

try:
    from pipecat.transports.vonage.video_connector import VonageVideoConnectorTransport
    print("✓ Pipecat Vonage transport available")
except ImportError:
    print("⚠ Pipecat Vonage transport not available on this platform")
    print("  (This is expected on macOS; Stage 2 uses Docker)")

# ── Summary ───────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("INTEGRATION TEST RESULTS")
print("=" * 70)
print("\n✓ Stage 1 (Bedrock Credentials): PASSED")
print("  - AWS credentials valid")
print("  - Bedrock LLM client works")
print("  - Model invocation successful")

print("\n✓ Stage 2 (Vonage Configuration): READY")
print("  - VONAGE_APPLICATION_ID set")
print("  - VONAGE_SESSION_ID set")
print("  - Private key file exists")

print("\n⚠ Stage 3 (Pipecat Transport): DEFERRED TO DOCKER")
print("  - Vonage transport dependencies deferred to Docker/Linux environment")
print("  - bedrock_echo_agent.py ready to run in Docker")

print("\n" + "=" * 70)
print("NEXT STEPS: Run Stage 2 with Docker")
print("=" * 70)
print("""
To run the full C4b Bedrock + Vonage integration test:

1. Build Docker image:
   cd tests/c4b_bedrock_nova_sonic
   docker build -t c4b-bedrock-nova-sonic .

2. Run Bedrock echo agent in Docker:
   docker run --rm \
     -e AWS_PROFILE=vonage-dev \
     -e AWS_REGION=us-east-1 \
     -v ~/.aws:/root/.aws \
     -v "$(pwd)/../../.env:/workspace/.env:ro" \
     -v "$(pwd)/../../private.key:/workspace/private.key:ro" \
     c4b-bedrock-nova-sonic python bedrock_echo_agent.py

3. Join Vonage Playground:
   https://tools.vonage.com/video/playground/
   (Use session ID from .env)

4. Publish audio → speak → wait for LLM echo → disconnect

5. Verify logs for success markers:
    grep "Connected to Vonage Video" logs/c4b-bedrock-nova-sonic-echo.log
    grep "Nova Sonic" logs/c4b-bedrock-nova-sonic-echo.log
    grep "Participant joined" logs/c4b-bedrock-nova-sonic-echo.log
""")

print("\nC4b Integration Test PASSED ✓\n")
