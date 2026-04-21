#!/usr/bin/env python3
"""
agent.py — Pipecat pipeline: Vonage ↔ Nova Sonic ↔ AgentCore

This module owns the long-running Pipecat pipeline that:
  1. Joins the Vonage Video session as a WebRTC participant
  2. Receives audio from browser participants via VonageTransport
  3. Processes speech through AWS Nova Sonic (STT + LLM + TTS)
  4. Sends synthesised speech back into the session
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import structlog
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = structlog.get_logger(__name__)


class VonagePipecatAgent:
    """Manages the Pipecat pipeline lifecycle for a single Vonage session."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._runner = None
        self._pipeline_task = None
        self.session_id: str = os.getenv("VONAGE_SESSION_ID", "")
        self.connected: bool = False

    # ── Public interface ──────────────────────────────────────────

    async def start(self) -> None:
        """Build and start the Pipecat pipeline."""
        if self._task and not self._task.done():
            logger.warning("Agent already running")
            return
        self._task = asyncio.create_task(self._run_pipeline())

    async def stop(self) -> None:
        """Stop the pipeline and disconnect from the session."""
        if self._pipeline_task:
            try:
                await self._pipeline_task.cancel()
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.connected = False
        logger.info("Agent stopped")

    # ── Pipeline ──────────────────────────────────────────────────

    async def _run_pipeline(self) -> None:
        try:
            from vonage import Auth, Vonage
            from pipecat.pipeline.pipeline import Pipeline
            from pipecat.pipeline.runner import PipelineRunner
            from pipecat.pipeline.task import PipelineParams, PipelineTask
            from pipecat.processors.frameworks.vonage import VonageTransport
            from pipecat.audio.vad.silero import SileroVADAnalyzer
            from pipecat.services.aws.nova_sonic import NovaSonicService
            from pipecat.services.aws.agentcore import AgentCoreService
        except ImportError as exc:
            logger.error("Missing dependency", error=str(exc))
            return

        application_id = os.getenv("VONAGE_APPLICATION_ID", "")
        private_key_path = os.getenv("VONAGE_PRIVATE_KEY", "private.key")
        aws_region = os.getenv("AWS_REGION", "us-east-1")
        model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-sonic-v1:0")
        agent_arn = os.getenv("AGENTCORE_AGENT_ARN", "")
        aws_access_key = os.getenv("AWS_ACCESS_KEY_ID", "")
        aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "")

        # Resolve private key path relative to repo root
        pk_file = Path(private_key_path)
        if not pk_file.is_absolute():
            pk_file = Path(__file__).resolve().parent.parent / private_key_path

        # Generate publisher token
        vonage_client = Vonage(
            Auth(application_id=application_id, private_key=str(pk_file))
        )
        token = vonage_client.video.generate_client_token(
            session_id=self.session_id,
            role="publisher",
            expire_time=7200,
        )
        logger.info("Publisher token generated", session_id=self.session_id)

        # Build pipeline components
        transport = VonageTransport(
            session_id=self.session_id,
            token=token,
            application_id=application_id,
            vad_analyzer=SileroVADAnalyzer(),
            params=VonageTransport.InputParams(audio_enabled=True),
        )

        nova_sonic = NovaSonicService(
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            aws_region=aws_region,
            model_id=model_id,
            system_prompt=(
                "You are a friendly, concise AI voice assistant. "
                "Keep responses brief and conversational."
            ),
        )

        agentcore = AgentCoreService(
            agent_arn=agent_arn,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            aws_region=aws_region,
        )

        pipeline = Pipeline([
            transport.input(),   # Audio in from Vonage session
            nova_sonic.stt(),    # Speech → text
            agentcore,           # LLM reasoning via AgentCore
            nova_sonic.tts(),    # Text → speech
            transport.output(),  # Audio out to Vonage session
        ])

        self._pipeline_task = PipelineTask(
            pipeline,
            params=PipelineParams(allow_interruptions=True),
        )

        @transport.event_handler("on_participant_joined")
        async def on_joined(transport, participant):
            logger.info("Participant joined", participant_id=participant.get("id"))
            self.connected = True

        @transport.event_handler("on_participant_left")
        async def on_left(transport, participant, reason):
            logger.info("Participant left", participant_id=participant.get("id"))

        logger.info("Pipeline started", session_id=self.session_id)
        self._runner = PipelineRunner()
        await self._runner.run(self._pipeline_task)
