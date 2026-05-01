# app — Full Integrated Agent

This is the complete application that wires all components together:

- **Vonage Video Connector Pipecat transport** — joins the video session and bridges media into Pipecat
- **Pipecat pipeline** — real-time audio processing and session orchestration
- **AWS Nova Sonic** — speech-to-speech AI inside the live media loop
- **AWS Bedrock AgentCore Runtime** — optional bootstrap context for initial assistant behavior
- **FastAPI** — WebSocket management API

## Bedrock vs AgentCore (Why Both?)

These services are complementary:

- **Amazon Bedrock** is the model inference layer for live conversation (Nova Sonic / Nova Lite).
- **Amazon Bedrock AgentCore** is the managed runtime layer for deployable agent app logic.

In this app, Bedrock powers real-time model responses, while AgentCore is optionally invoked at startup (when `AGENTCORE_AGENT_ARN` is set) to prime assistant behavior.

Short version: **Bedrock answers; AgentCore runs deployable agent app logic.**

This app uses the **transport** route, not the serializer route. In practice that means:

- You need the **Vonage Video Linux SDK / Video Connector SDK** available in Linux or Docker.
- You do **not** need the **Vonage Audio Connector SDK** for this sample.
- The Audio Connector SDK only applies to a separate serializer/WebSocket integration pattern that is not used in this repo.

## Transport vs Serializer (When to Choose)

| Option                           | Architecture Shape                                                                    | Choose It When                                                                                              | Official Vonage Docs                                                                                                                                                                                                         |
| -------------------------------- | ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Transport** (implemented here) | Browser/WebRTC <-> Vonage Video Session <-> Video Connector SDK <-> Pipecat transport | You need AI as a session participant in a shared Vonage Video room with join/leave/publish semantics        | [Vonage Pipecat Transport Guide](https://developer.vonage.com/en/video/guides/vonage-video-connector-pipecat-transport), [Vonage Video Connector Guide](https://developer.vonage.com/en/video/guides/vonage-video-connector) |
| **Serializer** (planned Phase 2) | Voice/media stream <-> serializer/WebSocket bridge <-> Pipecat                        | You need telephony-oriented or protocol-level media event control, without room-style participant semantics | [Vonage Audio Connector Guide](https://developer.vonage.com/en/video/guides/audio-connector), [Vonage Voice API Overview](https://developer.vonage.com/en/voice/overview)                                                    |

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
│    VonageVideoConnectorTransport ──► Nova Sonic ──► VonageVideoConnectorTransport
│                                      │
│  Optional startup bootstrap          │
│    AgentCore Runtime ──► initial response style/context
└──────────────────────────────────────┘
```

---

## Prerequisites

- Docker + Docker Compose (macOS / non-Linux)
  **or** Python 3.13.x with uv (native Linux)
- All credentials in the root `.env` file (stages `C1`, `C2`, `C3`, `C4a`, `C4b`, and `C5` passed)

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

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn main:app --host 0.0.0.0 --port 8000
```

## Deploy to Production

`docker compose` is the local/dev path. For production, deploy this app on Linux infrastructure.

Recommended targets:

- **EC2 (single host)**: fastest path from POC to first production deployment.
- **Managed containers**: ECS/Fargate (or EKS/App Runner) for rolling deployments, autoscaling, and managed operations.

### Production Responsibilities (AWS)

- **Amazon Bedrock**: model inference platform.
- **Amazon Nova Sonic**: speech-to-speech model used through Bedrock.
- **Amazon Bedrock AgentCore Runtime**: optional managed runtime bootstrap path in this sample.

Use the correct AWS API surface per call path:

- `bedrock` for control plane model operations ([AWS Bedrock API methods](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-api-methods.html))
- `bedrock-runtime` for inference data plane calls ([AWS Bedrock Runtime examples](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-runtime_example_bedrock-runtime_InvokeModel_AnthropicClaude_section.html))
- `bedrock-agentcore` for AgentCore runtime invocation ([AWS Bedrock AgentCore Data Plane API](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/Welcome.html))

### Minimum Production Checklist

- **Linux runtime**: deploy on Linux (native or container) for Video Connector compatibility.
- **Credentials**: use IAM roles or short-lived credentials; avoid long-lived static keys ([IAM best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)).
- **Least privilege**: scope Bedrock, AgentCore, logs, and secrets permissions to only required actions/resources.
- **Secrets management**: store secrets in AWS Secrets Manager or SSM Parameter Store (not plaintext `.env` in images/repos).
- **Model/region readiness**: verify model ID support and quotas in target region before rollout ([Bedrock model IDs](https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html)).
- **Observability**: collect CloudWatch metrics/logs and enable CloudTrail for API auditing ([Bedrock monitoring](https://docs.aws.amazon.com/bedrock/latest/userguide/monitoring.html), [Bedrock CloudTrail](https://docs.aws.amazon.com/bedrock/latest/userguide/logging-using-cloudtrail.html)).
- **Retries/timeouts**: tune SDK retries/timeouts for voice latency and resilience ([AWS SDK retry behavior](https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html)).
- **Container security**: apply ECS/Fargate security best practices when containerized ([ECS security best practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-best-practices.html)).
- **Session lifecycle**: monitor and tune `NOVA_SESSION_WARN_SECONDS`, `NOVA_SESSION_LIMIT_SECONDS`, and `NOVA_SESSION_STOP_ON_LIMIT` for long-lived calls.

## Runtime Notes

- When `VONAGE_SESSION_ID` is set, the app auto-joins that session on startup.
- `GET /status` is the quickest health check for the live agent pipeline. A healthy startup should show `running: true` and `last_error: null`.
- `connected` may remain `false` until a participant/client actually joins the Vonage session, then transitions to `true`.
- In Docker, the compose service mounts `${HOME}/.aws` to `/root/.aws` and `./private.key` to `/app/private.key`, so the app can reuse the AWS profile and Vonage key material already validated in the test folders.
- If you want to stop the live pipeline without stopping the API process, call `POST /leave`.

## Nova Sonic Reliability Notes

- AWS Nova Sonic sessions have a practical connection window (about 8 minutes in AWS guidance).
- The app now emits `session_renewal_recommended` before that window expires so callers can refresh via `POST /leave` + `POST /join`.
- To force-stop at the limit for strict session hygiene, set `NOVA_SESSION_STOP_ON_LIMIT=true`.
- Default behavior is non-breaking (`NOVA_SESSION_STOP_ON_LIMIT=false`): warning events/logs are emitted, but the pipeline is not force-stopped.

## End-to-End Test (From Scratch)

Use this sequence for a clean, repeatable validation run:

1. Stop all app containers:

```bash
# from repo root
docker compose --profile app down --remove-orphans
```

1. Start fresh app container:

```bash
docker compose --profile app up -d --build app
```

1. Confirm API is up:

```bash
curl http://localhost:8000/
curl http://localhost:8000/status
```

1. Rejoin explicitly only if needed (for example after a manual leave):

```bash
SESSION_ID="$(grep '^VONAGE_SESSION_ID=' .env | cut -d= -f2-)"

curl -X POST http://localhost:8000/join \
        -H "Content-Type: application/json" \
        -d "{\"session_id\":\"${SESSION_ID}\"}"
```

1. Open Vonage Playground and connect to the existing session:

- [https://tokbox.com/developer/tools/playground/](https://tokbox.com/developer/tools/playground/)
- Log in to the same Vonage account that owns your `VONAGE_APPLICATION_ID`
- Paste `VONAGE_SESSION_ID` from `.env` into the existing session flow

1. Optional: tail logs during the test:

```bash
docker compose --profile app logs -f app
```

1. Stop when done:

```bash
docker compose --profile app down --remove-orphans
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

| Variable                          | Description                                                                        |
| --------------------------------- | ---------------------------------------------------------------------------------- |
| `VONAGE_APPLICATION_ID`           | Vonage Video API application ID                                                    |
| `VONAGE_PRIVATE_KEY`              | Path to Vonage private key file                                                    |
| `VONAGE_SESSION_ID`               | Vonage Video session to join on startup                                            |
| `AWS_PROFILE`                     | AWS CLI profile name (recommended, e.g. `vonage-dev`)                              |
| `AWS_ACCESS_KEY_ID`               | AWS access key (optional fallback if not using profile)                            |
| `AWS_SECRET_ACCESS_KEY`           | AWS secret key (optional fallback if not using profile)                            |
| `AWS_REGION`                      | AWS region (default: `us-east-1`)                                                  |
| `BEDROCK_MODEL_ID`                | Nova Sonic model ID (default: `amazon.nova-2-sonic-v1:0`)                          |
| `BEDROCK_CONNECT_TIMEOUT_SECONDS` | Bedrock API connect timeout in seconds (default: `10`)                             |
| `BEDROCK_READ_TIMEOUT_SECONDS`    | Bedrock API read timeout in seconds (default: `60`)                                |
| `BEDROCK_MAX_ATTEMPTS`            | Bedrock API max retry attempts, standard mode (default: `4`)                       |
| `BEDROCK_VALIDATE_MODEL_ID`       | Validate `BEDROCK_MODEL_ID` at startup; fail fast on invalid IDs (default: `true`) |
| `AGENTCORE_AGENT_ARN`             | Optional AgentCore runtime ARN used for startup bootstrap                          |
| `NOVA_SESSION_WARN_SECONDS`       | Emit renewal recommendation event after this many seconds (default: `410`)         |
| `NOVA_SESSION_LIMIT_SECONDS`      | Session limit threshold used by monitor telemetry (default: `470`)                 |
| `NOVA_SESSION_STOP_ON_LIMIT`      | When `true`, cancels the pipeline at the limit to force renewal (default: `false`) |
| `PORT`                            | FastAPI port (default: `8000`)                                                     |

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

## Official AWS Bedrock and Nova References

Keep this minimal set for setup, API behavior, and model selection:

- [Amazon Bedrock API reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/welcome.html)
- [Amazon Nova Sonic getting started](https://docs.aws.amazon.com/nova/latest/nova2-userguide/sonic-getting-started.html)
- [Amazon Bedrock model IDs](https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html)
