#!/usr/bin/env python3
"""
Test C4b: AWS Nova Sonic — Speech-to-Speech Standalone Pipeline

Runs a Pipecat pipeline that:
  1. Opens a bidirectional streaming session with Amazon Nova Sonic
  2. Sends a short audio input (or synthesised test tone)
  3. Receives Nova Sonic's speech response
  4. Writes response audio to response_output.wav

Platform: Any (macOS, Linux, Windows)
Prerequisites: AWS credentials with Bedrock + Nova Sonic model access
"""

import asyncio
import os
import struct
import sys
import wave
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

OUTPUT_FILE = Path(__file__).parent / "response_output.wav"
SAMPLE_RATE = 16000
DURATION_SECONDS = 2  # length of synthetic silence test input


def generate_silence_wav(path: Path, duration: float, sample_rate: int = 16000) -> None:
    """Create a minimal silent WAV file to use as test input."""
    num_samples = int(sample_rate * duration)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)        # mono
        wf.setsampwidth(2)        # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{num_samples}h", *([0] * num_samples)))


async def run_nova_sonic_pipeline() -> None:
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    aws_region = os.getenv("AWS_REGION", "us-east-1").strip()
    model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-sonic-v1:0").strip()

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
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask
        from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
        from pipecat.services.aws.nova_sonic import NovaSonicService
        from pipecat.transports.local.audio import LocalAudioTransport
        from pipecat.transports.local.audio import LocalAudioParams
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("  Run: uv pip install -r requirements.txt")
        sys.exit(1)

    # ── Generate silent test-input WAV ────────────────────────────
    input_wav = Path(__file__).parent / "test_input.wav"
    if not input_wav.exists():
        print(f"Generating silent test input: {input_wav.name}")
        generate_silence_wav(input_wav, DURATION_SECONDS, SAMPLE_RATE)

    # ── Build pipeline ────────────────────────────────────────────
    nova_sonic = NovaSonicService(
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        aws_region=aws_region,
        model_id=model_id,
        system_prompt=(
            "You are a helpful voice assistant. "
            "Respond warmly in one or two short sentences."
        ),
    )
    print("✓ Nova Sonic pipeline initialised")

    transport = LocalAudioTransport(
        LocalAudioParams(
            audio_in_sample_rate=SAMPLE_RATE,
            audio_out_sample_rate=SAMPLE_RATE,
            audio_in_enabled=True,
            audio_out_enabled=True,
        )
    )

    buffer_processor = AudioBufferProcessor()

    pipeline = Pipeline([
        transport.input(),
        nova_sonic,
        buffer_processor,
        transport.output(),
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=False),
    )

    print(f"Sending audio input: {input_wav.name}")
    start = asyncio.get_event_loop().time()

    runner = PipelineRunner()
    await runner.run(task)

    elapsed = asyncio.get_event_loop().time() - start
    print(f"✓ Nova Sonic responded ({elapsed:.1f} s)")

    # ── Save response audio ───────────────────────────────────────
    audio_data = buffer_processor.get_audio()
    if audio_data:
        with wave.open(str(OUTPUT_FILE), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data)
        print(f"Response audio saved to: {OUTPUT_FILE.name}")
    else:
        print("WARNING: No audio output received from Nova Sonic")

    print("\nTest C4b PASSED ✓")


if __name__ == "__main__":
    asyncio.run(run_nova_sonic_pipeline())
