# Building Real-Time AI Voice Agents with Vonage, Pipecat, and AWS Bedrock AgentCore

This post walks through building a production-ready AI voice agent that joins a Vonage video call, listens to participants, responds with Amazon Nova Sonic in real time, and optionally uses AWS Bedrock AgentCore to bootstrap assistant behavior.

---

## Introduction

Conversational AI has moved from text chatbots to real-time voice agents that can participate in video calls just like a human colleague. In this post I'll show you how to wire together four key components:

1. **Vonage Video API + Video Connector SDK** — letting a Python server join a WebRTC video session as a first-class audio/video participant
2. **Pipecat AI** — an open-source framework for building real-time audio/video pipelines
3. **AWS Bedrock with Amazon Nova Sonic** — a low-latency speech-to-speech model for the live conversation loop
4. **AWS Bedrock AgentCore Runtime** — an optional bootstrap runtime for shaping initial assistant behavior

By the end you'll have a working agent that:

- Joins a Vonage video session
- Listens to participants in real time
- Optionally bootstraps assistant behavior via AgentCore
- Speaks back using Nova Sonic's natural TTS

The full project, runnable app, and environment setup live in the repository root [README](../README.md).

## Bedrock vs AgentCore (Why Both?)

These services solve different layers of the system:

- **Amazon Bedrock** is the model inference layer (Nova Sonic / Nova Lite) for real-time responses.
- **Amazon Bedrock AgentCore** is the managed runtime layer for deployable agent app logic.

In this implementation, Bedrock powers the live speech loop, and AgentCore is optional startup bootstrap context when `AGENTCORE_AGENT_ARN` is configured.

Short version: **Bedrock answers; AgentCore runs deployable agent app logic.**

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
│  VonageTransport ──► NovaSonic ──► VonageTransport │
│                                                  │
│  Optional startup bootstrap via AgentCore Runtime│
│                                                  │
│  FastAPI management API (:8000)                  │
└──────────────────────────────────────────────────┘
```

The pipeline is fully streaming. Audio frames flow through each stage without buffering entire utterances, keeping end-to-end latency well below a second.

---

## Prerequisites

- A [Vonage account](https://dashboard.nexmo.com) with a Video API application
- An AWS account with Bedrock model access (Nova Sonic + Nova Lite)
- Docker (for running the Linux-native Video Connector SDK on macOS)
- Python 3.11+ and [uv](https://docs.astral.sh/uv/)

## AWS Requirements

Before running the app, make sure AWS is ready in three areas:

1. Identity and region
   - Configure `AWS_PROFILE` and `AWS_REGION` (recommended region in this repo: `us-east-1`).
   - Verify credentials:

```bash
aws sts get-caller-identity --profile vonage-dev
```

1. Bedrock model access
   - Enable access for Amazon Nova Sonic and Nova Lite in the Bedrock Model Access console.

1. IAM permissions
   - Ensure your principal can invoke Bedrock models and AgentCore runtime endpoints.
   - Typical actions used by this project include:
     - `bedrock:InvokeModel`
     - `bedrock:InvokeModelWithResponseStream`
     - `bedrock-agentcore:InvokeAgentRuntime`

---

## Step 1 — Configure Credentials

Create a Vonage Video application in the dashboard, download `private.key`, and capture your Application ID.

In `.env`, set at minimum:

- `VONAGE_APPLICATION_ID`
- `VONAGE_PRIVATE_KEY`
- `VONAGE_SESSION_ID` (existing session)
- `AWS_PROFILE` and `AWS_REGION`
- `BEDROCK_MODEL_ID`
- `AGENTCORE_AGENT_ARN` (optional, only for startup bootstrap behavior)

Use the AWS verification command from **AWS Requirements** above to confirm your profile is ready.

---

## Step 2 — Run the Application

Start the integrated app:

```bash
# macOS / non-Linux
docker compose --profile app up --build
```

The FastAPI server starts on port 8000. The agent auto-joins `VONAGE_SESSION_ID` and waits for participants.

---

## Step 3 — Validate Live Session

1. Open [https://tokbox.com/developer/tools/playground/](https://tokbox.com/developer/tools/playground/)
2. Log in to the Vonage account that owns your `VONAGE_APPLICATION_ID`
3. Join the existing session from `.env`
4. Publish mic/audio and speak
5. Confirm the agent responds through Nova Sonic

Optional runtime checks:

```bash
curl http://localhost:8000/
curl http://localhost:8000/status
```

---

## SDK Usage Snippets

These snippets are intentionally simplified to highlight SDK usage. For the production implementation used in this repo, see [app/agent.py](../app/agent.py).

### 1) Vonage auth + publisher token

```python
from vonage import Auth, Vonage
from vonage_video import TokenOptions

client = Vonage(
    Auth(
        application_id=application_id,
        private_key=private_key_path,
    )
)

token = client.video.generate_client_token(
    TokenOptions(session_id=session_id, role="publisher")
)
```

### 2) Pipecat Vonage transport setup

```python
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.transports.vonage.video_connector import (
    VonageVideoConnectorTransport,
    VonageVideoConnectorTransportParams,
)

transport = VonageVideoConnectorTransport(
    application_id=application_id,
    session_id=session_id,
    token=token,
    params=VonageVideoConnectorTransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        video_in_enabled=False,
        video_out_enabled=False,
        audio_in_sample_rate=16000,
        audio_out_sample_rate=24000,
        vad_analyzer=SileroVADAnalyzer(),
        audio_in_auto_subscribe=True,
    ),
)
```

### 3) Nova Sonic service + pipeline wiring

```python
import boto3
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.services.aws.nova_sonic.llm import AWSNovaSonicLLMService, Params

session = boto3.Session(profile_name="vonage-dev", region_name="us-east-1")
creds = session.get_credentials().get_frozen_credentials()
bedrock_model_id = "amazon.nova-2-sonic-v1:0"

context = LLMContext(messages=[{"role": "user", "content": "Greet briefly."}])
context_aggregator = LLMContextAggregatorPair(context)

nova_sonic = AWSNovaSonicLLMService(
    access_key_id=creds.access_key,
    secret_access_key=creds.secret_key,
    session_token=creds.token,
    region="us-east-1",
    model=bedrock_model_id,
    params=Params(
        input_sample_rate=16000,
        input_channel_count=1,
        output_sample_rate=24000,
        output_channel_count=1,
    ),
)

pipeline = Pipeline([
    transport.input(),
    context_aggregator.user(),
    nova_sonic,
    context_aggregator.assistant(),
    transport.output(),
])
```

---

## Key Pipecat Pipeline Design

The pipeline in `app/agent.py` chains five stages:

```python
pipeline = Pipeline([
    transport.input(),   # Audio frames from Vonage WebRTC
    context_aggregator.user(),
    nova_sonic,          # Streaming speech-to-speech model
    context_aggregator.assistant(),
    transport.output(),  # Audio frames back to Vonage WebRTC
])
```

Each stage processes Pipecat `Frame` objects asynchronously. Nova Sonic streams audio output early, so playback starts before the full response is complete, which keeps perceived latency low.

---

## Deployment Considerations

- **Linux requirement** — The Vonage Video Connector SDK is a native Linux binary. Use Docker on macOS for development; deploy to a Linux VM or container for production.
- **AgentCore scaling** — AgentCore Runtime can scale independently when used for startup bootstrap calls.
- **Credentials** — Never commit `.env` or `private.key` to source control. Use AWS Secrets Manager or environment injection in production.
- **Nova Sonic pricing** — Billed per second of audio processed. The pipeline's VAD (voice activity detection) ensures the model is only called when a participant is speaking.

---

## Conclusion

In this post we built a real-time AI voice agent that:

- Joins a Vonage WebRTC video session as a server-side participant
- Processes live conversation with Amazon Nova Sonic in a streaming loop
- Optionally uses AWS Bedrock AgentCore Runtime to bootstrap assistant style/context
- Returns synthesised audio in near real time

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
