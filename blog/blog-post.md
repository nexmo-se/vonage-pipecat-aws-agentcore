# Building Real-Time AI Voice Agents with Vonage, Pipecat, and AWS Bedrock AgentCore

> **TL;DR** — This post walks through building a production-ready AI voice agent that joins a Vonage video call, listens to participants, reasons using AWS Bedrock AgentCore, and responds using Amazon Nova Sonic — all in real time.

---

## Introduction

Conversational AI has moved from text chatbots to real-time voice agents that can participate in video calls just like a human colleague. In this post I'll show you how to wire together three powerful platforms:

1. **Vonage Video API + Video Connector SDK** — letting a Python server join a WebRTC video session as a first-class audio/video participant
2. **Pipecat AI** — an open-source framework for building real-time audio/video pipelines
3. **AWS Bedrock with Amazon Nova Sonic** — a speech-to-speech model that handles STT, LLM reasoning, and TTS in a single low-latency API call
4. **AWS Bedrock AgentCore Runtime** — a managed runtime for deploying and scaling AI agents

By the end you'll have a working agent that:

- Joins a Vonage video session
- Listens to participants in real time
- Generates intelligent responses via AgentCore
- Speaks back using Nova Sonic's natural TTS

---

## Architecture Overview

```text
Browser (mic/speaker)
        │  WebRTC
        ▼
Vonage Video Platform
        │  WebRTC via Video Connector SDK
        ▼
┌──────────────────────────────────────────────────┐
│  Python Agent (Docker / Linux)                   │
│                                                  │
│  Pipecat Pipeline                                │
│  VonageTransport ──► NovaSonic ──► AgentCore     │
│                  ◄── NovaSonic ◄──               │
│                                                  │
│  FastAPI management API (:8000)                  │
└──────────────────────────────────────────────────┘
```

The pipeline is fully streaming — audio frames flow through each stage without buffering entire utterances, keeping end-to-end latency well below a second.

---

## Prerequisites

- A [Vonage account](https://dashboard.nexmo.com) with a Video API application
- An AWS account with Bedrock model access (Nova Sonic + Nova Lite)
- Docker (for running the Linux-native Video Connector SDK on macOS)
- Python 3.11+ and [uv](https://docs.astral.sh/uv/)

---

## Step 1 — Vonage Video Session (Test C1)

Before running any code, create a Vonage Video application in the dashboard, download the `private.key`, and note your Application ID.

```bash
cd tests/c1_vonage_video_session
uv venv && uv pip install -r requirements.txt
uv run python test_session.py
```

This creates a video session and prints a playground URL. Open it in a browser — you'll see your own webcam. This browser tab provides the audio that the AI agent will listen to in later steps.

The script also prints the `VONAGE_SESSION_ID` — copy this into your `.env` file.

---

## Step 2 — Video Connector SDK (Test C2)

The Vonage Video Connector SDK allows a server-side Linux process to join a WebRTC session as a native participant — sending and receiving audio/video. It is the bridge between the Vonage cloud and your Python agent.

```bash
# macOS users — run inside Docker:
docker compose run --rm --build c2-video-connector
```

When this test passes you should see a second participant thumbnail appear in your browser tab.

---

## Step 3 — Pipecat Echo Bot (Test C3)

With the transport layer verified, we add Pipecat on top. This test runs a simple echo bot — it captures audio from the browser participant, runs it through a voice-activity detector, and plays it back.

```bash
docker compose run --rm --build c3-pipecat-transport
```

Speak into your browser microphone. After a short pause you should hear your own voice echoed back through the session. This confirms the full Pipecat ↔ Vonage round-trip is working.

---

## Step 4 — AWS Bedrock + Nova Sonic (Test C4)

```bash
cd tests/c4_bedrock_nova_sonic
uv venv && uv pip install -r requirements.txt
uv run python test_bedrock.py           # Stage 1: Credential verification
uv run python bedrock_echo_agent.py     # Stage 2: Bedrock + Vonage integration
```

This combined test validates your AWS credentials with **Amazon Nova Lite** (fast, lightweight text model for sanity check), then moves to **Nova Sonic** — Amazon's speech-to-speech model that accepts raw audio, reasons internally, and returns synthesised speech, removing the need for separate STT and TTS services.

The test sends a short silent WAV and receives a response audio file. Play `response_output.wav` to verify Nova Sonic is working.

---

## Step 5 — AgentCore Runtime (Test C5)

AWS Bedrock AgentCore lets you deploy an AI agent as a managed, serverless endpoint. The test creates a hello-world agent, invokes it, and cleans up.

```bash
cd tests/c5_agentcore
uv venv && uv pip install -r requirements.txt
uv run python test_agentcore.py
```

Copy the agent ARN into `AGENTCORE_AGENT_ARN` in your `.env` for use by the full app.

---

## Step 6 — Full Application

With all five tests passing, run the complete agent:

```bash
# macOS / non-Linux
docker compose --profile app up --build
```

The FastAPI server starts on port 8000. The agent automatically joins the session in `VONAGE_SESSION_ID` and listens for participants.

**Try it:** Open the Vonage playground URL from test C1 and say hello. The agent will respond in real time through Nova Sonic.

---

## Key Pipecat Pipeline Design

The pipeline in `app/agent.py` chains four stages:

```python
pipeline = Pipeline([
    transport.input(),   # Audio frames from Vonage WebRTC
    nova_sonic.stt(),    # Speech → text (streaming)
    agentcore,           # Text → AgentCore → text response
    nova_sonic.tts(),    # Text → synthesised speech (streaming)
    transport.output(),  # Audio frames back to Vonage WebRTC
])
```

Each stage processes Pipecat `Frame` objects asynchronously. Nova Sonic's streaming API means the TTS stage starts generating audio before the full LLM response is complete — dramatically reducing perceived latency.

---

## Deployment Considerations

- **Linux requirement** — The Vonage Video Connector SDK is a native Linux binary. Use Docker on macOS for development; deploy to a Linux VM or container for production.
- **AgentCore scaling** — AgentCore Runtime handles scaling automatically. Each session creates an independent agent invocation.
- **Credentials** — Never commit `.env` or `private.key` to source control. Use AWS Secrets Manager or environment injection in production.
- **Nova Sonic pricing** — Billed per second of audio processed. The pipeline's VAD (voice activity detection) ensures the model is only called when a participant is speaking.

---

## Conclusion

In this post we built a real-time AI voice agent that:

✅ Joins a Vonage WebRTC video session as a server-side participant  
✅ Processes speech with Amazon Nova Sonic (STT + LLM + TTS in one call)  
✅ Delegates reasoning to AWS Bedrock AgentCore Runtime  
✅ Returns synthesised audio in near real time

The complete source code is available at [github.com/nexmo-se/vonage-pipecat-aws-agentcore](https://github.com/nexmo-se/vonage-pipecat-aws-agentcore).

---

## Official Vonage References

For implementation details and product behavior, use Vonage-authored documentation as the primary source:

- [Vonage Video API overview](https://developer.vonage.com/en/video/overview)
- [Vonage Video Python Server SDK docs](https://developer.vonage.com/en/video/server-sdks/python)
- [Vonage Python SDK repository](https://github.com/Vonage/vonage-python-sdk)
- [Vonage Python SDK Video API examples](https://github.com/Vonage/vonage-python-sdk/blob/main/video/README.md)
- [Vonage Video Connector guide](https://developer.vonage.com/en/video/guides/vonage-video-connector)
- [Vonage Pipecat transport guide](https://developer.vonage.com/en/video/guides/vonage-video-connector-pipecat-transport)
- [Vonage Audio Connector guide (serializer/WebSocket related)](https://developer.vonage.com/en/video/guides/audio-connector)
- [Vonage Voice API overview](https://developer.vonage.com/en/voice/overview)

---

## Credits

Built with care by the Vonage API CSE team.
