#!/usr/bin/env python3
"""
Test C3: Pipecat Transport — Vonage Video Echo Bot

Runs a Pipecat pipeline that:
    1. Joins the Vonage Video session via the official Vonage Pipecat transport
  2. Receives audio from browser participants
    3. Passes audio through VAD and a simple echo stage
    4. Sends the audio back into the session

Platform: Linux only.  Run via Docker on macOS — see README.md.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".env").exists():
            return candidate
    return start.resolve()  # .env not found; env vars come from docker-compose env_file


REPO_ROOT = find_repo_root(Path(__file__).parent)
load_dotenv(REPO_ROOT / ".env")


async def run_echo_bot() -> None:
    application_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    private_key_path = os.getenv("VONAGE_PRIVATE_KEY", "private.key").strip()
    session_id = os.getenv("VONAGE_SESSION_ID", "").strip()

    # ── Validate env vars ─────────────────────────────────────────
    missing: list[str] = []
    if not application_id:
        missing.append("VONAGE_APPLICATION_ID")
    if not session_id:
        missing.append("VONAGE_SESSION_ID")
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    private_key_file = Path(private_key_path)
    if not private_key_file.is_absolute():
        private_key_file = REPO_ROOT / private_key_path
    if not private_key_file.exists():
        print(f"ERROR: Private key not found: {private_key_file}")
        sys.exit(1)

    # ── Imports ───────────────────────────────────────────────────
    try:
        from vonage import Auth, Vonage
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask
        from pipecat.services.echo import EchoService
        from pipecat.transports.vonage.video_connector import (
            VonageVideoConnectorTransport,
            VonageVideoConnectorTransportParams,
        )
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("  Run: pip install -r requirements.txt")
        sys.exit(1)

    # ── Generate publisher token ──────────────────────────────────
    client = Vonage(
        Auth(
            application_id=application_id,
            private_key=str(private_key_file),
        )
    )
    token = client.video.generate_client_token(
        session_id=session_id,
        role="publisher",
        expire_time=3600,
    )
    print(f"Initialising Vonage Pipecat transport for session {session_id} …")

    # ── Build Pipecat pipeline ────────────────────────────────────
    transport = VonageVideoConnectorTransport(
        application_id=application_id,
        session_id=session_id,
        token=token,
        params=VonageVideoConnectorTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            publisher_name="Pipecat Echo Bot",
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
            vad_analyzer=SileroVADAnalyzer(),
            audio_in_auto_subscribe=True,
            video_in_auto_subscribe=False,
            video_connector_log_level="INFO",
            clear_buffers_on_interruption=True,
        ),
    )

    echo = EchoService()

    pipeline = Pipeline([
        transport.input(),   # Receive audio from Vonage session
        echo,                # Echo audio frames straight back to the caller
        transport.output(),  # Send audio back into the session
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
    )

    @transport.event_handler("on_joined")
    async def on_joined(transport, data):
        print(f"✓ Connected to Vonage Video session {data['sessionId']}")

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(transport, data):
        stream_id = data.get("streamId", "unknown")
        print(f"  Participant joined with stream {stream_id}")

    @transport.event_handler("on_left")
    async def on_left(transport, data):
        print(f"Left Vonage Video session {data.get('sessionId', '')}".rstrip())

    @transport.event_handler("on_error")
    async def on_error(transport, error):
        print(f"ERROR: Transport error — {error}")

    print("Pipecat pipeline running — speak into your browser microphone")
    print("  Audio received → echoed back as audio")
    print("Press Ctrl+C to stop.\n")

    runner = PipelineRunner()
    await runner.run(task)


if __name__ == "__main__":
    try:
        asyncio.run(run_echo_bot())
    except KeyboardInterrupt:
        print("\nStopped by user. Test C3 complete ✓")
