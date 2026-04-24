# app — Full Integrated Agent

This is the complete application that wires all components together:

- **Vonage Video Connector Pipecat transport** — joins the video session and bridges media into Pipecat
- **Pipecat pipeline** — real-time audio processing
- **AWS Nova Sonic** — speech-to-speech AI (STT + TTS)
- **AWS Bedrock AgentCore** — LLM reasoning and business logic
- **FastAPI** — WebSocket management API

This app uses the **transport** route, not the serializer route. In practice that means:

- You need the **Vonage Video Linux SDK / Video Connector SDK** available in Linux or Docker.
- You do **not** need the **Vonage Audio Connector SDK** for this sample.
- The Audio Connector SDK only applies to a separate serializer/WebSocket integration pattern that is not used in this repo.

**Platform: Linux** (Vonage Video Connector SDK is a native Linux binary). Use Docker on macOS.

> **Public Beta:** The Vonage Video Connector Pipecat integration is currently in beta. Official transport docs: [Vonage Video Connector Pipecat transport guide](https://developer.vonage.com/en/video/guides/vonage-video-connector-pipecat-transport). Official source repo: [Vonage/pipecat](https://github.com/Vonage/pipecat).

---

## Architecture

```text
Browser (mic/speaker)
        │  WebRTC
        ▼
Vonage Video Platform
        │  WebRTC (Video Connector SDK)
        ▼
┌──────────────────────────────────────┐
│  Python Agent (Docker / Linux)       │
│                                      │
│  FastAPI (port 8000)                 │
│    └── /ws  WebSocket management     │
│                                      │
│  Pipecat Pipeline                    │
│    VonageVideoConnectorTransport ──► NovaSonic ──► AgentCore ──► NovaSonic ──► VonageVideoConnectorTransport
└──────────────────────────────────────┘
```

---

## Prerequisites

- Docker + Docker Compose (macOS / non-Linux)
  **or** Python 3.13.x with uv (native Linux)
- All credentials in the root `.env` file (all tests C1–C5 passed)

---

## Run (macOS — Docker)

```bash
# From the repo root
docker compose --profile app up --build
```

The agent starts listening on `http://localhost:8000`.

## Run (native Linux)

```bash
cd app

uv venv
uv pip install -r pyproject.toml   # or: uv sync

uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## API

| Endpoint      | Method    | Description                                            |
| ------------- | --------- | ------------------------------------------------------ |
| `GET /`       | HTTP      | Health check — returns `{"status": "ok"}`              |
| `GET /status` | HTTP      | Agent status (connected session, pipeline state)       |
| `POST /join`  | HTTP      | Instruct agent to join a Vonage session                |
| `POST /leave` | HTTP      | Instruct agent to leave the current session            |
| `WS /ws`      | WebSocket | Real-time events (participant joined/left, transcript) |

---

## Environment Variables

All variables are loaded from the root `.env` file (see `.env.example`):

| Variable                | Description                                             |
| ----------------------- | ------------------------------------------------------- |
| `VONAGE_APPLICATION_ID` | Vonage Video API application ID                         |
| `VONAGE_PRIVATE_KEY`    | Path to Vonage private key file                         |
| `VONAGE_SESSION_ID`     | Vonage Video session to join on startup                 |
| `AWS_PROFILE`           | AWS CLI profile name (recommended, e.g. `vonage-dev`)   |
| `AWS_ACCESS_KEY_ID`     | AWS access key (optional fallback if not using profile) |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key (optional fallback if not using profile) |
| `AWS_REGION`            | AWS region (default: `us-east-1`)                       |
| `BEDROCK_MODEL_ID`      | Nova Sonic model ID (default: `amazon.nova-sonic-v1:0`) |
| `AGENTCORE_AGENT_ARN`   | ARN of deployed AgentCore agent                         |
| `PORT`                  | FastAPI port (default: `8000`)                          |

---

## Official Vonage References

Use Vonage-authored docs as source-of-truth when extending this app:

- [Vonage Video API overview](https://developer.vonage.com/en/video/overview)
- [Vonage Video Python Server SDK docs](https://developer.vonage.com/en/video/server-sdks/python)
- [Vonage Python SDK Video API examples](https://github.com/Vonage/vonage-python-sdk/blob/main/video/README.md)
- [Vonage Video Connector guide](https://developer.vonage.com/en/video/guides/vonage-video-connector)
- [Vonage Pipecat transport guide](https://developer.vonage.com/en/video/guides/vonage-video-connector-pipecat-transport)
- [Vonage Audio Connector guide (serializer/WebSocket related)](https://developer.vonage.com/en/video/guides/audio-connector)
- [Vonage Voice API overview (Phase 2 Serializer/Voice scope)](https://developer.vonage.com/en/voice/overview)
