# app — Full Integrated Agent

This is the complete application that wires all components together:

- **Vonage Video Connector** — joins the video session as a WebRTC participant
- **Pipecat pipeline** — real-time audio processing
- **AWS Nova Sonic** — speech-to-speech AI (STT + TTS)
- **AWS Bedrock AgentCore** — LLM reasoning and business logic
- **FastAPI** — WebSocket management API

**Platform: Linux** (Vonage Video Connector SDK is a native Linux binary). Use Docker on macOS.

---

## Architecture

```
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
│    VonageTransport ──► NovaSonic ──► AgentCore ──► NovaSonic ──► VonageTransport
└──────────────────────────────────────┘
```

---

## Prerequisites

- Docker + Docker Compose (macOS / non-Linux)
  **or** Python 3.11+ with uv (native Linux)
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

| Endpoint | Method | Description |
|---|---|---|
| `GET /` | HTTP | Health check — returns `{"status": "ok"}` |
| `GET /status` | HTTP | Agent status (connected session, pipeline state) |
| `POST /join` | HTTP | Instruct agent to join a Vonage session |
| `POST /leave` | HTTP | Instruct agent to leave the current session |
| `WS /ws` | WebSocket | Real-time events (participant joined/left, transcript) |

---

## Environment Variables

All variables are loaded from the root `.env` file (see `.env.example`):

| Variable | Description |
|---|---|
| `VONAGE_APPLICATION_ID` | Vonage Video API application ID |
| `VONAGE_PRIVATE_KEY` | Path to Vonage private key file |
| `VONAGE_SESSION_ID` | Vonage Video session to join on startup |
| `AWS_ACCESS_KEY_ID` | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `AWS_REGION` | AWS region (default: `us-east-1`) |
| `BEDROCK_MODEL_ID` | Nova Sonic model ID (default: `amazon.nova-sonic-v1:0`) |
| `AGENTCORE_AGENT_ARN` | ARN of deployed AgentCore agent |
| `PORT` | FastAPI port (default: `8000`) |
