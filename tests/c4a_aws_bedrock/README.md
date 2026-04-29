# C4a — AWS Bedrock Credentials + Vonage Transport Connectivity

Two-stage test that validates the AWS and Vonage layers separately before combining them with Nova Sonic in C4b:

**Stage 1:** Verify AWS Bedrock credentials and Nova Lite text model access (pure credential check, no transport)  
**Stage 2:** Verify Vonage transport session connectivity in the Bedrock-configured Docker environment (pure audio echo, no LLM invocation)

This paves the way for C4b by proving both layers independently: Bedrock credentials work (Stage 1) and the Vonage transport joins and routes audio correctly (Stage 2).

**Platform:** Linux only (Bedrock echo agent). Run via Docker on macOS — see setup below.

---

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- AWS account with IAM credentials and Bedrock model access
- Vonage Video API credentials (from C1) with active session ID
- **Model Access Required:**
  - `amazon.nova-lite-v1:0` (for credential test in Stage 1)
  - Enable model access in [Bedrock console](https://console.aws.amazon.com/bedrock/home#/modelaccess) — us-east-1 recommended

---

## Setup

### macOS (Docker)

```bash
cd tests/c4a_aws_bedrock

# Build Dockerfile (includes git for Pipecat source install, Python 3.13, boto3, Vonage SDK)
docker build -t c4a-bedrock .

# Ensure root .env has AWS_PROFILE set
# (or AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY for explicit credentials)
```

### Native Linux

```bash
cd tests/c4a_aws_bedrock

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
  c4a-bedrock python test_bedrock.py

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

Test C4a PASSED ✓
```

### What It Tests

| Step           | Description                                                                   |
| -------------- | ----------------------------------------------------------------------------- |
| Credentials    | Confirms `AWS_PROFILE` or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` valid |
| Model listing  | Calls `ListFoundationModels` to verify Bedrock API access                     |
| Text inference | Calls `InvokeModel` with Nova Lite and a simple prompt                        |

---

## Stage 2: Transport Echo (Vonage Session Connectivity)

Runs a Pipecat pipeline in the Bedrock-configured Docker environment to validate Vonage session join, participant lifecycle, and audio round-trip.

**Pipeline:** `transport.input() → transport.output()` — audio is echoed directly back with no LLM processing. This is the same transport pattern as C3, but running inside the c4a Docker image that will be extended with Nova Sonic in C4b.

### File Overview

| File                               | Purpose                                                                   |
| ---------------------------------- | ------------------------------------------------------------------------- |
| `test_bedrock.py`                  | Stage 1: AWS credential & model access verification                       |
| `bedrock_transport_integration.py` | Bedrock client wrapper + LLM invocation helper classes                    |
| `bedrock_echo_agent.py`            | Stage 2: Vonage transport echo (session join + audio round-trip, no LLM)  |
| `Dockerfile`                       | Linux runtime: Python 3.13, git, system dependencies for Pipecat SDK      |
| `requirements.txt`                 | Dependencies: boto3, Pipecat, Vonage Video SDK, python-dotenv, websockets |

### Configuration

Set in root `.env`:

```env
# Vonage Video (from C1)
VONAGE_APPLICATION_ID=<your-app-id>
VONAGE_PRIVATE_KEY=private.key
VONAGE_SESSION_ID=<session-from-c1>

# AWS credentials (profile recommended)
AWS_PROFILE=vonage-dev            # or use AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY
AWS_REGION=us-east-1

# Transport tuning (optional)
VONAGE_VIDEO_CONNECTOR_LOG_LEVEL=INFO
VONAGE_MONITOR_ENABLED=true
VONAGE_MONITOR_INTERVAL_SECONDS=15
```

### Run Stage 2

```bash
# macOS (Docker with host .aws credentials)
docker run --rm \
  -e AWS_PROFILE=vonage-dev \
  -e AWS_REGION=us-east-1 \
  -v ~/.aws:/root/.aws \
  -v "$(pwd)/../../.env:/workspace/.env:ro" \
  -v "$(pwd)/../../private.key:/workspace/private.key:ro" \
  c4a-bedrock python bedrock_echo_agent.py

# Native Linux (assumes VONAGE_SESSION_ID is set in root .env)
source .venv/bin/activate
python bedrock_echo_agent.py
```

### Validated Run Flow (Recommended)

Use this exact flow for reproducible results:

```bash
cd tests/c4a_aws_bedrock

# 1) Build latest image
docker build -t c4a-bedrock .

# 2) Clear previous log
rm -f c4a-bedrock-echo.log

# 3) Start agent and capture output
docker run --rm \
  -e AWS_PROFILE=vonage-dev \
  -e AWS_REGION=us-east-1 \
  -e VONAGE_MONITOR_ENABLED=true \
  -e VONAGE_MONITOR_INTERVAL_SECONDS=10 \
  -v ~/.aws:/root/.aws:ro \
  -v "$(pwd)/../../.env:/workspace/.env:ro" \
  -v "$(pwd)/../../private.key:/workspace/private.key:ro" \
  -v "$(pwd)/logs:/app/logs" \
  c4a-bedrock python bedrock_echo_agent.py 2>&1 | tee c4a-bedrock-echo.log
```

Then in Vonage Playground:

1. Open [https://tokbox.com/developer/tools/playground/](https://tokbox.com/developer/tools/playground/)
2. Log in to the Vonage account that owns your `VONAGE_APPLICATION_ID`
3. Join the existing session using `VONAGE_SESSION_ID` from `.env`
4. Publish mic/audio
5. Speak — you should hear your own audio echoed back within ~1 second
6. Press Ctrl+C to stop the agent

### Expected Runtime Output (Stage 2)

```text
Initializing Bedrock LLM (amazon.nova-2-sonic-v1:0) in us-east-1…
Initialising Vonage Pipecat transport for session 2_MX...…
✓ Connected to Vonage Video session 2_MX...
✓ Bedrock LLM (amazon.nova-2-sonic-v1:0) ready for participant interactions

Pipecat transport echo running — speak into your browser microphone
  Audio received → echoed back directly (no LLM — transport connectivity test)
  Transport config: log_level=INFO, audio_in=True, audio_out=True, …
  Env: model=amazon.nova-2-sonic-v1:0, region=us-east-1 (model unused in Stage 2)
Press Ctrl+C to stop.
```

> Note: The pipeline is `transport.input() → transport.output()`. Audio is echoed back directly — no Bedrock model inference occurs during Stage 2. LLM inference is added in C4b.

### End-to-End Validation Workflow

Same workflow as C3 — this is a transport echo with no LLM processing:

1. **Start C4a agent** (Docker or native)
2. **Join [Vonage Playground](https://tokbox.com/developer/tools/playground/)**
   - Log in to the Vonage account that owns your `VONAGE_APPLICATION_ID`
   - Use `VONAGE_SESSION_ID` from `.env`
   - Enable camera + microphone
3. **Publish audio**
4. **Speak into microphone** — audio is echoed back directly (no LLM, ~1 s round-trip)
5. **Unpublish, then disconnect** from Playground
6. **Stop agent** (Ctrl+C)
7. **Verify logs** for success signals (see below)

### Verify Success from Logs

```bash
# Check key markers from the latest run
grep -a -n -E "Connected to Vonage|Bedrock LLM.*ready|Participant joined|Client connected|monitor: active_streams|ERROR|Exception" c4a-bedrock-echo.log

# If your log includes binary segments, use strings extraction first
strings -n 4 c4a-bedrock-echo.log | grep -n -E "Connected to Vonage|Bedrock LLM.*ready|Participant joined|Client connected|monitor: active_streams|ERROR|Exception"
```

### Success Checklist

- [ ] Agent connects to Vonage session (logs: "Connected to Vonage Video session")
- [ ] Bedrock LLM initialized (logs: "Bedrock LLM (...) ready for participant interactions")
- [ ] Participant joins from Playground (logs: "Participant joined with stream")
- [ ] Client connects (logs: "Client connected to stream")
- [ ] Monitor shows active_streams > 0 (logs: "monitor: active_streams=1")
- [ ] Participant speaks → audio echoed back within ~1 second (no LLM delay)
- [ ] Client disconnects (logs: "Client disconnected from stream")
- [ ] Participant leaves (logs: "Participant left stream")
- [ ] Agent stops cleanly (Ctrl+C → "Test C4a Bedrock integration complete ✓")

---

## What This Stage Adds

| Component            | Purpose                                                                    |
| -------------------- | -------------------------------------------------------------------------- |
| **Vonage Transport** | Session join + participant lifecycle in the Bedrock-configured environment |
| **Audio echo**       | `transport.input() → transport.output()` — confirms audio round-trip works |
| **Event handlers**   | Client connect/disconnect, participant join/leave tracking                 |
| **Monitor loop**     | Periodic snapshots of active streams, subscribers, event counters          |
| **Error handling**   | Transport error recovery, graceful shutdown on Ctrl+C                      |

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

- **C4b:** Run the integrated Bedrock + Nova Sonic + Vonage transport test in `tests/c4b_bedrock_nova_sonic`
- **C5:** Full AgentCore integration with Bedrock + Vonage transport for multi-turn context
- **Monitoring:** Extend C4a to log all Bedrock invocations (prompts, responses, latency) for observability

---

## References

- [AWS Bedrock Nova Models](https://aws.amazon.com/bedrock/nova/)
- [Vonage Video Pipecat Transport Docs](https://developer.vonage.com/en/video/guides/vonage-video-connector-pipecat-transport)
- [Pipecat GitHub](https://github.com/Vonage/pipecat)
