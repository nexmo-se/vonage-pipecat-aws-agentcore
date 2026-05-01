#!/usr/bin/env python3
"""Application agent runtime built from the validated C4 transport pipeline."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

import structlog
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = structlog.get_logger(__name__)


class VonagePipecatAgent:
    """Manages the Pipecat transport + Nova Sonic pipeline for one session."""

    def __init__(
        self,
        *,
        on_event: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> None:
        self._task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None
        self._runner = None
        self._pipeline_task = None
        self.session_id: str = os.getenv("VONAGE_SESSION_ID", "")
        self.connected: bool = False
        self.last_error: str | None = None
        self.on_event = on_event
        self.event_counts: dict[str, int] = {
            "participant_joined": 0,
            "participant_left": 0,
            "client_connected": 0,
            "client_disconnected": 0,
            "errors": 0,
        }

    async def _emit(self, event: dict[str, Any]) -> None:
        if self.on_event is None:
            return
        try:
            result = self.on_event(event)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:  # pragma: no cover - best effort callback
            logger.warning("Event callback failed", error=str(exc), event=event.get("event"))

    # ── Public interface ──────────────────────────────────────────

    async def start(self) -> None:
        """Build and start the Pipecat pipeline."""
        if self._task and not self._task.done():
            logger.warning("Agent already running")
            return
        if not self.session_id:
            raise ValueError("session_id is required")
        self.last_error = None
        self._task = asyncio.create_task(self._run_pipeline())

    async def stop(self) -> None:
        """Stop the pipeline and disconnect from the session."""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        if self._pipeline_task is not None:
            try:
                cancel_result = self._pipeline_task.cancel()
                if inspect.isawaitable(cancel_result):
                    await cancel_result
            except Exception:
                pass

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self.connected = False
        await self._emit({"event": "agent_stopped", "session_id": self.session_id})
        logger.info("Agent stopped")

    # ── Pipeline ──────────────────────────────────────────────────

    async def _run_pipeline(self) -> None:
        def env_bool(name: str, default: bool) -> bool:
            value = os.getenv(name)
            if value is None:
                return default
            return value.strip().lower() in {"1", "true", "yes", "on"}

        def env_int(name: str, default: int) -> int:
            value = os.getenv(name, "").strip()
            if not value:
                return default
            try:
                return int(value)
            except ValueError:
                logger.warning("Invalid integer env var; using default", name=name, value=value, default=default)
                return default

        try:
            import boto3
            from botocore.config import Config
            from botocore.exceptions import ClientError
            from vonage import Auth, Vonage
            from vonage_video import TokenOptions
            from pipecat.frames.frames import LLMContextFrame
            from pipecat.audio.vad.silero import SileroVADAnalyzer
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
        except ImportError as exc:
            self.last_error = f"missing dependency: {exc}"
            logger.error("Missing dependency", error=str(exc))
            await self._emit({"event": "agent_error", "error": self.last_error})
            return

        application_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
        private_key_path = os.getenv("VONAGE_PRIVATE_KEY", "private.key").strip()
        aws_region = os.getenv("AWS_REGION", "us-east-1").strip()
        bedrock_model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-2-sonic-v1:0").strip()
        aws_profile = os.getenv("AWS_PROFILE", os.getenv("AWS_DEFAULT_PROFILE", "")).strip()
        agentcore_runtime_arn = os.getenv("AGENTCORE_AGENT_ARN", "").strip()
        initial_user_message = os.getenv(
            "BEDROCK_INITIAL_USER_MESSAGE",
            "Please greet the participant briefly and ask how you can help.",
        ).strip()
        agentcore_bootstrap_prompt = os.getenv(
            "AGENTCORE_BOOTSTRAP_PROMPT",
            "Provide one short greeting plus one helpful follow-up question for a live voice assistant session.",
        ).strip()

        missing: list[str] = []
        if not application_id:
            missing.append("VONAGE_APPLICATION_ID")
        if not self.session_id:
            missing.append("VONAGE_SESSION_ID")
        if missing:
            self.last_error = f"missing env vars: {', '.join(missing)}"
            logger.error("Invalid environment", missing=missing)
            await self._emit({"event": "agent_error", "error": self.last_error})
            return

        private_key_file = Path(private_key_path)
        if not private_key_file.is_absolute():
            app_dir = Path(__file__).resolve().parent
            candidates = [
                app_dir / private_key_path,
                Path.cwd() / private_key_path,
                app_dir.parent / private_key_path,
            ]
            private_key_file = next((path for path in candidates if path.exists()), candidates[0])
        if not private_key_file.exists():
            self.last_error = f"private key not found: {private_key_file}"
            logger.error("Private key missing", path=str(private_key_file))
            await self._emit({"event": "agent_error", "error": self.last_error})
            return

        bedrock_connect_timeout_seconds = env_int("BEDROCK_CONNECT_TIMEOUT_SECONDS", 10)
        bedrock_read_timeout_seconds = env_int("BEDROCK_READ_TIMEOUT_SECONDS", 60)
        bedrock_max_attempts = env_int("BEDROCK_MAX_ATTEMPTS", 4)
        bedrock_validate_model_id = env_bool("BEDROCK_VALIDATE_MODEL_ID", True)

        session_kwargs: dict[str, Any] = {"region_name": aws_region}
        if aws_profile:
            session_kwargs["profile_name"] = aws_profile
        try:
            aws_session = boto3.Session(**session_kwargs)
            credentials = aws_session.get_credentials()
            if credentials is None:
                raise RuntimeError("boto3 could not resolve AWS credentials")
            frozen_credentials = credentials.get_frozen_credentials()
            aws_client_config = Config(
                retries={"max_attempts": max(1, bedrock_max_attempts), "mode": "standard"},
                connect_timeout=max(1, bedrock_connect_timeout_seconds),
                read_timeout=max(1, bedrock_read_timeout_seconds),
                user_agent_extra="vonage-pipecat-aws-agentcore-app/0.1",
            )
            agentcore_client = (
                aws_session.client("bedrock-agentcore", config=aws_client_config)
                if agentcore_runtime_arn
                else None
            )
        except Exception as exc:
            self.last_error = f"unable to resolve AWS credentials: {exc}"
            logger.error("AWS credential resolution failed", error=str(exc))
            await self._emit({"event": "agent_error", "error": self.last_error})
            return

        if bedrock_validate_model_id:
            try:
                bedrock_client = aws_session.client("bedrock", config=aws_client_config)
                bedrock_client.get_foundation_model(modelIdentifier=bedrock_model_id)
                logger.info("Bedrock model validation passed", model=bedrock_model_id, region=aws_region)
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code", "Unknown")
                # Fail fast only for clearly invalid model IDs; permission errors remain non-fatal.
                if error_code in {"ValidationException", "ResourceNotFoundException"}:
                    self.last_error = (
                        f"invalid BEDROCK_MODEL_ID '{bedrock_model_id}' for region {aws_region}: {error_code}"
                    )
                    logger.error(
                        "Bedrock model validation failed",
                        model=bedrock_model_id,
                        region=aws_region,
                        code=error_code,
                    )
                    await self._emit({"event": "agent_error", "error": self.last_error})
                    return
                logger.warning(
                    "Bedrock model validation skipped due to API permissions or transient error",
                    model=bedrock_model_id,
                    region=aws_region,
                    code=error_code,
                )

        # Optional transport tuning from the C3/C4 test flow.
        video_connector_log_level = os.getenv("VONAGE_VIDEO_CONNECTOR_LOG_LEVEL", "INFO").strip() or "INFO"
        session_enable_migration = env_bool("VONAGE_SESSION_ENABLE_MIGRATION", False)
        clear_buffers_on_interruption = env_bool("VONAGE_CLEAR_BUFFERS_ON_INTERRUPTION", True)
        audio_in_sample_rate = env_int("VONAGE_AUDIO_IN_SAMPLE_RATE", 16000)
        audio_out_sample_rate = env_int("VONAGE_AUDIO_OUT_SAMPLE_RATE", 24000)
        audio_in_channels = env_int("VONAGE_AUDIO_IN_CHANNELS", 1)
        audio_out_channels = env_int("VONAGE_AUDIO_OUT_CHANNELS", 1)
        monitor_enabled = env_bool("VONAGE_MONITOR_ENABLED", True)
        monitor_interval_seconds = env_int("VONAGE_MONITOR_INTERVAL_SECONDS", 15)
        # AWS Nova Sonic docs describe an ~8 minute connection window.
        # Emit an early renewal signal and optionally stop the pipeline at limit.
        nova_session_limit_seconds = env_int("NOVA_SESSION_LIMIT_SECONDS", 470)
        nova_session_warn_seconds = env_int(
            "NOVA_SESSION_WARN_SECONDS",
            max(60, nova_session_limit_seconds - 60),
        )
        nova_stop_on_limit = env_bool("NOVA_SESSION_STOP_ON_LIMIT", False)

        try:
            client = Vonage(
                Auth(
                    application_id=application_id,
                    private_key=str(private_key_file),
                )
            )
            token = client.video.generate_client_token(
                TokenOptions(
                    session_id=self.session_id,
                    role="publisher",
                )
            )
            if isinstance(token, bytes):
                token = token.decode("utf-8")
        except Exception as exc:
            self.last_error = f"failed to generate Vonage token: {exc}"
            logger.error("Vonage token generation failed", error=str(exc))
            await self._emit({"event": "agent_error", "error": self.last_error})
            return

        async def invoke_agentcore_bootstrap(prompt: str) -> str | None:
            if not prompt or agentcore_client is None or not agentcore_runtime_arn:
                return None

            def _invoke() -> str | None:
                response = agentcore_client.invoke_agent_runtime(
                    agentRuntimeArn=agentcore_runtime_arn,
                    contentType="application/json",
                    accept="application/json",
                    payload=json.dumps({"input": prompt}).encode("utf-8"),
                )
                body = response.get("payload") or response.get("response")
                if hasattr(body, "read"):
                    body = body.read()
                if isinstance(body, bytes):
                    body = body.decode("utf-8", errors="replace")
                return (body or "").strip() or None

            try:
                return await asyncio.to_thread(_invoke)
            except Exception as exc:
                logger.warning("AgentCore bootstrap invocation failed; continuing without it", error=str(exc))
                await self._emit({"event": "agentcore_bootstrap_failed", "error": str(exc)})
                return None

        bootstrap_message = await invoke_agentcore_bootstrap(agentcore_bootstrap_prompt)

        context_messages = []
        if bootstrap_message:
            context_messages.append(
                {
                    "role": "user",
                    "content": (
                        "Use the following context to shape your first response style: "
                        f"{bootstrap_message}"
                    ),
                }
            )
        if initial_user_message:
            context_messages.append({"role": "user", "content": initial_user_message})
        context = LLMContext(messages=context_messages)
        context_aggregator = LLMContextAggregatorPair(context)

        try:
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
                    "You are a helpful voice assistant for a Vonage video session. "
                    "Keep responses brief and conversational."
                ),
            )
        except Exception as exc:
            self.last_error = f"failed to initialize Nova Sonic: {exc}"
            logger.error("Nova Sonic initialization failed", error=str(exc))
            await self._emit({"event": "agent_error", "error": self.last_error})
            return

        transport = VonageVideoConnectorTransport(
            application_id=application_id,
            session_id=self.session_id,
            token=token,
            params=VonageVideoConnectorTransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                video_in_enabled=False,
                video_out_enabled=False,
                publisher_name=os.getenv("VONAGE_PUBLISHER_NAME", "Vonage AI Assistant").strip() or "Vonage AI Assistant",
                audio_in_sample_rate=audio_in_sample_rate,
                audio_in_channels=audio_in_channels,
                audio_out_sample_rate=audio_out_sample_rate,
                audio_out_channels=audio_out_channels,
                vad_analyzer=SileroVADAnalyzer(),
                audio_in_auto_subscribe=True,
                video_in_auto_subscribe=False,
                session_enable_migration=session_enable_migration,
                video_connector_log_level=video_connector_log_level,
                clear_buffers_on_interruption=clear_buffers_on_interruption,
            ),
        )

        pipeline = Pipeline([
            transport.input(),
            context_aggregator.user(),
            nova_sonic,
            context_aggregator.assistant(),
            transport.output(),
        ])

        self._pipeline_task = PipelineTask(
            pipeline,
            params=PipelineParams(allow_interruptions=True),
            cancel_on_idle_timeout=False,
            idle_timeout_secs=None,
        )

        context_seeded = False
        session_started_at: float | None = None
        renewal_emitted = False
        renewal_stop_triggered = False

        async def seed_initial_context(reason: str) -> None:
            nonlocal context_seeded
            if context_seeded:
                return
            logger.info("Seeding initial Nova Sonic context", reason=reason)
            await self._pipeline_task.queue_frame(LLMContextFrame(context))
            context_seeded = True

        async def monitor_loop() -> None:
            nonlocal renewal_emitted, renewal_stop_triggered
            while True:
                await asyncio.sleep(max(1, monitor_interval_seconds))
                session_age_seconds: int | None = None
                if session_started_at is not None:
                    session_age_seconds = int(asyncio.get_running_loop().time() - session_started_at)

                logger.info(
                    "Monitor snapshot",
                    connected=self.connected,
                    event_counts=self.event_counts,
                    session_age_seconds=session_age_seconds,
                )

                if session_age_seconds is None:
                    continue

                if not renewal_emitted and session_age_seconds >= nova_session_warn_seconds:
                    renewal_emitted = True
                    logger.warning(
                        "Nova Sonic session renewal recommended",
                        session_age_seconds=session_age_seconds,
                        warn_after_seconds=nova_session_warn_seconds,
                        limit_seconds=nova_session_limit_seconds,
                    )
                    await self._emit(
                        {
                            "event": "session_renewal_recommended",
                            "session_id": self.session_id,
                            "session_age_seconds": session_age_seconds,
                            "warn_after_seconds": nova_session_warn_seconds,
                            "limit_seconds": nova_session_limit_seconds,
                            "recommended_action": "Call POST /leave then POST /join to refresh session",
                        }
                    )
                if (
                    nova_stop_on_limit
                    and not renewal_stop_triggered
                    and session_age_seconds >= nova_session_limit_seconds
                ):
                    renewal_stop_triggered = True
                    self.last_error = "Nova Sonic session duration limit reached; renew with /leave then /join"
                    logger.warning(
                        "Stopping pipeline at Nova Sonic session limit",
                        session_age_seconds=session_age_seconds,
                        limit_seconds=nova_session_limit_seconds,
                    )
                    await self._emit(
                        {
                            "event": "session_renewal_required",
                            "session_id": self.session_id,
                            "session_age_seconds": session_age_seconds,
                            "limit_seconds": nova_session_limit_seconds,
                            "error": self.last_error,
                        }
                    )
                    cancel_result = self._pipeline_task.cancel()
                    if inspect.isawaitable(cancel_result):
                        await cancel_result
                    return

        if monitor_enabled:
            self._monitor_task = asyncio.create_task(monitor_loop())

        @transport.event_handler("on_joined")
        async def on_joined(_transport, data):
            nonlocal session_started_at
            self.connected = True
            session_started_at = asyncio.get_running_loop().time()
            logger.info("Joined session", session_id=data.get("sessionId"), model=bedrock_model_id)
            await self._emit({"event": "joined", "session_id": data.get("sessionId")})

        @transport.event_handler("on_participant_joined")
        async def on_participant_joined(_transport, data):
            self.event_counts["participant_joined"] += 1
            logger.info("Participant joined", stream_id=data.get("streamId"))
            await self._emit({
                "event": "participant_joined",
                "stream_id": data.get("streamId"),
                "connection_data": data.get("connectionData"),
            })
            await seed_initial_context("on_participant_joined")

        @transport.event_handler("on_participant_left")
        async def on_participant_left(_transport, data):
            self.event_counts["participant_left"] += 1
            logger.info("Participant left", stream_id=data.get("streamId"))
            await self._emit({
                "event": "participant_left",
                "stream_id": data.get("streamId"),
                "connection_data": data.get("connectionData"),
            })

        @transport.event_handler("on_client_connected")
        async def on_client_connected(_transport, data):
            self.event_counts["client_connected"] += 1
            logger.info("Client connected", subscriber_id=data.get("subscriberId"))
            await self._emit({"event": "client_connected", "subscriber_id": data.get("subscriberId")})
            await seed_initial_context("on_client_connected")

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(_transport, data):
            self.event_counts["client_disconnected"] += 1
            logger.info("Client disconnected", subscriber_id=data.get("subscriberId"))
            await self._emit({"event": "client_disconnected", "subscriber_id": data.get("subscriberId")})

        @transport.event_handler("on_left")
        async def on_left(_transport, data):
            self.connected = False
            logger.info("Left session", session_id=data.get("sessionId"))
            await self._emit({"event": "left", "session_id": data.get("sessionId")})

        @transport.event_handler("on_error")
        async def on_error(_transport, error):
            self.event_counts["errors"] += 1
            self.last_error = str(error)
            logger.error("Transport error", error=error)
            await self._emit({"event": "agent_error", "error": self.last_error})

        logger.info(
            "Pipeline starting",
            session_id=self.session_id,
            aws_region=aws_region,
            model=bedrock_model_id,
            aws_profile=aws_profile or None,
            agentcore_bootstrap_enabled=bool(agentcore_runtime_arn),
            agentcore_bootstrap_applied=bool(bootstrap_message),
            initial_message_seeded=bool(initial_user_message),
        )
        await self._emit({
            "event": "agent_starting",
            "session_id": self.session_id,
            "model": bedrock_model_id,
            "region": aws_region,
            "agentcore_bootstrap_enabled": bool(agentcore_runtime_arn),
            "agentcore_bootstrap_applied": bool(bootstrap_message),
        })

        self._runner = PipelineRunner()
        try:
            await self._runner.run(self._pipeline_task)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("Pipeline execution failed")
            await self._emit({"event": "agent_error", "error": self.last_error})
