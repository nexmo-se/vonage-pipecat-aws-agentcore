#!/usr/bin/env python3
"""
C6 Stage 0 — Pre-flight checks before AgentCore deploy.

Validates local tooling, AWS credentials, Vonage config, and that C6 scaffold
files are present. Run before `agentcore configure` / `agentcore deploy`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from vonage_env import REPO_ROOT, load_vonage_credentials, resolve_private_key_path

C6_DIR = Path(__file__).resolve().parent
load_dotenv(REPO_ROOT / ".env")

REQUIRED_FILES = (
    "vonage_env.py",
    "network_probe.py",
    "vonage_turn.py",
    "agentcore_video_agent.py",
    "Dockerfile",
    "requirements.txt",
    "test_agentcore_video.py",
)

PLACEHOLDER_VALUES = {
    "",
    "your-vonage-application-id",
    "your-vonage-session-id",
    "your-aws-access-key-id",
}


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "✓" if ok else "✗"
    line = f"{mark} {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main() -> None:
    print("=" * 70)
    print("C6 Stage 0 — Pre-flight Integration Check")
    print("=" * 70)

    all_ok = True

    print("\n[Scaffold files]")
    for filename in REQUIRED_FILES:
        path = C6_DIR / filename
        all_ok &= check(filename, path.exists(), str(path))

    print("\n[Environment]")
    application_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    session_id = os.getenv("VONAGE_SESSION_ID", "").strip()
    private_key_path = os.getenv("VONAGE_PRIVATE_KEY", "private.key").strip()
    runtime_arn = (
        os.getenv("AGENTCORE_RUNTIME_ARN", "").strip()
        or os.getenv("C6_AGENTCORE_RUNTIME_ARN", "").strip()
        or os.getenv("AGENTCORE_AGENT_ARN", "").strip()
    )
    aws_profile = os.getenv("AWS_PROFILE", "").strip()
    aws_region = os.getenv("AWS_REGION", "us-east-1").strip()
    all_ok &= check(
        "VONAGE_APPLICATION_ID",
        application_id not in PLACEHOLDER_VALUES,
        application_id or "missing",
    )
    check(
        "VONAGE_SESSION_ID",
        session_id not in PLACEHOLDER_VALUES,
        session_id or "not set (ok for Stage 0–2 — export in shell for Stage 3+ tests)",
    )

    private_key_file = resolve_private_key_path(private_key_path)
    all_ok &= check(
        "VONAGE_PRIVATE_KEY",
        private_key_file.exists(),
        str(private_key_file),
    )

    if runtime_arn:
        check("C6 runtime ARN", True, runtime_arn)
    else:
        check(
            "C6 runtime ARN",
            True,
            "not set (ok before deploy — set AGENTCORE_RUNTIME_ARN after agentcore deploy)",
        )

    print("\n[CLI tooling]")
    all_ok &= check("aws CLI", shutil.which("aws") is not None)
    all_ok &= check("docker CLI", shutil.which("docker") is not None)
    all_ok &= check("agentcore CLI", shutil.which("agentcore") is not None)

    if shutil.which("docker"):
        try:
            result = subprocess.run(
                ["docker", "buildx", "ls"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            arm64_ok = "linux/arm64" in result.stdout or result.returncode == 0
            all_ok &= check("docker buildx", arm64_ok, "needed for ARM64 AgentCore images")
        except Exception as exc:
            all_ok &= check("docker buildx", False, str(exc))

    print("\n[AWS credentials]")
    if aws_profile:
        check("AWS_PROFILE", True, aws_profile)
    try:
        import boto3

        session = boto3.Session(profile_name=aws_profile or None, region_name=aws_region)
        identity = session.client("sts").get_caller_identity()
        check("AWS STS", True, identity.get("Arn", "ok"))
    except Exception as exc:
        all_ok &= check("AWS STS", False, str(exc))

    print("\n[Vonage token generation]")
    if application_id and private_key_file.exists() and session_id:
        try:
            from vonage import Auth, Vonage
            from vonage_video import TokenOptions

            client = Vonage(Auth(application_id=application_id, private_key=str(private_key_file)))
            token = client.video.generate_client_token(
                TokenOptions(session_id=session_id, role="publisher")
            )
            token_str = token.decode("utf-8") if isinstance(token, bytes) else str(token)
            all_ok &= check("Vonage token", bool(token_str), f"{len(token_str)} chars")
        except Exception as exc:
            all_ok &= check("Vonage token", False, str(exc))
    else:
        check("Vonage token", False, "skipped — missing application_id, key, or session_id")

    print("\n[Local network probe (optional pre-deploy smoke test)]")
    print("  Run locally (not inside AgentCore) to verify probe script:")
    print("  python network_probe.py")

    print("\n" + "=" * 70)
    if all_ok:
        print("C6 Stage 0 PASSED ✓")
        print("\nNext steps:")
        print("  1. cd tests/c6_agentcore_video_transport")
        print("  2. agentcore configure -e agentcore_video_agent.py -r us-east-1")
        print("  3. AWS_PROFILE=vonage-dev agentcore deploy")
        print("  4. Set AGENTCORE_RUNTIME_ARN in root .env")
        print("  5. python test_agentcore_video.py --stage network")
        sys.exit(0)

    print("C6 Stage 0 FAILED ✗ — fix issues above before deploying")
    sys.exit(1)


if __name__ == "__main__":
    main()
