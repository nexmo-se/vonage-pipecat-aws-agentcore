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

Architecture responsibilities in this sample:

- **AWS AgentCore**: where the agent runs
- **Nova Sonic**: how the agent listens and speaks
- **Vonage Video**: how the agent joins and participates in live calls

Core building blocks:

| Component                      | Role                                         |
| ------------------------------ | -------------------------------------------- |
| **Vonage Video API**           | Browser session management and media routing |
| **Vonage Video Connector SDK** | Server-side session participant for Pipecat  |
| **Pipecat AI**                 | Real-time media and model orchestration      |
| **Amazon Nova Sonic**          | Low-latency speech-to-speech intelligence    |
| **Amazon Bedrock AgentCore**   | Managed runtime for deployable agent logic   |

## Bedrock and AgentCore

These two AWS services are complementary.

| Layer                           | Service                      | What it does in this project                                                                      |
| ------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------- |
| **Model inference layer**       | **Amazon Bedrock**           | Runs model inference (Nova Lite / Nova Sonic) for language and speech generation.                 |
| **Managed agent runtime layer** | **Amazon Bedrock AgentCore** | Hosts deployable agent application logic and returns bootstrap instructions/persona when enabled. |

How they work together in this repository:

1. **Bedrock (C4b)** provides live model capabilities during conversation.
2. **AgentCore (C5)** provides managed, deployable agent logic.
3. In `app/`, AgentCore can be invoked at session start (when `AGENTCORE_AGENT_ARN` is set) to prime behavior, while Bedrock/Nova handles live inference.

Decision rule:

- Use **Bedrock only** for quick model-driven prototypes.
- Add **AgentCore + Bedrock** when you need managed deployment, versioned runtime logic, tool/memory workflows, or governance/auditability.

Short version: **Bedrock answers; AgentCore runs deployable agent app logic.**

This repository currently implements the **Transport** path; see **Transport vs Serializer** below for architecture tradeoffs and selection guidance.

## Transport vs Serializer

Both integration options are valid, but they solve different problems.

### Option A: Transport (current repository implementation)

Architecture shape:

`Browser WebRTC <-> Vonage Video Platform <-> Video Connector SDK <-> Pipecat transport pipeline`

Characteristics:

- Agent joins as a real participant in a Vonage Video session.
- Media transport, session membership, and participant lifecycle come from Vonage Video.
- Best fit for browser/mobile video session experiences where humans and AI share the same live room.

Choose Transport when:

- You need WebRTC session semantics (join/leave, publish/subscribe, participant events).
- You are building meeting-style or in-app video/audio rooms.
- You want to reuse Vonage Video session controls and moderation patterns.

### Option B: Serializer (planned Phase 2)

Architecture shape:

`Voice/telephony media stream <-> serializer/WebSocket bridge <-> Pipecat pipeline`

Characteristics:

- Focuses on serialized media events over WebSocket instead of session-participant transport.
- Better aligned with telephony and non-room media streaming scenarios.
- Usually requires explicit handling for stream protocol details and event mapping.

Choose Serializer when:

- Your primary channel is voice/telephony rather than shared video sessions.
- You need custom stream event control at the protocol/message layer.
- You do not need an AI participant to appear as a native Vonage Video session member.

### Quick decision guide

- Pick **Transport** for Vonage Video session-native AI participants.
- Pick **Serializer** for telephony-oriented or protocol-level streaming integrations.

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

## Test Components & Validation Path

The repository includes six modular validation stages (`C1`, `C2`, `C3`, `C4a`, `C4b`, `C5`) that validate each layer of the stack in isolation before combining them in `app/`. Run them in order to build confidence in the full integration.

### C1: Vonage Video Session Creation

**What it validates:** Vonage Video API authentication, session provisioning, and client token generation.

**Purpose:**

- Confirms your Vonage Video API credentials are correct.
- Creates a persistent `VONAGE_SESSION_ID` for use in downstream tests.
- Generates a browser playground URL so you can manually verify session access.

**When you're done:** You have a real Vonage session ID stored in `.env` and can join that session in the browser.

**Platform:** Any (macOS, Linux, Windows)

---

### C2: Vonage Video Connector SDK

**What it validates:** The native **Vonage Video Connector SDK** can join a Vonage Video session as a server-side WebRTC participant.

**Purpose:**

- Proves the Video Connector SDK is installed and compatible with the Linux runtime environment.
- Verifies the SDK can authenticate to Vonage and establish media connection.
- Demonstrates the bridge between Vonage Video session and Pipecat pipeline (foundation for C3).

**When you're done:** You see the Video Connector participant appear in the Vonage session (via Playground or other browser client).

**Platform:** Linux only (Docker on macOS)

---

### C3: Pipecat Transport Echo Bot

**What it validates:** **Pipecat orchestration** combined with **Vonage Video Connector transport** as an echo bot.

**Purpose:**

- Confirms Pipecat can receive audio frames from the Vonage session and replay them back in real time.
- Validates the full media pipeline (browser → Vonage → Video Connector → Pipecat → back to Vonage → browser).
- Tests transport frame handling without adding model/LLM complexity yet.

**When you're done:** You can speak in the Vonage Playground, hear your audio echoed back by the agent, and confirm round-trip latency is acceptable.

**Platform:** Linux only (Docker on macOS)

---

### C4a: AWS Bedrock Credential Check

**What it validates:** AWS Bedrock credentials, model access, and baseline text inference before the full speech path.

**Purpose:**

- Confirms AWS credentials and region settings are correct.
- Verifies Bedrock access to Nova Lite before running the heavier transport integration.
- Gives you a lower-cost preflight step before the full Nova Sonic session test.

**When you're done:** You have confirmed Bedrock connectivity and basic inference before moving to the integrated Nova Sonic transport stage.

**Platform:** Linux / Docker

---

### C4b: AWS Bedrock + Nova Sonic Integration

**What it validates:** **AWS Bedrock LLM** and **Nova Sonic** speech-to-speech model integrated with the Vonage transport pipeline.

**Purpose:**

- Builds on C4a by combining verified Bedrock access with the Vonage transport path.
- Demonstrates speech-to-speech inference (listen → generate text response → speak).
- Validates end-to-end latency with real ML model (STT → LLM reasoning → TTS).

**When you're done:** You can ask the agent a question in the Vonage Playground, and it responds naturally with AI-generated speech.

**Platform:** Linux / Docker

---

### C5: AWS Bedrock AgentCore Runtime

**What it validates:** **AWS Bedrock AgentCore** deployment and invocation.

**Purpose:**

- Proves AgentCore runtime deployment (writing code, configuring, deploying to AWS).
- Validates the `bedrock-agentcore` API for runtime invocation.
- Demonstrates how AgentCore can provide dynamic initialization (e.g., persona, system prompt) that primes the Pipecat agent before media interaction.

**AgentCore Role:**
AgentCore is a managed AWS runtime that hosts deployable agent logic. In this project, it's used as an optional **bootstrap layer**—at session start, if `AGENTCORE_AGENT_ARN` is set, the app invokes AgentCore to fetch a priming message (e.g., custom instructions or persona). This message is injected into the Pipecat pipeline, customizing agent behavior before real-time conversation begins.

**When you're done:** You have deployed a runtime to AWS, captured its ARN, and verified it can be invoked programmatically.

**Platform:** Any (AWS credentials required)

---

## Full Application Flow

Once all staged tests pass:

1. **C1** confirms Vonage session access.
2. **C2** confirms the Video Connector SDK can join a session.
3. **C3** confirms Pipecat transport and echo behavior.
4. **C4a** confirms Bedrock credentials and baseline text inference.
5. **C4b** confirms Bedrock + Nova Sonic speech-to-speech inference.
6. **C5** confirms AgentCore runtime deployment and bootstrap capability.

The `app/` folder combines all five pieces into a complete agent:

- Uses the session from **C1**.
- Joins via the connector from **C2**.
- Orchestrates via Pipecat transport from **C3**.
- Responds with AI speech via **C4b** (Nova Sonic).
- Optionally primes behavior via **C5** (AgentCore bootstrap).

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

This repository uses the session-participant model where **Vonage is the media/session intermediary** (see **Transport vs Serializer** above).

### Data Flow

Inbound (Browser to Agent):

1. Browser captures microphone audio via WebRTC.
2. Vonage Video routes media to the Video Connector SDK participant.
3. Pipecat receives audio frames via transport input.
4. Nova Sonic + AgentCore process speech and response logic.

Outbound (Agent to Browser):

1. Nova Sonic generates response audio frames.
2. Pipecat publishes frames through transport output.
3. Vonage Video distributes audio to connected participants.

### Frame Types (Pipecat)

| Frame                      | Direction | Description                          |
| -------------------------- | --------- | ------------------------------------ |
| `AudioRawFrame`            | In / Out  | Raw PCM audio (16 kHz, mono, 16-bit) |
| `UserStartedSpeakingFrame` | Internal  | VAD detected speech start            |
| `UserStoppedSpeakingFrame` | Internal  | VAD detected speech end              |
| `TranscriptionFrame`       | Internal  | STT output text                      |
| `TextFrame`                | Internal  | AgentCore LLM response text          |

### Latency Budget (Typical)

| Stage                              | Typical latency  |
| ---------------------------------- | ---------------- |
| VAD detection                      | < 50 ms          |
| Nova Sonic STT (first token)       | ~200–400 ms      |
| AgentCore inference (first token)  | ~300–600 ms      |
| Nova Sonic TTS (first audio chunk) | ~100–200 ms      |
| Vonage media routing               | < 50 ms          |
| **Total (time-to-first-audio)**    | **~650–1300 ms** |

### Security Notes

- Keep credentials in `.env` (gitignored).
- Rotate Vonage session tokens periodically (short expiry preferred).
- Restrict management API exposure (`/join`, `/leave`, `/ws`) behind auth in production.
- Scope AWS IAM permissions to required Bedrock and AgentCore actions only.

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

## Setup Reference

Python package baseline:

| Package                  | Version (minimum) |
| ------------------------ | ----------------- |
| `vonage`                 | `>=4.0.0`         |
| `vonage-video-connector` | `>=1.0.0`         |
| `pipecat-ai`             | `>=0.0.50`        |
| `boto3`                  | `>=1.34.0`        |
| `bedrock-agentcore`      | `>=0.1.0`         |

Bedrock model IDs used in this project:

| Model             | ID                         |
| ----------------- | -------------------------- |
| Amazon Nova Sonic | `amazon.nova-2-sonic-v1:0` |
| Amazon Nova Lite  | `amazon.nova-lite-v1:0`    |
| Amazon Nova Pro   | `amazon.nova-pro-v1:0`     |

Vonage Video recommendations:

- Use `routed` media mode when using Video Connector.
- Use `publisher` token role for the AI session participant.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/nexmo-se/vonage-pipecat-aws-agentcore.git
cd vonage-pipecat-aws-agentcore

# 2. Copy and fill in credentials
cp .env.example .env
# Edit .env with your VONAGE_APPLICATION_ID, private key path, and runtime/model settings

# 3. Configure AWS profile (recommended)
aws configure --profile vonage-dev
# enter AWS Access Key ID, Secret Access Key, region (us-east-1), output (json)

# verify profile works
aws sts get-caller-identity --profile vonage-dev

# use this profile for all test commands
export AWS_PROFILE=vonage-dev

# 4. Run tests in order (see each folder's README for details)
```

---

## Test Folders

Work through the tests in order to validate each layer of the stack before wiring everything together.

| #   | Folder                                                                   | What it tests                                     | Platform       |
| --- | ------------------------------------------------------------------------ | ------------------------------------------------- | -------------- |
| C1  | [tests/c1_vonage_video_session](tests/c1_vonage_video_session/README.md) | Vonage Video session creation + client token      | Any            |
| C2  | [tests/c2_video_connector_sdk](tests/c2_video_connector_sdk/README.md)   | Video Connector SDK joining as WebRTC participant | Linux / Docker |
| C3  | [tests/c3_pipecat_transport](tests/c3_pipecat_transport/README.md)       | Pipecat echo bot over Vonage transport            | Linux / Docker |
| C4a | [tests/c4a_aws_bedrock](tests/c4a_aws_bedrock/README.md)                 | Bedrock credential check + staged echo validation | Linux / Docker |
| C4b | [tests/c4b_bedrock_nova_sonic](tests/c4b_bedrock_nova_sonic/README.md)   | AWS Bedrock + Nova Sonic speech-to-speech         | Linux / Docker |
| C5  | [tests/c5_agentcore](tests/c5_agentcore/README.md)                       | AgentCore Runtime deploy + invoke hello world     | Any            |

---

## Full Application

Once all staged tests pass, run the complete agent:

```bash
docker compose --profile app up --build     # repo root; macOS / non-Linux
# or
cd app
uvicorn main:app --host 0.0.0.0 --port 8000   # native Linux
```

If `uv` is missing, install it first with `brew install uv` on macOS.

What to expect from the running app:

- `GET /` returns `{"status": "ok"}` when the API is live.
- `GET /status` shows whether the auto-join pipeline is running and connected.
- A normal fresh startup can report `running: true` with `connected: false` until a participant/client joins; `last_error` should remain `null`.
- On Docker, the app mounts `${HOME}/.aws` and `./private.key` automatically so it can reuse the same AWS profile and Vonage key material validated in C4b/C5.

Current runtime shape:

- The FastAPI app auto-joins `VONAGE_SESSION_ID` on startup when it is present in `.env`.
- The speech loop uses the same validated **Vonage Video Connector + Nova Sonic** path from C4b.
- `AGENTCORE_AGENT_ARN` is used as an optional bootstrap step to shape the initial assistant behavior, not as a separate in-pipeline service hop.
- The app monitor emits `session_renewal_recommended` before the Nova Sonic connection window expires so you can refresh with `POST /leave` then `POST /join`.

See [app/README.md](app/README.md) for full instructions.

## Production Deployment

Use `docker compose` for local validation only. For production, deploy on Linux infrastructure:

- **Fastest path**: EC2/Linux VM running this app as a service or container.
- **Recommended at scale**: ECS/Fargate (or EKS/App Runner) with CI/CD image deploys.

Production responsibility split:

- **Amazon Bedrock**: model inference platform.
- **Amazon Nova Sonic**: speech-to-speech model used through Bedrock.
- **Amazon Bedrock AgentCore Runtime**: optional managed bootstrap/runtime logic.

Minimum production controls:

- Use role-based IAM or temporary credentials (avoid long-lived static keys).
- Keep least-privilege permissions for Bedrock, AgentCore, logging, and secrets.
- Verify model IDs/region support and quotas before rollout.
- Enable CloudWatch metrics/logs and CloudTrail auditing.

Detailed deployment runbook: [app/README.md](app/README.md#deploy-to-production)

AWS references:

- [Amazon Bedrock API methods](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-api-methods.html)
- [Amazon Bedrock model IDs](https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html)
- [Amazon Bedrock monitoring](https://docs.aws.amazon.com/bedrock/latest/userguide/monitoring.html)
- [Amazon Bedrock CloudTrail logging](https://docs.aws.amazon.com/bedrock/latest/userguide/logging-using-cloudtrail.html)
- [Amazon Bedrock AgentCore security](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/security.html)
- [AWS IAM best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)

### Ground-Up Validation Flow (Clean Restart)

Use this exact sequence when validating end-to-end behavior from scratch.

1. Stop all running app services:

```bash
# from repo root
docker compose --profile app down --remove-orphans
```

1. Start the app fresh:

```bash
docker compose --profile app up -d --build app
```

1. Verify API health and runtime state:

```bash
curl http://localhost:8000/
curl http://localhost:8000/status
```

1. If needed, force a clean leave/rejoin cycle:

```bash
SESSION_ID="$(grep '^VONAGE_SESSION_ID=' .env | cut -d= -f2-)"

curl -X POST http://localhost:8000/leave
curl -X POST http://localhost:8000/join \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"${SESSION_ID}\"}"
```

1. Connect from Vonage Playground:

- Open [https://tokbox.com/developer/tools/playground/](https://tokbox.com/developer/tools/playground/)
- Log in to the Vonage account that owns `VONAGE_APPLICATION_ID`
- Join existing session using `VONAGE_SESSION_ID` from `.env`

1. (Optional) Watch live app logs while testing:

```bash
docker compose --profile app logs -f app
```

1. Stop services after validation:

```bash
docker compose --profile app down --remove-orphans
```

### Acceptance Evidence (April 2026)

Use this quick check after a Playground join/leave cycle to confirm app health and clean logs:

```bash
cd /path/to/vonage-pipecat-aws-agentcore
curl -s http://localhost:8000/status
docker compose --profile app logs --tail=300 app | \
grep -E "participant_joined|client_connected|client_disconnected|participant_left|Monitor snapshot|ERROR|Exception|Traceback|RuntimeWarning|Timed out waiting for input events|was never awaited|connection reset by peer"
```

Expected result:

- `running: true`, `last_error: null`, and `event_counts.errors: 0` in `/status`.
- Join/leave counters increment during the Playground session.
- No `ERROR`/`Exception`/`Traceback`/`RuntimeWarning` timeout or await-warning matches in filtered logs.

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
│   ├── c4b_bedrock_nova_sonic/   # Bedrock + Nova Sonic speech-to-speech
│   └── c5_agentcore/             # AgentCore Runtime
├── app/                          # Full integrated agent
└── blog/                         # Blog post + images
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

## Official AWS Bedrock and Nova References

Keep this minimal set for setup, API behavior, and model selection:

- [Amazon Bedrock API reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/welcome.html)
- [Amazon Nova Sonic getting started](https://docs.aws.amazon.com/nova/latest/nova2-userguide/sonic-getting-started.html)
- [Amazon Bedrock model IDs](https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html)

---

## License

[MIT](LICENSE) — Copyright © 2026 Vonage API CSE
