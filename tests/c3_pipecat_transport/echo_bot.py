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
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".env").exists():
            return candidate
    workspace_root = Path("/workspace")
    if (workspace_root / ".env").exists():
        return workspace_root
    return start.resolve()  # .env not found; env vars come from docker-compose env_file


REPO_ROOT = find_repo_root(Path(__file__).parent)
load_dotenv(REPO_ROOT / ".env")


async def run_echo_bot() -> None:
    def env_bool(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def env_resolution(name: str, default: tuple[int, int]) -> tuple[int, int]:
        value = os.getenv(name, "").strip()
        if not value:
            return default
        try:
            width_str, height_str = value.lower().split("x", 1)
            return (int(width_str), int(height_str))
        except ValueError:
            print(f"WARN: Invalid {name}={value!r}, using default {default[0]}x{default[1]}")
            return default

    def env_int(name: str, default: int) -> int:
        value = os.getenv(name, "").strip()
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            print(f"WARN: Invalid {name}={value!r}, using default {default}")
            return default

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

    # Optional transport tuning aligned with official docs
    video_connector_log_level = os.getenv("VONAGE_VIDEO_CONNECTOR_LOG_LEVEL", "INFO").strip() or "INFO"
    session_enable_migration = env_bool("VONAGE_SESSION_ENABLE_MIGRATION", False)
    clear_buffers_on_interruption = env_bool("VONAGE_CLEAR_BUFFERS_ON_INTERRUPTION", True)
    enable_pipecat_logger = env_bool("VONAGE_ENABLE_PIPECAT_LOGGER", True)

    manual_subscribe = env_bool("VONAGE_MANUAL_SUBSCRIBE", False)
    manual_subscribe_video = env_bool("VONAGE_MANUAL_SUBSCRIBE_VIDEO", False)

    audio_in_enabled = env_bool("VONAGE_AUDIO_IN_ENABLED", True)
    audio_out_enabled = env_bool("VONAGE_AUDIO_OUT_ENABLED", True)
    video_in_enabled = env_bool("VONAGE_VIDEO_IN_ENABLED", False)
    video_out_enabled = env_bool("VONAGE_VIDEO_OUT_ENABLED", False)

    audio_in_sample_rate = env_int("VONAGE_AUDIO_IN_SAMPLE_RATE", 16000)
    audio_out_sample_rate = env_int("VONAGE_AUDIO_OUT_SAMPLE_RATE", 24000)
    audio_in_channels = env_int("VONAGE_AUDIO_IN_CHANNELS", 1)
    audio_out_channels = env_int("VONAGE_AUDIO_OUT_CHANNELS", 1)

    video_out_width = env_int("VONAGE_VIDEO_OUT_WIDTH", 1280)
    video_out_height = env_int("VONAGE_VIDEO_OUT_HEIGHT", 720)
    video_out_framerate = env_int("VONAGE_VIDEO_OUT_FRAMERATE", 30)
    video_out_color_format = os.getenv("VONAGE_VIDEO_OUT_COLOR_FORMAT", "RGB").strip() or "RGB"

    publisher_enable_opus_dtx = env_bool("VONAGE_PUBLISHER_ENABLE_OPUS_DTX", False)
    publisher_name = os.getenv("VONAGE_PUBLISHER_NAME", "Pipecat Echo Bot").strip() or "Pipecat Echo Bot"

    audio_in_auto_subscribe = env_bool("VONAGE_AUDIO_IN_AUTO_SUBSCRIBE", True)
    video_in_auto_subscribe = env_bool("VONAGE_VIDEO_IN_AUTO_SUBSCRIBE", False)
    if manual_subscribe:
        audio_in_auto_subscribe = False
        video_in_auto_subscribe = False

    preferred_resolution = env_resolution("VONAGE_VIDEO_IN_PREFERRED_RESOLUTION", (640, 480))
    preferred_framerate = env_int("VONAGE_VIDEO_IN_PREFERRED_FRAMERATE", 15)

    monitor_enabled = env_bool("VONAGE_MONITOR_ENABLED", True)
    monitor_interval_seconds = env_int("VONAGE_MONITOR_INTERVAL_SECONDS", 15)
    debug_event_payloads = env_bool("VONAGE_DEBUG_EVENT_PAYLOADS", False)

    # ── Imports ───────────────────────────────────────────────────
    try:
        from vonage import Auth, Vonage
        from vonage_video import TokenOptions
        from loguru import logger
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask
        from pipecat.transports.vonage.video_connector import (
            SubscribeSettings,
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
        TokenOptions(
            session_id=session_id,
            role="publisher",
        )
    )
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    if enable_pipecat_logger:
        logger.enable("pipecat")

    print(f"Initialising Vonage Pipecat transport for session {session_id} …")

    # ── Build Pipecat pipeline ────────────────────────────────────
    transport = VonageVideoConnectorTransport(
        application_id=application_id,
        session_id=session_id,
        token=token,
        params=VonageVideoConnectorTransportParams(
            audio_in_enabled=audio_in_enabled,
            audio_out_enabled=audio_out_enabled,
            video_in_enabled=video_in_enabled,
            video_out_enabled=video_out_enabled,
            publisher_name=publisher_name,
            audio_in_sample_rate=audio_in_sample_rate,
            audio_in_channels=audio_in_channels,
            audio_out_sample_rate=audio_out_sample_rate,
            audio_out_channels=audio_out_channels,
            video_out_width=video_out_width,
            video_out_height=video_out_height,
            video_out_framerate=video_out_framerate,
            video_out_color_format=video_out_color_format,
            vad_analyzer=SileroVADAnalyzer(),
            audio_in_auto_subscribe=audio_in_auto_subscribe,
            video_in_auto_subscribe=video_in_auto_subscribe,
            video_in_preferred_resolution=preferred_resolution,
            video_in_preferred_framerate=preferred_framerate,
            publisher_enable_opus_dtx=publisher_enable_opus_dtx,
            session_enable_migration=session_enable_migration,
            video_connector_log_level=video_connector_log_level,
            clear_buffers_on_interruption=clear_buffers_on_interruption,
        ),
    )

    pipeline = Pipeline([
        transport.input(),   # Receive audio from Vonage session
        transport.output(),  # Send audio frames straight back into the session
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
    )

    active_streams: set[str] = set()
    active_subscribers: set[str] = set()
    event_counts = {
        "participant_joined": 0,
        "participant_left": 0,
        "client_connected": 0,
        "client_disconnected": 0,
        "errors": 0,
    }

    def maybe_dump_event_payload(event_name: str, payload: dict) -> None:
        if not debug_event_payloads:
            return
        logger.debug(f"{event_name} payload: {json.dumps(payload, sort_keys=True)}")

    async def monitor_loop() -> None:
        while True:
            await asyncio.sleep(max(1, monitor_interval_seconds))
            logger.info(
                "monitor: active_streams={} active_subscribers={} event_counts={}",
                len(active_streams),
                len(active_subscribers),
                event_counts,
            )

    monitor_task = asyncio.create_task(monitor_loop()) if monitor_enabled else None

    @transport.event_handler("on_joined")
    async def on_joined(transport, data):
        print(f"✓ Connected to Vonage Video session {data['sessionId']}")
        maybe_dump_event_payload("on_joined", data)

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(transport, data):
        event_counts["participant_joined"] += 1
        stream_id = data.get("streamId", "unknown")
        if stream_id != "unknown":
            active_streams.add(stream_id)
        print(f"  Participant joined with stream {stream_id}")
        maybe_dump_event_payload("on_participant_joined", data)
        if manual_subscribe and stream_id != "unknown":
            print(
                f"  Manual subscribe stream={stream_id} "
                f"(audio=True, video={manual_subscribe_video}, "
                f"resolution={preferred_resolution[0]}x{preferred_resolution[1]}, fps={preferred_framerate})"
            )
            await transport.subscribe_to_stream(
                stream_id,
                SubscribeSettings(
                    subscribe_to_audio=True,
                    subscribe_to_video=manual_subscribe_video,
                    preferred_resolution=preferred_resolution,
                    preferred_framerate=preferred_framerate,
                ),
            )

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, data):
        stream_id = data.get("streamId", "unknown")
        print(f"  First participant joined with stream {stream_id}")
        maybe_dump_event_payload("on_first_participant_joined", data)

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, data):
        event_counts["participant_left"] += 1
        stream_id = data.get("streamId", "unknown")
        if stream_id != "unknown":
            active_streams.discard(stream_id)
        print(f"  Participant left stream {stream_id}")
        maybe_dump_event_payload("on_participant_left", data)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, data):
        event_counts["client_connected"] += 1
        subscriber_id = data.get("subscriberId", "unknown")
        if subscriber_id != "unknown":
            active_subscribers.add(subscriber_id)
        print(f"  Client connected to stream {subscriber_id}")
        maybe_dump_event_payload("on_client_connected", data)

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, data):
        event_counts["client_disconnected"] += 1
        subscriber_id = data.get("subscriberId", "unknown")
        if subscriber_id != "unknown":
            active_subscribers.discard(subscriber_id)
        print(f"  Client disconnected from stream {subscriber_id}")
        maybe_dump_event_payload("on_client_disconnected", data)

    @transport.event_handler("on_left")
    async def on_left(transport, data):
        print(f"Left Vonage Video session {data.get('sessionId', '')}".rstrip())
        maybe_dump_event_payload("on_left", data)

    @transport.event_handler("on_error")
    async def on_error(transport, error):
        event_counts["errors"] += 1
        print(f"ERROR: Transport error — {error}")
        logger.exception("transport_error")

    print("Pipecat pipeline running — speak into your browser microphone")
    print("  Audio received → echoed back as audio")
    print(
        f"  Transport config: log_level={video_connector_log_level}, "
        f"audio_in={audio_in_enabled}, audio_out={audio_out_enabled}, "
        f"video_in={video_in_enabled}, video_out={video_out_enabled}, "
        f"session_migration={session_enable_migration}, "
        f"clear_buffers_on_interruption={clear_buffers_on_interruption}, "
        f"manual_subscribe={manual_subscribe}, "
        f"opus_dtx={publisher_enable_opus_dtx}, "
        f"monitor_enabled={monitor_enabled}, "
        f"monitor_interval_s={monitor_interval_seconds}, "
        f"debug_event_payloads={debug_event_payloads}"
    )
    print("Press Ctrl+C to stop.\n")

    runner = PipelineRunner()
    try:
        await runner.run(task)
    finally:
        if monitor_task is not None:
            monitor_task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(run_echo_bot())
    except KeyboardInterrupt:
        print("\nStopped by user. Test C3 complete ✓")
