#!/usr/bin/env python3
"""
Production AgentCore Runtime — Vonage Video + Pipecat + Nova Sonic.

Deploy with: cd runtime && agentcore deploy (see README.md).
Invoke via answer/server.py POST /start-agent with session_id + token.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from network_probe import run_network_probe
from vonage_env import load_vonage_credentials

app = BedrockAgentCoreApp()

_pipeline_lock = asyncio.Lock()
_pipeline_task: asyncio.Task | None = None
_pipeline_runner_task: asyncio.Task | None = None
_pipeline_state: dict[str, Any] = {
    "running": False,
    "connected": False,
    "session_id": None,
    "mode": None,
    "started_at": None,
    "last_error": None,
    "event_counts": {},
}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _context_value(context: Any, key: str) -> str:
    if context is None:
        return ""
    if isinstance(context, dict):
        return str(context.get(key, "") or "").strip()
    getter = getattr(context, "get", None)
    if callable(getter):
        return str(getter(key, "") or "").strip()
    return str(getattr(context, key, "") or "").strip()


def _join_credentials(payload: dict[str, Any], context: Any) -> tuple[str, str]:
    """Resolve session_id and token from invoke payload/context (dynamic per session)."""
    session_id = (
        str(payload.get("session_id") or "").strip()
        or _context_value(context, "session_id")
    )
    token = (
        str(payload.get("token") or "").strip()
        or _context_value(context, "token")
    )
    return session_id, token


def _status_payload() -> dict[str, Any]:
    running = _pipeline_task is not None and not _pipeline_task.done()
    return {
        "running": running,
        "connected": _pipeline_state.get("connected", False),
        "session_id": _pipeline_state.get("session_id"),
        "mode": _pipeline_state.get("mode"),
        "started_at": _pipeline_state.get("started_at"),
        "last_error": _pipeline_state.get("last_error"),
        "event_counts": _pipeline_state.get("event_counts", {}),
    }


async def _stop_pipeline() -> None:
    global _pipeline_task, _pipeline_runner_task

    if _pipeline_runner_task and not _pipeline_runner_task.done():
        _pipeline_runner_task.cancel()
        try:
            await _pipeline_runner_task
        except asyncio.CancelledError:
            pass
        _pipeline_runner_task = None

    if _pipeline_task and not _pipeline_task.done():
        _pipeline_task.cancel()
        try:
            await _pipeline_task
        except asyncio.CancelledError:
            pass
        _pipeline_task = None

    _pipeline_state["running"] = False
    _pipeline_state["connected"] = False


async def _generate_vonage_token(application_id: str, private_key_file: Path, session_id: str) -> str:
    from vonage import Auth, Vonage
    from vonage_video import TokenOptions

    client = Vonage(Auth(application_id=application_id, private_key=str(private_key_file)))
    token = client.video.generate_client_token(
        TokenOptions(session_id=session_id, role="publisher")
    )
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


async def _run_echo_pipeline(session_id: str, token: str, application_id: str) -> None:
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame, UserAudioRawFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
    from pipecat.transports.vonage.video_connector import (
        VonageVideoConnectorTransport,
        VonageVideoConnectorTransportParams,
    )

    class _EchoProcessor(FrameProcessor):
        async def process_frame(self, frame, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if isinstance(frame, InputAudioRawFrame):
                await self.push_frame(
                    OutputAudioRawFrame(
                        audio=frame.audio,
                        sample_rate=frame.sample_rate,
                        num_channels=frame.num_channels,
                    ),
                    direction,
                )
            elif isinstance(frame, UserAudioRawFrame):
                pass
            else:
                await self.push_frame(frame, direction)

    class _AudioFrameTap(FrameProcessor):
        """Log inbound audio frame flow — visible in CloudWatch when echo is working."""

        def __init__(self) -> None:
            super().__init__()
            self._count = 0

        async def process_frame(self, frame, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if isinstance(frame, InputAudioRawFrame):
                self._count += 1
                if self._count == 1 or self._count % 100 == 0:
                    print(f"C6 echo audio frames in pipeline: {self._count}")
            await self.push_frame(frame, direction)

    publisher_name = os.getenv("VONAGE_PUBLISHER_NAME", "C6 Echo Agent").strip() or "C6 Echo Agent"
    video_connector_log_level = os.getenv("VONAGE_VIDEO_CONNECTOR_LOG_LEVEL", "INFO").strip() or "INFO"

    transport = VonageVideoConnectorTransport(
        application_id=application_id,
        session_id=session_id,
        token=token,
        params=VonageVideoConnectorTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            video_in_enabled=False,
            video_out_enabled=False,
            publisher_name=publisher_name,
            audio_in_sample_rate=16000,
            audio_in_channels=1,
            audio_out_sample_rate=24000,
            audio_out_channels=1,
            vad_analyzer=SileroVADAnalyzer(),
            audio_in_auto_subscribe=True,
            video_in_auto_subscribe=False,
            clear_buffers_on_interruption=True,
            session_enable_migration=False,
            video_connector_log_level=video_connector_log_level,
        ),
    )

    pipeline = Pipeline([transport.input(), _AudioFrameTap(), _EchoProcessor(), transport.output()])
    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
        enable_rtvi=False,
        cancel_on_idle_timeout=False,
        idle_timeout_secs=None,
    )
    runner = PipelineRunner()

    @transport.event_handler("on_joined")
    async def on_joined(_transport, data):
        _pipeline_state["connected"] = True
        print(f"C6 joined session {data.get('sessionId')}")

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(_transport, data):
        counts = _pipeline_state.setdefault("event_counts", {})
        counts["participant_joined"] = counts.get("participant_joined", 0) + 1
        print(f"C6 participant joined stream={data.get('streamId')}")

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, data):
        counts = _pipeline_state.setdefault("event_counts", {})
        counts["client_connected"] = counts.get("client_connected", 0) + 1
        print(f"C6 subscriber connected stream={data.get('subscriberId')}")

    @transport.event_handler("on_error")
    async def on_error(_transport, error):
        _pipeline_state["last_error"] = str(error)
        counts = _pipeline_state.setdefault("event_counts", {})
        counts["errors"] = counts.get("errors", 0) + 1
        print(f"C6 transport error: {error}")

    await runner.run(task)


async def _run_nova_sonic_pipeline(session_id: str, token: str, application_id: str) -> None:
    import boto3
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.frames.frames import LLMContextFrame, LLMRunFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
    from pipecat.services.aws.nova_sonic.llm import AWSNovaSonicLLMService, Params
    from pipecat.transports.vonage.video_connector import (
        VonageVideoConnectorTransport,
        VonageVideoConnectorTransportParams,
    )

    aws_region = os.getenv("AWS_REGION", "us-east-1").strip()
    bedrock_model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-2-sonic-v1:0").strip()
    bootstrap_prompt = os.getenv(
        "AGENTCORE_BOOTSTRAP_PROMPT",
        "You are a helpful voice assistant. Keep responses brief and conversational.",
    ).strip()
    initial_user_message = os.getenv("BEDROCK_INITIAL_USER_MESSAGE", "").strip()

    system_instruction = bootstrap_prompt
    if initial_user_message:
        system_instruction = (
            f"{bootstrap_prompt}\n\n"
            "When the session starts, your first spoken message to the participant must be:\n"
            f"{initial_user_message}"
        )

    session_kwargs: dict[str, Any] = {"region_name": aws_region}
    aws_session = boto3.Session(**session_kwargs)
    credentials = aws_session.get_credentials()
    if credentials is None:
        raise RuntimeError("boto3 could not resolve AWS credentials")
    frozen = credentials.get_frozen_credentials()

    llm_context = LLMContext(
        messages=[
            {
                "role": "user",
                "content": (
                    "The participant has joined the video session. "
                    "Begin with your opening greeting now."
                ),
            }
        ]
    )
    context_aggregator = LLMContextAggregatorPair(llm_context)

    nova_sonic = AWSNovaSonicLLMService(
        access_key_id=frozen.access_key,
        secret_access_key=frozen.secret_key,
        session_token=frozen.token,
        region=aws_region,
        model=bedrock_model_id,
        params=Params(
            input_sample_rate=16000,
            input_channel_count=1,
            output_sample_rate=24000,
            output_channel_count=1,
        ),
        system_instruction=system_instruction,
    )

    publisher_name = os.getenv("VONAGE_PUBLISHER_NAME", "C6 Nova Agent").strip() or "C6 Nova Agent"
    transport = VonageVideoConnectorTransport(
        application_id=application_id,
        session_id=session_id,
        token=token,
        params=VonageVideoConnectorTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            video_in_enabled=False,
            video_out_enabled=False,
            publisher_name=publisher_name,
            audio_in_sample_rate=16000,
            audio_in_channels=1,
            audio_out_sample_rate=24000,
            audio_out_channels=1,
            vad_analyzer=SileroVADAnalyzer(),
            audio_in_auto_subscribe=True,
            video_in_auto_subscribe=False,
        ),
    )

    pipeline = Pipeline([
        transport.input(),
        context_aggregator.user(),
        nova_sonic,
        context_aggregator.assistant(),
        transport.output(),
    ])
    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
        enable_rtvi=False,
        cancel_on_idle_timeout=False,
        idle_timeout_secs=None,
    )
    runner = PipelineRunner()
    context_seeded = False

    async def seed_nova_sonic(reason: str) -> None:
        """Seed context + trigger LLM run — prevents Nova Sonic 532 idle timeout."""
        nonlocal context_seeded
        if context_seeded:
            return
        print(f"C6 seeding Nova Sonic context ({reason})")
        await task.queue_frame(LLMContextFrame(llm_context))
        await task.queue_frame(LLMRunFrame())
        context_seeded = True

    @transport.event_handler("on_joined")
    async def on_joined(_transport, data):
        _pipeline_state["connected"] = True
        print(f"C6 joined session {data.get('sessionId')} model={bedrock_model_id}")
        print(
            f"C6 Nova Sonic persona: bootstrap_chars={len(bootstrap_prompt)} "
            f"opening_chars={len(initial_user_message)}"
        )
        await seed_nova_sonic("on_joined")

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(_transport, data):
        counts = _pipeline_state.setdefault("event_counts", {})
        counts["participant_joined"] = counts.get("participant_joined", 0) + 1
        await seed_nova_sonic("on_participant_joined")

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _data):
        counts = _pipeline_state.setdefault("event_counts", {})
        counts["client_connected"] = counts.get("client_connected", 0) + 1
        await seed_nova_sonic("on_client_connected")

    @transport.event_handler("on_error")
    async def on_error(_transport, error):
        _pipeline_state["last_error"] = str(error)
        counts = _pipeline_state.setdefault("event_counts", {})
        counts["errors"] = counts.get("errors", 0) + 1
        print(f"C6 transport error: {error}")

    await runner.run(task)


async def _pipeline_wrapper(session_id: str, token: str, mode: str) -> None:
    global _pipeline_runner_task

    application_id, private_key_file = load_vonage_credentials()

    if not application_id:
        _pipeline_state["last_error"] = "VONAGE_APPLICATION_ID not set"
        return
    if not private_key_file.exists():
        _pipeline_state["last_error"] = f"private key not found: {private_key_file}"
        return

    try:
        if not token:
            token = await _generate_vonage_token(application_id, private_key_file, session_id)
        _pipeline_state["running"] = True
        _pipeline_state["session_id"] = session_id
        _pipeline_state["mode"] = mode
        _pipeline_state["started_at"] = time.time()
        _pipeline_state["last_error"] = None
        _pipeline_state["event_counts"] = {}

        if mode == "nova_sonic":
            await _run_nova_sonic_pipeline(session_id, token, application_id)
        else:
            await _run_echo_pipeline(session_id, token, application_id)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _pipeline_state["last_error"] = str(exc)
        print(f"C6 pipeline failed: {exc}")
    finally:
        _pipeline_state["running"] = False
        _pipeline_state["connected"] = False


async def _start_pipeline(session_id: str, token: str, mode: str) -> dict[str, Any]:
    global _pipeline_task

    async with _pipeline_lock:
        if _pipeline_task and not _pipeline_task.done():
            return {
                "error": "pipeline already running",
                "status": _status_payload(),
            }

        await _stop_pipeline()
        _pipeline_task = asyncio.create_task(_pipeline_wrapper(session_id, token, mode))

    return {"status": "joining", "session_id": session_id, "mode": mode}


@app.entrypoint
async def handler(payload: dict[str, Any], context: Any = None) -> dict[str, Any]:
    action = (payload or {}).get("action", "").strip().lower()

    if action == "network_probe":
        return await run_network_probe()

    if action == "status":
        return _status_payload()

    if action == "leave":
        async with _pipeline_lock:
            session_id = _pipeline_state.get("session_id")
            await _stop_pipeline()
        return {"status": "left", "session_id": session_id}

    if action == "join":
        session_id, token = _join_credentials(payload or {}, context)
        if not session_id:
            return {"error": "session_id is required in invoke payload or context"}
        if not token:
            application_id, _ = load_vonage_credentials()
            if not application_id:
                return {"error": "token required when VONAGE_APPLICATION_ID is unavailable for generation"}
        mode = (payload.get("mode") or os.getenv("C6_PIPELINE_MODE", "nova_sonic")).strip().lower()
        if mode not in {"echo", "nova_sonic"}:
            return {"error": f"unsupported mode: {mode}"}
        return await _start_pipeline(session_id, token, mode)

    return {"error": f"unknown action: {action or '(empty)'}"}


@app.websocket
async def ws_handler(websocket, context: Any = None) -> None:
    """Stage 4b alternative trigger — receive join/leave commands over /ws."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            action = (data.get("action") or "").strip().lower()

            if action == "network_probe":
                await websocket.send_json(await run_network_probe())
            elif action == "status":
                await websocket.send_json(_status_payload())
            elif action == "leave":
                async with _pipeline_lock:
                    session_id = _pipeline_state.get("session_id")
                    await _stop_pipeline()
                await websocket.send_json({"status": "left", "session_id": session_id})
            elif action == "join":
                session_id, token = _join_credentials(data, context)
                mode = (data.get("mode") or os.getenv("C6_PIPELINE_MODE", "nova_sonic")).strip().lower()
                result = await _start_pipeline(session_id, token, mode)
                await websocket.send_json(result)
            else:
                await websocket.send_json({"error": f"unknown action: {action}"})
    except Exception as exc:
        print(f"C6 websocket error: {exc}")
    finally:
        await websocket.close()


if __name__ == "__main__":
    app.run()
