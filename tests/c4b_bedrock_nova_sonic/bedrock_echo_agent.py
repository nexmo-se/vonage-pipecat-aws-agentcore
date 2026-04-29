#!/usr/bin/env python3
"""
Test C4b: AWS Bedrock + Vonage Pipecat Transport — Echo Agent

Runs a Pipecat pipeline that:
    1. Joins the Vonage Video session (same as C3)
    2. Receives audio from browser participants
    3. Invokes AWS Bedrock Nova Sonic LLM for text responses
    4. Echoes back combined response via transport

This test validates:
    - Bedrock LLM integration with Vonage transport
    - Event handling + LLM invocation coordination
    - End-to-end session lifecycle with external AI service

Platform: Linux only. Run via Docker on macOS — see README.md.
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
    return start.resolve()


REPO_ROOT = find_repo_root(Path(__file__).parent)
load_dotenv(REPO_ROOT / ".env")


async def run_bedrock_echo_agent() -> None:
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

    # ── Vonage Video configuration ────────────────────────────────
    application_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    private_key_path = os.getenv("VONAGE_PRIVATE_KEY", "private.key").strip()
    session_id = os.getenv("VONAGE_SESSION_ID", "").strip()

    # ── AWS Bedrock configuration ─────────────────────────────────
    bedrock_model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-2-sonic-v1:0").strip()
    aws_region = os.getenv("AWS_REGION", "us-east-1").strip()
    aws_profile = os.getenv("AWS_PROFILE", os.getenv("AWS_DEFAULT_PROFILE", "")).strip()
    initial_user_message = os.getenv(
        "BEDROCK_INITIAL_USER_MESSAGE",
        "Please greet the participant briefly and ask how you can help.",
    ).strip()

    # ── Validate required env vars ────────────────────────────────
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

    # ── Optional transport tuning ─────────────────────────────────
    video_connector_log_level = os.getenv("VONAGE_VIDEO_CONNECTOR_LOG_LEVEL", "INFO").strip() or "INFO"
    session_enable_migration = env_bool("VONAGE_SESSION_ENABLE_MIGRATION", False)
    clear_buffers_on_interruption = env_bool("VONAGE_CLEAR_BUFFERS_ON_INTERRUPTION", True)
    enable_pipecat_logger = env_bool("VONAGE_ENABLE_PIPECAT_LOGGER", True)
    enable_bedrock_debug = env_bool("VONAGE_ENABLE_BEDROCK_DEBUG", True)

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
    publisher_name = os.getenv("VONAGE_PUBLISHER_NAME", "Bedrock Echo Agent").strip() or "Bedrock Echo Agent"

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
        import boto3
        from vonage import Auth, Vonage
        from vonage_video import TokenOptions
        from loguru import logger
        from pipecat.frames.frames import LLMContextFrame
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask
        from pipecat.processors.aggregators.llm_context import LLMContext
        from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
        from pipecat.services.aws.nova_sonic.llm import AWSNovaSonicLLMService, Params
        from pipecat.transports.vonage.video_connector import (
            SubscribeSettings,
            VonageVideoConnectorTransport,
            VonageVideoConnectorTransportParams,
        )
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("  Run: pip install -r requirements.txt")
        sys.exit(1)

    session_kwargs = {"region_name": aws_region}
    if aws_profile:
        session_kwargs["profile_name"] = aws_profile

    try:
        aws_session = boto3.Session(**session_kwargs)
        credentials = aws_session.get_credentials()
        if credentials is None:
            raise RuntimeError("boto3 could not resolve AWS credentials")
        frozen_credentials = credentials.get_frozen_credentials()
    except Exception as exc:
        print(f"ERROR: Unable to resolve AWS credentials for Nova Sonic — {exc}")
        sys.exit(1)

    print(f"Initializing Nova Sonic ({bedrock_model_id}) in {aws_region}…")
    if aws_profile:
        print(f"Using AWS profile {aws_profile} via mounted credentials")
    nova_sonic = AWSNovaSonicLLMService(
        access_key_id=frozen_credentials.access_key,
        secret_access_key=frozen_credentials.secret_key,
        session_token=frozen_credentials.token,
        region=aws_region,
        model=bedrock_model_id,
        params=Params(
            input_sample_rate=audio_in_sample_rate,
            input_channel_count=audio_in_channels,
            output_sample_rate=audio_out_sample_rate,
            output_channel_count=audio_out_channels,
        ),
        system_instruction=(
            "You are a helpful voice assistant. Respond warmly and briefly in one or two short sentences."
        ),
    )
    # AWSNovaSonicLLMService requires initial context before it finishes session setup.
    context_messages = []
    if initial_user_message:
        context_messages.append({"role": "user", "content": initial_user_message})
    context = LLMContext(messages=context_messages)
    context_aggregator = LLMContextAggregatorPair(context)

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

    print(f"Initialising Vonage Pipecat transport for session {session_id}…")

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
        transport.input(),   # Receive participant audio from Vonage session
        context_aggregator.user(),
        nova_sonic,          # Speech-to-speech via AWS Nova Sonic
        context_aggregator.assistant(),
        transport.output(),  # Publish response audio back into the session
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
        cancel_on_idle_timeout=False,
        idle_timeout_secs=None,
    )

    active_streams: set[str] = set()
    active_subscribers: set[str] = set()
    context_seeded = False
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

    async def seed_initial_context(reason: str) -> None:
        nonlocal context_seeded
        if context_seeded:
            return
        print(f"  Seeding initial Nova Sonic context ({reason})")
        logger.info("Seeding initial Nova Sonic context ({})", reason)
        await task.queue_frame(LLMContextFrame(context))
        context_seeded = True

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
        print(f"✓ Nova Sonic ({bedrock_model_id}) ready for participant interactions")
        maybe_dump_event_payload("on_joined", data)
        await seed_initial_context("on_joined")

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(transport, data):
        event_counts["participant_joined"] += 1
        stream_id = data.get("streamId", "unknown")
        if stream_id != "unknown":
            active_streams.add(stream_id)
        print(f"  Participant joined with stream {stream_id}")
        maybe_dump_event_payload("on_participant_joined", data)
        await seed_initial_context("on_participant_joined")
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
        if enable_bedrock_debug:
            logger.debug(f"on_client_connected data: {json.dumps(data, default=str)}")
        maybe_dump_event_payload("on_client_connected", data)
        await seed_initial_context("on_client_connected")

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

    print("Pipecat pipeline with Nova Sonic running — speak into your browser microphone")
    print("  Audio received → Nova Sonic processes → spoken response published back")
    print(
        f"  Transport config: log_level={video_connector_log_level}, "
        f"audio_in={audio_in_enabled}, audio_out={audio_out_enabled}, "
        f"video_in={video_in_enabled}, video_out={video_out_enabled}, "
        f"session_migration={session_enable_migration}"
    )
    print(f"  AI config: model={bedrock_model_id}, region={aws_region}")
    print("Press Ctrl+C to stop.\n")

    runner = PipelineRunner()
    try:
        await runner.run(task)
    finally:
        if monitor_task is not None:
            monitor_task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(run_bedrock_echo_agent())
    except KeyboardInterrupt:
        print("\nStopped by user. Test C4b Bedrock integration complete ✓")
