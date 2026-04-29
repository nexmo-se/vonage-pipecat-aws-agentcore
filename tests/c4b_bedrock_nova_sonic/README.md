# C4b — AWS Bedrock + Nova Sonic + Vonage Pipecat Transport Integration

Two-stage test that validates AWS Bedrock integration with the Vonage Video transport (building on C3):

**Stage 1:** Verify AWS Bedrock credentials and Nova Lite text model access (prerequisite for Stage 2)  
**Stage 2:** Integrate AWS Bedrock LLM with Vonage Pipecat transport for end-to-end session validation

This paves the way for C5 (AgentCore full-stack runtime) by proving Bedrock API access and Vonage session lifecycle with external AI service.

**Platform:** Linux only (Bedrock echo agent). Run via Docker on macOS — see setup below.

## What is AWS Bedrock and Nova Sonic?

**AWS Bedrock** is a managed foundation model service that provides:

- **Foundation models:** Access to multiple LLM and multimodal models from AWS and partners.
- **API-based inference:** No server management; invoke models via simple API calls.
- **Pay-per-use:** No upfront costs; pay only for inference consumption.

**Amazon Nova Sonic** (used in this project) is a lightweight, low-latency speech-to-speech model that:

- Listens to incoming audio (STT).
- Generates response text or passes it through an LLM.
- Synthesizes response audio (TTS).
- Operates at low latency suitable for real-time conversations (~200–400 ms for STT, ~100–200 ms for TTS).

In this project:

- Bedrock hosts the LLM (Nova Lite for text generation, Nova Sonic for speech-to-speech).
- Pipecat calls Bedrock API to process transcribed text and generate responses.
- Nova Sonic handles speech input/output, compressing the typical STT → LLM → TTS pipeline.

## Bedrock vs AgentCore (Why Both?)

C4b focuses on **Bedrock model inference**, not AgentCore runtime hosting.

- **Bedrock in C4b:** verifies credentials, model access, and live inference behavior.
- **AgentCore in C5:** verifies deployable runtime logic (configure/deploy/invoke) and optional bootstrap integration.

If C4b passes, your model layer is working. If C5 passes, your managed runtime layer is working.

Short version: **Bedrock answers; AgentCore runs deployable agent app logic.**

## Purpose

This C4b test validates that:

- AWS Bedrock credentials are correctly configured.
- Nova Sonic models are available and accessible.
- An end-to-end agent can listen to speech, generate a response, and speak back—all via Bedrock APIs.
- Real-time latency with a production AI model is acceptable.

**Stage 1** (credential validation) checks that Bedrock API is reachable and Nova Lite model access is enabled.  
**Stage 2** (echo agent) runs a real conversational agent on Vonage sessions with Bedrock inference.

When complete, you can ask the agent a question in the Vonage Playground, and it responds naturally with AI-generated speech backed by real Bedrock models.

---

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- AWS account with IAM credentials and Bedrock model access
- Vonage Video API credentials (from C1) with active session ID
- **Model Access Required:**
  - `amazon.nova-lite-v1:0` (for credential test in Stage 1)
  - `amazon.nova-2-sonic-v1:0` (for echo agent in Stage 2)
  - Enable models in [Bedrock console](https://console.aws.amazon.com/bedrock/home#/modelaccess) — us-east-1 recommended

---

## Setup

### macOS (Docker)

```bash
cd tests/c4b_bedrock_nova_sonic

# Build Dockerfile (includes git for Pipecat source install, Python 3.13, boto3, Vonage SDK)
docker build -t c4b-bedrock-nova-sonic .

# Ensure root .env has AWS_PROFILE set
# (or AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY for explicit credentials)
```

### Native Linux

```bash
cd tests/c4b_bedrock_nova_sonic

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# or with uv: uv venv && uv pip install -r requirements.txt
```

---

## Stage 1: Credential Test

Verify AWS Bedrock access is correctly configured.

### Run

```bash
# macOS (Docker)
docker run --rm -e AWS_PROFILE=vonage-dev \
  -e AWS_REGION=us-east-1 \
  -v ~/.aws:/root/.aws \
  -v "$(pwd)/../../.env:/workspace/.env:ro" \
  c4b-bedrock-nova-sonic python test_bedrock.py

# Native Linux
source .venv/bin/activate
python test_bedrock.py
```

### Expected Output

```text
✓ Using AWS profile: vonage-dev (region: us-east-1)
✓ Bedrock client initialised
✓ Model access verified: amazon.nova-lite-v1:0

Sending test prompt: "Say hello in exactly one sentence."
✓ Response received:
  Hello! I'm Nova Lite, an AI assistant — how can I help you today?

Test C4b PASSED ✓
```

### What It Tests

| Step           | Description                                                                   |
| -------------- | ----------------------------------------------------------------------------- |
| Credentials    | Confirms `AWS_PROFILE` or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` valid |
| Model listing  | Calls `ListFoundationModels` to verify Bedrock API access                     |
| Text inference | Calls `InvokeModel` with Nova Lite and a simple prompt                        |

---

## Stage 2: Bedrock Echo Agent (Vonage Integration)

Combines C3 Pipecat transport with AWS Bedrock LLM for end-to-end validation.

### File Overview

| File                               | Purpose                                                                   |
| ---------------------------------- | ------------------------------------------------------------------------- |
| `test_bedrock.py`                  | Stage 1: AWS credential & model access verification                       |
| `bedrock_transport_integration.py` | Bedrock client wrapper + LLM invocation helper classes                    |
| `bedrock_echo_agent.py`            | Stage 2: Vonage transport + Bedrock LLM integration (echo bot)            |
| `Dockerfile`                       | Linux runtime: Python 3.13, git, system dependencies for Pipecat SDK      |
| `requirements.txt`                 | Dependencies: boto3, Pipecat, Vonage Video SDK, python-dotenv, websockets |

### Configuration

Set in root `.env`:

```env
# Vonage Video (from C1)
VONAGE_APPLICATION_ID=<your-app-id>
VONAGE_PRIVATE_KEY=private.key
VONAGE_SESSION_ID=<session-from-c1>

# AWS Bedrock
AWS_PROFILE=vonage-dev            # or use AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=amazon.nova-2-sonic-v1:0
BEDROCK_INITIAL_USER_MESSAGE=Please greet the participant briefly and ask how you can help.

# Transport tuning (optional, defaults align with C3 best practices)
VONAGE_VIDEO_CONNECTOR_LOG_LEVEL=INFO
VONAGE_MONITOR_ENABLED=true
VONAGE_MONITOR_INTERVAL_SECONDS=15
```

Set `BEDROCK_INITIAL_USER_MESSAGE=` (empty) to disable the initial greeting.

### Run Stage 2

```bash
# macOS (Docker with host .aws credentials)
docker run --rm \
  -e AWS_PROFILE=vonage-dev \
  -e AWS_REGION=us-east-1 \
  -v ~/.aws:/root/.aws \
  -v "$(pwd)/../../.env:/workspace/.env:ro" \
  -v "$(pwd)/../../private.key:/workspace/private.key:ro" \
  c4b-bedrock-nova-sonic python bedrock_echo_agent.py

# Native Linux (assumes VONAGE_SESSION_ID is set in root .env)
source .venv/bin/activate
python bedrock_echo_agent.py
```

### Validated Run Flow (Recommended)

Use this exact flow for reproducible results:

```bash
cd tests/c4b_bedrock_nova_sonic

# 1) Build latest image
docker build -t c4b-bedrock-nova-sonic .

# 2) Clear previous log
rm -f c4b-bedrock-nova-sonic-echo.log

# 3) Start agent and capture output
docker run --rm \
  -e AWS_PROFILE=vonage-dev \
  -e AWS_REGION=us-east-1 \
  -e BEDROCK_MODEL_ID=amazon.nova-2-sonic-v1:0 \
  -e VONAGE_MONITOR_ENABLED=true \
  -e VONAGE_MONITOR_INTERVAL_SECONDS=10 \
  -v ~/.aws:/root/.aws:ro \
  -v "$(pwd)/../../.env:/workspace/.env:ro" \
  -v "$(pwd)/../../private.key:/workspace/private.key:ro" \
  -v "$(pwd)/logs:/app/logs" \
  c4b-bedrock-nova-sonic python bedrock_echo_agent.py 2>&1 | tee c4b-bedrock-nova-sonic-echo.log
```

Then in Vonage Playground:

1. Open [https://tokbox.com/developer/tools/playground/](https://tokbox.com/developer/tools/playground/)
2. Log in to the Vonage account that owns your `VONAGE_APPLICATION_ID`
3. Join an existing session using the same session ID from `.env`
4. Publish mic/audio
5. Speak for 10-20 seconds
6. Confirm you hear assistant audio
7. Press Ctrl+C to stop the agent

### Expected Runtime Output (Stage 2)

```text
Initializing Nova Sonic (amazon.nova-2-sonic-v1:0) in us-east-1…
Initialising Vonage Pipecat transport for session 2_MX...…
✓ Connected to Vonage Video session 2_MX...
✓ Nova Sonic (amazon.nova-2-sonic-v1:0) ready for participant interactions

Pipecat pipeline with Nova Sonic running — speak into your browser microphone
  Audio received → Nova Sonic processes → spoken response published back
  Transport config: log_level=INFO, audio_in=true, audio_out=true, …
  AI config: model=amazon.nova-2-sonic-v1:0, region=us-east-1
Press Ctrl+C to stop.
```

### End-to-End Validation Workflow

Same workflow as C3, with LLM processing:

1. **Start C4b agent** (Docker or native)
2. **Join [Vonage Playground](https://tokbox.com/developer/tools/playground/)**

- Log in to the Vonage account that owns your `VONAGE_APPLICATION_ID`
- Use the same session ID from `.env`
- Enable camera + microphone

1. **Publish video/audio**
1. **Speak into microphone** (text will be processed through Bedrock LLM)
1. **Wait 5-10 seconds** for LLM response + echo
1. **Unpublish, then disconnect** from Playground
1. **Stop agent** (Ctrl+C)
1. **Verify logs** for success signals (see below)

### Verify Success from Logs

```bash
# Check key markers from the latest run
grep -a -n -E "Seeding initial Nova Sonic context|Finishing connecting|on_client_connected|ERROR|Exception" c4b-bedrock-nova-sonic-echo.log

# If your log includes binary segments, use strings extraction first
strings -n 4 c4b-bedrock-nova-sonic-echo.log | grep -n -E "Seeding initial Nova Sonic context|Finishing connecting|on_client_connected|ERROR|Exception"
```

### Success Checklist

- [ ] Agent connects to Vonage session (logs: "Connected to Vonage Video session")
- [ ] Nova Sonic initialized (logs: "Nova Sonic (...) ready")
- [ ] Participant joins from Playground (logs: "Participant joined")
- [ ] Client connects (logs: "Client connected")
- [ ] Monitor shows active_streams > 0 (logs: "monitor: active_streams=1")
- [ ] Participant speaks → assistant audio returns (audio loop confirmed)
- [ ] Client disconnects (logs: "Client disconnected")
- [ ] Participant leaves (logs: "Participant left")
- [ ] Agent stops cleanly (Ctrl+C → "Test C4b Bedrock integration complete ✓")

---

## What This Stage Adds

| Component            | Purpose                                                                |
| -------------------- | ---------------------------------------------------------------------- |
| **Bedrock API**      | LLM invocation via AWS Bedrock Nova Sonic (same model as C5 AgentCore) |
| **Vonage Transport** | Session join + participant lifecycle (same as C3)                      |
| **Event handlers**   | Client connect/disconnect, participant join/leave tracking             |
| **Monitor loop**     | Periodic snapshots of active streams, subscribers, event counters      |
| **Async pipeline**   | PipelineRunner coordination with LLM invocation in parallel            |
| **Error handling**   | Transport + Bedrock error recovery, graceful shutdown                  |

---

## Troubleshooting

| Error                          | Fix                                                                                                |
| ------------------------------ | -------------------------------------------------------------------------------------------------- |
| `NoCredentialsError`           | Set `AWS_PROFILE` or `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` in env                          |
| `AccessDeniedException`        | Enable model access in [Bedrock console](https://console.aws.amazon.com/bedrock/home#/modelaccess) |
| `EndpointResolutionError`      | Check `AWS_REGION` — Bedrock may not be available in all regions                                   |
| `ModuleNotFoundError: pipecat` | Run: `pip install -r requirements.txt` (Pipecat from Git source)                                   |
| `Session ID not found`         | Set `VONAGE_SESSION_ID` in root `.env` (from C1)                                                   |
| `Private key not found`        | Ensure `private.key` exists in repo root with valid Vonage key                                     |
| Docker build fails (git)       | Dockerfile includes `apt-get install git` for Git-based Pipecat install                            |

---

## Next Steps

- **C5:** Validate AgentCore runtime deployment and invocation against this transport path
- **App:** Run full app integration with Bedrock + Vonage transport + optional AgentCore bootstrap
- **Monitoring:** Extend C4b to log all Bedrock invocations (prompts, responses, latency) for observability

---

## References

- [AWS Bedrock Nova Models](https://aws.amazon.com/bedrock/nova/)
- [Vonage Video Pipecat Transport Docs](https://developer.vonage.com/en/video/guides/vonage-video-connector-pipecat-transport)
- [Pipecat GitHub](https://github.com/Vonage/pipecat)
