# vonage-pipecat-aws-agentcore

Real-time AI voice and video agents using **Vonage Video**, **Pipecat**, **Amazon Nova Sonic**, and **Amazon Bedrock AgentCore Runtime**.

---

## Overview

This repository is an opinionated sample app and blog companion that combines:

- **Amazon Bedrock AgentCore Runtime** as the managed runtime that hosts the agent logic
- **Amazon Nova Sonic** as the low-latency speech-to-speech model inside the Pipecat pipeline
- **Vonage Video API + Video Connector transport** as the real-time session layer that connects browser participants to the agent
- **Pipecat** as the orchestration layer that moves media between the transport and the model

Unlike direct client-to-agent transport examples, this sample uses **Vonage Video as the live session layer**. Browser users join a Vonage session, and the AI agent joins that same session through the **Vonage Video Connector Pipecat transport**.

That makes the architecture split explicit:

- **AWS AgentCore** explains where the agent runs
- **Nova Sonic** explains how the agent speaks and listens
- **Vonage Video** explains how the agent joins a live call

This project shows how to wire those pieces together into a working sample.

Core building blocks:

| Component                      | Role                                         |
| ------------------------------ | -------------------------------------------- |
| **Vonage Video API**           | Browser session management and media routing |
| **Vonage Video Connector SDK** | Server-side session participant for Pipecat  |
| **Pipecat AI**                 | Real-time media and model orchestration      |
| **Amazon Nova Sonic**          | Low-latency speech-to-speech intelligence    |
| **Amazon Bedrock AgentCore**   | Managed runtime for deployable agent logic   |

Transport choice for this repo:

- This sample uses the **Vonage Video Connector Pipecat transport** path.
- That means the required native media layer is the **Vonage Video Linux SDK / Video Connector SDK**.
- The **Vonage Audio Connector SDK** is **not** required here.
- The Audio Connector SDK applies to the separate **serializer / WebSocket** integration path, planned as **Phase 2 (Serializer/Voice)**.

## Delivery Phases

This repository is being delivered in phases to keep the POC fast while preserving the broader product request.

- **Phase 1 (current): Transport/Video**
  Vonage Video API + Video Connector transport, Pipecat transport pipeline, Amazon Nova Sonic integration, and AWS Bedrock AgentCore runtime deploy/invoke.
- **Phase 2 (planned): Serializer/Voice**
  Vonage Voice telephony use case path, Pipecat serializer/WebSocket integration, and architecture guidance for when serializer is preferred over transport.

## Positioning

Use this repository as both:

- a **sample app** for validating each layer independently before running the full integrated agent
- a **reference implementation** for a blog post that explains how Vonage Video, Pipecat, Nova Sonic, and AgentCore fit together

The validation flow in `tests/` intentionally decomposes the stack so you can prove each dependency separately before combining them in `app/`.

---

## Architecture

High-level runtime topology:

```text
┌──────────────────────────────────────────────────────────────┐
│                  Browser / Mobile Client                      │
│              (Vonage Video Web SDK / OpenTok.js)              │
└───────────────────────────┬──────────────────────────────────┘
                            │  WebRTC (audio + video)
                            ▼
┌──────────────────────────────────────────────────────────────┐
│              Vonage Video API Platform                        │
│         (Session Management · Media Routing)                 │
└───────────────────────────┬──────────────────────────────────┘
                            │  Session join via Video Connector transport
                            ▼
┌──────────────────────────────────────────────────────────────┐
│         AI Agent Runtime (Pipecat on AgentCore)              │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                 Pipecat Pipeline                     │    │
│  │                                                      │    │
│  │  ┌───────────────┐   ┌──────────────┐               │    │
│  │  │    Vonage     │   │  AWS Bedrock │               │    │
│  │  │  Transport      │◀─▶│  Nova Sonic  │               │    │
│  │  │ (session I/O)   │   │ (speech I/O) │               │    │
│  │  └───────────────┘   └──────┬───────┘               │    │
│  │                             │                       │    │
│  │                      ┌──────▼────────┐              │    │
│  │                      │ Agent Logic    │              │    │
│  │                      │ on AgentCore   │              │    │
│  │                      └───────────────┘              │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

What is happening in this sample:

1. A browser joins a **Vonage Video** session.
2. The AI agent joins that same session through the **Vonage Video Connector Pipecat transport**.
3. **Pipecat** orchestrates the real-time conversation loop.
4. **Amazon Nova Sonic** handles low-latency speech input/output.
5. **Amazon Bedrock AgentCore Runtime** hosts the deployable agent logic used by the full application and C5 runtime validation.

This is different from direct WebSocket or direct WebRTC examples where the client connects straight to the agent runtime. In this repository, **Vonage is the media/session intermediary**, which is the important architectural distinction.

---

## Prerequisites

| Requirement                      | Notes                                                                               |
| -------------------------------- | ----------------------------------------------------------------------------------- |
| Python 3.11+                     | `python --version`                                                                  |
| [uv](https://docs.astral.sh/uv/) | Optional — faster venv/install alternative to pip                                   |
| Docker + Docker Compose          | Required for Linux-only tests (C2, C3, app)                                         |
| Vonage account                   | [dashboard.nexmo.com](https://dashboard.nexmo.com) — create a Video API application |
| AWS account                      | IAM user with `AmazonBedrockFullAccess` and AgentCore permissions                   |
| AWS Bedrock model access         | Enable **Nova Sonic** and **Nova Lite** in us-east-1 Bedrock console                |

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/nexmo-se/vonage-pipecat-aws-agentcore.git
cd vonage-pipecat-aws-agentcore

# 2. Copy and fill in credentials
cp .env.example .env
# Edit .env with your VONAGE_APPLICATION_ID, private key path, and runtime/model settings

# 2a. Configure AWS profile (recommended)
aws configure --profile vonage-dev
# enter AWS Access Key ID, Secret Access Key, region (us-east-1), output (json)

# verify profile works
aws sts get-caller-identity --profile vonage-dev

# use this profile for all test commands
export AWS_PROFILE=vonage-dev

# 3. Run tests in order (see each folder's README for details)
```

---

## Test Folders

Work through the tests in order to validate each layer of the stack before wiring everything together.

| #   | Folder                                                                   | What it tests                                      | Platform       |
| --- | ------------------------------------------------------------------------ | -------------------------------------------------- | -------------- |
| C1  | [tests/c1_vonage_video_session](tests/c1_vonage_video_session/README.md) | Vonage Video session creation + browser client URL | Any            |
| C2  | [tests/c2_video_connector_sdk](tests/c2_video_connector_sdk/README.md)   | Video Connector SDK joining as WebRTC participant  | Linux / Docker |
| C3  | [tests/c3_pipecat_transport](tests/c3_pipecat_transport/README.md)       | Pipecat echo bot over Vonage transport             | Linux / Docker |
| C4  | [tests/c4_bedrock_nova_sonic](tests/c4_bedrock_nova_sonic/README.md)     | AWS Bedrock + Nova Lite + Nova Sonic integration   | Any            |
| C5  | [tests/c5_agentcore](tests/c5_agentcore/README.md)                       | AgentCore Runtime deploy + invoke hello world      | Any            |

---

## C5 At A Glance

C5 validates that an AWS Bedrock AgentCore runtime is both deployable and invokable from this project.

- `tests/c5_agentcore/hello_agent.py` is the minimal deployable runtime app.
- `tests/c5_agentcore/test_agentcore.py` invokes the deployed runtime (`AGENTCORE_AGENT_ARN`) with a hello-world prompt.

High-level flow:

1. Configure runtime deployment with the AgentCore CLI.
2. Deploy the runtime and capture the runtime ARN.
3. Set `AGENTCORE_AGENT_ARN` in `.env`.
4. Run the C5 test to verify invocation and response.

For exact commands, IAM prerequisites, and expected output, see [tests/c5_agentcore/README.md](tests/c5_agentcore/README.md).

---

## Full Application

Once all tests pass, run the complete agent:

```bash
cd app
docker compose up --build     # macOS / non-Linux
# or
uv run uvicorn main:app --reload --port 8000   # native Linux
```

If `uv` is missing, install it first with `brew install uv` on macOS.

See [app/README.md](app/README.md) for full instructions.

---

## Repository Layout

```text
vonage-pipecat-aws-agentcore/
├── .env.example                  # Template for all credentials
├── docker-compose.yml            # Linux container services (macOS-friendly)
├── tests/
│   ├── c1_vonage_video_session/  # Vonage Video session + token
│   ├── c2_video_connector_sdk/   # Video Connector SDK (Linux/Docker)
│   ├── c3_pipecat_transport/     # Pipecat echo bot (Linux/Docker)
│   ├── c4_bedrock_nova_sonic/     # Bedrock + Nova Lite + Nova Sonic
│   └── c5_agentcore/             # AgentCore Runtime
├── app/                          # Full integrated agent
├── blog/                         # Blog post + images
└── docs/                         # Architecture diagrams + notes
```

## Official Vonage References

This project intentionally cites Vonage-authored documentation as the primary source for API and SDK behavior.

- [Vonage Video API overview](https://developer.vonage.com/en/video/overview)
- [Vonage Video Python Server SDK docs](https://developer.vonage.com/en/video/server-sdks/python)
- [Vonage Python SDK repository](https://github.com/Vonage/vonage-python-sdk)
- [Vonage Python SDK Video API examples](https://github.com/Vonage/vonage-python-sdk/blob/main/video/README.md)
- [Vonage Video Connector guide](https://developer.vonage.com/en/video/guides/vonage-video-connector)
- [Vonage Pipecat transport guide](https://developer.vonage.com/en/video/guides/vonage-video-connector-pipecat-transport)
- [Vonage Audio Connector guide (serializer/WebSocket related)](https://developer.vonage.com/en/video/guides/audio-connector)
- [Vonage Voice API overview (Phase 2 Serializer/Voice scope)](https://developer.vonage.com/en/voice/overview)

---

## License

[MIT](LICENSE) — Copyright © 2026 Vonage API CSE
