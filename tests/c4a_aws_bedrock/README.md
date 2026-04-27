# C4a — AWS Bedrock + Vonage Pipecat Transport Integration

Two-stage test that validates AWS Bedrock integration with the Vonage Video transport (building on C3):

**Stage 1:** Verify AWS Bedrock credentials and Nova Lite text model access (prerequisite for Stage 2)  
**Stage 2:** Integrate AWS Bedrock LLM with Vonage Pipecat transport for end-to-end session validation

This paves the way for C5 (AgentCore full-stack runtime) by proving Bedrock API access and Vonage session lifecycle with external AI service.

**Platform:** Linux only (Bedrock echo agent). Run via Docker on macOS — see setup below.

---

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- AWS account with IAM credentials and Bedrock model access
- Vonage Video API credentials (from C1) with active session ID
- **Model Access Required:**
  - `amazon.nova-lite-v1:0` (for credential test in Stage 1)
  - `amazon.nova-sonic-v1:0` (for echo agent in Stage 2)
  - Enable models in [Bedrock console](https://console.aws.amazon.com/bedrock/home#/modelaccess) — us-east-1 recommended

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

```
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
BEDROCK_MODEL_ID=amazon.nova-sonic-v1:0

# Transport tuning (optional, defaults align with C3 best practices)
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

### Expected Output

```
Initializing Bedrock LLM (amazon.nova-sonic-v1:0) in us-east-1…
Initialising Vonage Pipecat transport for session 2_MX4zZjI4NTlhYy01OWU4LTQ2YjEtODFiOS1hZjE2NWFhZTVkNjN-…
✓ Connected to Vonage Video session 2_MX4zZjI4NTlhYy01OWU4LTQ2YjEtODFiOS1hZjE2NWFhZTVkNjN-
✓ Bedrock LLM (amazon.nova-sonic-v1:0) ready for participant interactions

Pipecat pipeline with Bedrock LLM running — speak into your browser microphone
  Audio received → LLM processes → echoed back as audio
  Transport config: log_level=INFO, audio_in=true, audio_out=true, …
  LLM config: model=amazon.nova-sonic-v1:0, region=us-east-1
Press Ctrl+C to stop.
```

### End-to-End Validation Workflow

Same workflow as C3, with LLM processing:

1. **Start C4a agent** (Docker or native)
2. **Join [Vonage Playground](https://tools.vonage.com/video/playground/)**
   - Use the same session ID from `.env`
   - Enable camera + microphone
3. **Publish video/audio**
4. **Speak into microphone** (text will be processed through Bedrock LLM)
5. **Wait 5-10 seconds** for LLM response + echo
6. **Unpublish, then disconnect** from Playground
7. **Stop agent** (Ctrl+C)
8. **Verify logs** for success signals (see below)

### Verify Success from Logs

```bash
# Capture output to file
docker run --rm … c4a-bedrock python bedrock_echo_agent.py 2>&1 | tee logs/c4a-bedrock-echo.log

# Then grep for success markers
grep "Connected to Vonage Video session" logs/c4a-bedrock-echo.log
grep "Bedrock LLM ready" logs/c4a-bedrock-echo.log
grep "Participant joined" logs/c4a-bedrock-echo.log
grep "Client connected" logs/c4a-bedrock-echo.log
grep "monitor:" logs/c4a-bedrock-echo.log        # Check counters
grep "Client disconnected" logs/c4a-bedrock-echo.log
grep "Participant left" logs/c4a-bedrock-echo.log
```

### Success Checklist

- [ ] Agent connects to Vonage session (logs: "Connected to Vonage Video session")
- [ ] Bedrock LLM initialized (logs: "Bedrock LLM ready")
- [ ] Participant joins from Playground (logs: "Participant joined")
- [ ] Client connects (logs: "Client connected")
- [ ] Monitor shows active_streams > 0 (logs: "monitor: active_streams=1")
- [ ] Participant speaks → LLM processes → echo returns (audio loop confirmed)
- [ ] Client disconnects (logs: "Client disconnected")
- [ ] Participant leaves (logs: "Participant left")
- [ ] Agent stops cleanly (Ctrl+C → "Test C4a Bedrock integration complete ✓")

---

## What It Tests

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

- **C4b:** Validate Nova Sonic (speech-to-speech) model as alternative to Nova Lite
- **C5:** Full AgentCore integration with Bedrock + Vonage transport for multi-turn context
- **Monitoring:** Extend C4a to log all Bedrock invocations (prompts, responses, latency) for observability

---

## References

- [AWS Bedrock Nova Models](https://aws.amazon.com/bedrock/nova/)
- [Vonage Video Pipecat Transport Docs](https://developer.vonage.com/en/video/guides/vonage-video-connector-pipecat-transport)
- [Pipecat GitHub](https://github.com/Vonage/pipecat)
