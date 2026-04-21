#!/usr/bin/env python3
"""
Test C3: Pipecat Transport — Vonage Video Echo Bot

Runs a Pipecat pipeline that:
  1. Joins the Vonage Video session via the Video Connector SDK
  2. Receives audio from browser participants
  3. Passes audio through a VAD → STT → echo → TTS pipeline
  4. Sends synthesised speech back into the session

Platform: Linux only.  Run via Docker on macOS — see README.md.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


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
        private_key_file = Path(__file__).resolve().parents[2] / private_key_path
    if not private_key_file.exists():
        print(f"ERROR: Private key not found: {private_key_file}")
        sys.exit(1)

    # ── Imports ───────────────────────────────────────────────────
    try:
        from vonage import Auth, Vonage
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask
        from pipecat.processors.frameworks.vonage import VonageTransport
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.services.echo import EchoService
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("  Run: uv pip install -r requirements.txt")
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
    print(f"Initialising Vonage transport for session {session_id} …")

    # ── Build Pipecat pipeline ────────────────────────────────────
    transport = VonageTransport(
        session_id=session_id,
        token=token,
        application_id=application_id,
        vad_analyzer=SileroVADAnalyzer(),
        params=VonageTransport.InputParams(audio_enabled=True),
    )

    echo = EchoService()

    pipeline = Pipeline([
        transport.input(),   # Receive audio from Vonage session
        echo,                # Echo frames straight back (STT → passthrough → TTS)
        transport.output(),  # Send audio back into the session
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
    )

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(transport, participant):
        print(f"  Participant joined: {participant['id']}")

    print("✓ Connected to Vonage Video session")
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
