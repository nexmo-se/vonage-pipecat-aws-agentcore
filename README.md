# vonage-pipecat-aws-agentcore

Real-time AI voice and video agents using **Vonage Video Connector Pipecat Integration** and **AWS Bedrock AgentCore Runtime**.

---

## Overview

This project shows how to build production-ready, real-time AI voice/video agents by wiring together:

| Component | Role |
|---|---|
| **Vonage Video API** | WebRTC session management and media routing |
| **Vonage Video Connector SDK** | Server-side WebRTC participant (Linux) |
| **Pipecat AI** | Real-time audio/video pipeline orchestration |
| **AWS Nova Sonic** | Speech-to-speech model on AWS Bedrock |
| **AWS Bedrock AgentCore** | Managed runtime for scalable AI agents |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  Browser / Mobile Client                      │
│              (Vonage Video Web SDK / OpenTok.js)              │
└───────────────────────────┬──────────────────────────────────┘
                            │  WebRTC (audio + video)
                            ▼
┌──────────────────────────────────────────────────────────────┐
│              Vonage Video API Platform                        │
│         (Session Management · Media Routing · TURN)          │
└───────────────────────────┬──────────────────────────────────┘
                            │  WebRTC (Video Connector SDK)
                            ▼
┌──────────────────────────────────────────────────────────────┐
│           Python AI Agent  (Linux · Docker)                  │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                 Pipecat Pipeline                     │    │
│  │                                                      │    │
│  │  ┌───────────────┐   ┌──────────────┐               │    │
│  │  │    Vonage     │   │  AWS Bedrock │               │    │
│  │  │   Transport   │──▶│  Nova Sonic  │               │    │
│  │  │  (WebRTC I/O) │   │  (STT + TTS) │               │    │
│  │  └───────────────┘   └──────┬───────┘               │    │
│  │                             │ text                  │    │
│  │                      ┌──────▼───────┐               │    │
│  │                      │  AgentCore   │               │    │
│  │                      │   Runtime    │               │    │
│  │                      │ (LLM logic)  │               │    │
│  │                      └──────────────┘               │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│            FastAPI WebSocket  (management API)               │
└──────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | `python --version` |
| [uv](https://docs.astral.sh/uv/) | Fast Python package manager |
| Docker + Docker Compose | Required for Linux-only tests (C2, C3, app) |
| Vonage account | [dashboard.nexmo.com](https://dashboard.nexmo.com) — create a Video API application |
| AWS account | IAM user with `AmazonBedrockFullAccess` and AgentCore permissions |
| AWS Bedrock model access | Enable **Nova Sonic** and **Nova Lite** in us-east-1 Bedrock console |

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/nexmo-se/vonage-pipecat-aws-agentcore.git
cd vonage-pipecat-aws-agentcore

# 2. Copy and fill in credentials
cp .env.example .env
# Edit .env with your VONAGE_APPLICATION_ID, private key path, and AWS keys

# 3. Run tests in order (see each folder's README for details)
```

---

## Test Folders

Work through the tests in order to validate each layer of the stack before wiring everything together.

| # | Folder | What it tests | Platform |
|---|---|---|---|
| C1 | [tests/c1_vonage_video_session](tests/c1_vonage_video_session/README.md) | Vonage Video session creation + browser client URL | Any |
| C2 | [tests/c2_video_connector_sdk](tests/c2_video_connector_sdk/README.md) | Video Connector SDK joining as WebRTC participant | Linux / Docker |
| C3 | [tests/c3_pipecat_transport](tests/c3_pipecat_transport/README.md) | Pipecat echo bot over Vonage transport | Linux / Docker |
| C4a | [tests/c4a_aws_bedrock](tests/c4a_aws_bedrock/README.md) | AWS Bedrock credentials + Nova Lite text chat | Any |
| C4b | [tests/c4b_nova_sonic](tests/c4b_nova_sonic/README.md) | Nova Sonic speech-to-speech standalone pipeline | Any |
| C5 | [tests/c5_agentcore](tests/c5_agentcore/README.md) | AgentCore Runtime deploy + invoke hello world | Any |

---

## Full Application

Once all tests pass, run the complete agent:

```bash
cd app
docker compose up --build     # macOS / non-Linux
# or
uv run uvicorn main:app --reload --port 8000   # native Linux
```

See [app/README.md](app/README.md) for full instructions.

---

## Repository Layout

```
vonage-pipecat-aws-agentcore/
├── .env.example                  # Template for all credentials
├── docker-compose.yml            # Linux container services (macOS-friendly)
├── tests/
│   ├── c1_vonage_video_session/  # Vonage Video session + token
│   ├── c2_video_connector_sdk/   # Video Connector SDK (Linux/Docker)
│   ├── c3_pipecat_transport/     # Pipecat echo bot (Linux/Docker)
│   ├── c4a_aws_bedrock/          # Bedrock credentials + Nova Lite
│   ├── c4b_nova_sonic/           # Nova Sonic speech-to-speech
│   └── c5_agentcore/             # AgentCore Runtime
├── app/                          # Full integrated agent
├── blog/                         # Blog post + images
└── docs/                         # Architecture diagrams + notes
```

---

## License

[MIT](LICENSE) — Copyright © 2026 Vonage API CSE
