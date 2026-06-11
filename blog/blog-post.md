# Deploy an AI Video Agent using Vonage Video Transport for Pipecat, Nova Sonic, and AWS Bedrock AgentCore

This post walks through deploying a production AI voice agent that joins a Vonage Video session as a native WebRTC participant, listens and speaks with **Amazon Nova Sonic** in real time, and runs the full pipeline on **AWS Bedrock AgentCore Runtime**.

The project — production deploy artifacts and architecture diagrams — lives at [github.com/nexmo-se/vonage-pipecat-aws-agentcore](https://github.com/nexmo-se/vonage-pipecat-aws-agentcore). See the root [README](../README.md) for the source of truth.

> **Status (June 2026):** Full agent on AgentCore + App Runner orchestrator + Playground demo validated end-to-end.

---

## Introduction

This architecture wires together four components:

1. **Vonage Video Transport for Pipecat** (`VonageVideoConnectorTransport`) — joins a Vonage Video session as a WebRTC participant via the Video Connector SDK
2. **Pipecat** — real-time audio pipeline orchestration
3. **Amazon Bedrock with Nova Sonic** — speech-to-speech inference inside the live media loop
4. **Amazon Bedrock AgentCore Runtime** — hosts the **entire** agent (transport + Pipecat + Nova Sonic)

By the end you will understand:

- How browser audio flows through Vonage Video into Pipecat and back in production
- How to deploy the agent to AgentCore and trigger it from App Runner
- Why WebRTC inside AgentCore requires Vonage SDK-managed TURN

---

## What you are building

Production is two deploy artifacts:

| Component | Folder | Role |
| --- | --- | --- |
| **Agent** | `runtime/` | Full pipeline on AgentCore (`runtime/agent.py`) |
| **Orchestrator** | `answer/` | Thin HTTP API on App Runner — `POST /start-agent` → `InvokeAgentRuntime` |

---

## Bedrock vs AgentCore

| Layer | Service | Role |
| --- | --- | --- |
| Model inference | **Amazon Bedrock** | Nova Sonic speech-to-speech inside Pipecat |
| Agent hosting | **Amazon Bedrock AgentCore Runtime** | Runs the full agent in a managed microVM |

Bedrock is called from **inside** AgentCore via the execution role IAM. App Runner only invokes AgentCore — it does not run inference or media.

Nova Sonic is **inside** the Pipecat pipeline. AgentCore is not a separate inference hop the way App Runner is an orchestration hop.

**Bedrock powers the model; AgentCore hosts the deployable agent.**

---

## Architecture

![Production architecture](../images/architecture-overview-production.png)

```text
Browser (Playground or future React client)
  ↓ WebRTC
Vonage Video Session
  ↓
App Runner (answer/) — POST /start-agent → InvokeAgentRuntime
  ↓ payload: {action, session_id, token, mode}
AgentCore Runtime (runtime/) — VonageVideoConnectorTransport + Pipecat + Nova Sonic
  ↓ Bedrock (via execution role inside microVM)
Audio back to session participants
```

1. User joins a Vonage session and publishes their mic.
2. A client calls `POST /start-agent` on App Runner with `{ session_id, token }`.
3. App Runner invokes AgentCore Runtime with `action: join`.
4. **Vonage Video Transport for Pipecat** joins the session as a WebRTC participant (SDK-managed TURN).
5. Pipecat invokes **Amazon Nova Sonic on Bedrock**.
6. Agent audio routes back through Vonage to the user.

Deploy:

- **`runtime/`** → `agentcore deploy` — agent (**linux/arm64**, Python 3.13)
- **`answer/`** → `answer/deploy.sh` — orchestrator (**linux/amd64**)

Invoke payload:

```json
{"action":"join","session_id":"...","token":"...","mode":"nova_sonic"}
```

App Runner tracks `runtimeSessionId` in memory per client — use the same session for `GET /status` and `POST /leave` after a join.

### AgentCore runtime ARN (required)

App Runner (`answer/`) must know **which** AgentCore runtime to invoke. Every `POST /start-agent` becomes `bedrock-agentcore:InvokeAgentRuntime` against that ARN.

| Where | Variable | When |
| --- | --- | --- |
| Root `.env` | `AGENTCORE_RUNTIME_ARN` | After `agentcore deploy` — **before** `answer/deploy.sh` |
| App Runner service env | `AGENTCORE_RUNTIME_ARN` | Set automatically by `answer/deploy.sh` from your `.env` |
| AgentCore container | *(none)* | The agent **is** the runtime — it does not invoke itself |

`answer/deploy.sh` sources root `.env`, then resolves the runtime ARN in this order: `AGENTCORE_RUNTIME_ARN` → `C6_AGENTCORE_RUNTIME_ARN` → `AGENTCORE_AGENT_ARN` → hardcoded POC default. It injects `AGENTCORE_RUNTIME_ARN` into the App Runner service env.

`answer/smoke_local.py` calls App Runner over HTTPS; it does **not** need the ARN in your shell — App Runner already has it. Verify with `curl` that health returns `"runtime_arn_set": true`.

### Pipecat pipeline

```text
VonageVideoConnectorTransport.input()
  → context aggregator (user)
  → Amazon Nova Sonic (Bedrock)
  → context aggregator (assistant)
  → VonageVideoConnectorTransport.output()
```

Audio: **16 kHz mono in**, **24 kHz mono out**.

AgentCore also supports **`echo`** mode — loopback without Nova Sonic — useful to validate WebRTC before enabling the full model.

### Transport vs Serializer

This repo uses **Transport** (native Vonage Video participant):

`Browser ↔ Vonage Video ↔ Video Connector SDK ↔ Pipecat`

For telephony WebSocket streams, see [vonage-pipecat-serializer-voice-aws-agentcore](https://github.com/nexmo-se/vonage-pipecat-serializer-voice-aws-agentcore).

---

## Why AgentCore + App Runner?

**The full agent runs in AgentCore.** Runtime is invoked with `{session_id, token, mode}` and then runs a **long-lived WebRTC pipeline** — not a REST API browsers call directly.

**App Runner (`answer/`)** validates input → `InvokeAgentRuntime` → returns status. No Pipecat, no media, no Bedrock on App Runner.

**Vonage SDK-managed TURN** is required — AgentCore microVMs have **no public IP**. The Video Connector SDK negotiates session-specific TURN at join. Allow egress to `*.tokbox.com`, `*.opentok.com`, and `*.vonage.com`.

---

## Prerequisites

- [Vonage account](https://dashboard.vonage.com) with a Video API application and `private.key`
- AWS account with **Nova Sonic** enabled (`amazon.nova-2-sonic-v1:0`) in your region
- Docker Desktop (for `agentcore deploy --local-build` on macOS)
- Python 3.13 and the AgentCore CLI

### Clone and configure

```bash
git clone https://github.com/nexmo-se/vonage-pipecat-aws-agentcore.git
cd vonage-pipecat-aws-agentcore
cp .env.example .env
```

Root `.env` (quote persona strings for zsh):

```bash
VONAGE_APPLICATION_ID=...
VONAGE_PRIVATE_KEY=private.key
AWS_PROFILE=vonage-dev
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=amazon.nova-2-sonic-v1:0

# Persona — passed to AgentCore at deploy time
AGENTCORE_BOOTSTRAP_PROMPT="You are a nurse triage voice assistant. Ask one short question at a time..."
BEDROCK_INITIAL_USER_MESSAGE="Hello, I am your nurse intake assistant. What symptoms are you experiencing today?"

# Set after Step 2 (agentcore deploy) — required before Step 3 (App Runner deploy)
# AGENTCORE_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-east-1:ACCOUNT:runtime/video_agent-...
```

Place `private.key` in the repo root.

### AWS setup

```bash
aws configure --profile vonage-dev
aws sts get-caller-identity --profile vonage-dev
export AWS_PROFILE=vonage-dev
export AWS_REGION=us-east-1
```

Enable Nova Sonic in the [Bedrock Model Access console](https://console.aws.amazon.com/bedrock/home#/modelaccess).

Four AWS identities: developer profile, AgentCore execution role, App Runner instance role, App Runner access role. Details: [docs/AWS_IAM.md](../docs/AWS_IAM.md).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install bedrock-agentcore-starter-toolkit
```

---

## Step 1 — Create a Vonage Video session

Create a session with the Vonage Video API (or your backend). You need `session_id` and a publisher `token` for the agent.

```python
from vonage import Auth, Vonage
from vonage_video import SessionOptions, TokenOptions

client = Vonage(Auth(application_id=application_id, private_key=private_key_path))
session = client.video.create_session(SessionOptions(media_mode="routed"))
session_id = session.id

token = client.video.generate_client_token(
    TokenOptions(session_id=session_id, role="publisher")
)
```

For the demo flow, set `VONAGE_SESSION_ID` in `.env` so `answer/smoke_local.py` can pass the same session to App Runner.

---

## Step 2 — Deploy the agent (AgentCore)

See [runtime/README.md](../runtime/README.md) for one-time `agentcore configure --create` and Dockerfile generation.

Validate WebRTC with **`echo`** mode before enabling Nova Sonic full.

```bash
cd runtime
cp ../private.key ./private.key
set -a && source ../.env && set +a

echo "opening: ${#BEDROCK_INITIAL_USER_MESSAGE} bootstrap: ${#AGENTCORE_BOOTSTRAP_PROMPT}"
# expect non-zero counts — if 0, fix .env quoting

AWS_PROFILE=vonage-dev ../.venv/bin/agentcore deploy \
  -a video_agent \
  --local-build \
  --auto-update-on-conflict \
  --env "VONAGE_APPLICATION_ID=${VONAGE_APPLICATION_ID}" \
  --env "VONAGE_PRIVATE_KEY=private.key" \
  --env "BEDROCK_MODEL_ID=${BEDROCK_MODEL_ID}" \
  --env "BEDROCK_INITIAL_USER_MESSAGE=${BEDROCK_INITIAL_USER_MESSAGE}" \
  --env "AGENTCORE_BOOTSTRAP_PROMPT=${AGENTCORE_BOOTSTRAP_PROMPT}"
```

Persona is **deploy-time only** — root `.env` is not read inside the AgentCore container:

- `AGENTCORE_BOOTSTRAP_PROMPT` → Nova Sonic `system_instruction`
- `BEDROCK_INITIAL_USER_MESSAGE` → required opening line

CloudWatch logs `opening_chars=N` on join. **`N=0` means persona vars were missing.**

**Required:** copy the runtime ARN from deploy output into root `.env` before Step 3:

```bash
AGENTCORE_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/video_agent-ErxQpSHrDP
```

App Runner cannot invoke your agent without this value (or a matching hardcoded default in `answer/deploy.sh`).

---

## Step 3 — Deploy the orchestrator (App Runner)

`answer/deploy.sh` builds the orchestrator image, creates/updates the App Runner service, and injects `AGENTCORE_RUNTIME_ARN` from your `.env` into the running service.

Confirm `AGENTCORE_RUNTIME_ARN` is set in `.env` (from Step 2), then deploy. See [answer/README.md](../answer/README.md).

```bash
# Verify ARN is loaded
grep AGENTCORE_RUNTIME_ARN .env

AWS_PROFILE=vonage-dev bash answer/deploy.sh --inline-private-key

# Updates
AWS_PROFILE=vonage-dev bash answer/deploy.sh --inline-private-key --update-only
```

Verify rollout — **`runtime_arn_set` must be `true`**:

```bash
curl -s https://YOUR_APP_RUNNER_URL/
# Expect: "runtime_arn_set": true, "build": "...", "vonage_app_id_set": true, "vonage_key_set": true
```

If `runtime_arn_set` is `false`, App Runner has no target runtime — `/start-agent` will fail with a 500.

---

## Step 4 — Run the production demo

Creating a session does **not** start the agent. Playground does **not** invoke AgentCore. Call `/start-agent`.

```bash
# 0) Optional cleanup
ANSWER_BASE_URL=https://YOUR_APP_RUNNER_URL \
  .venv/bin/python answer/smoke_local.py --leave

# 1) Create a Vonage session — set VONAGE_SESSION_ID in .env (Step 1)

# 2) Playground → Join existing session → publish mic

# 3) Start agent
ANSWER_BASE_URL=https://YOUR_APP_RUNNER_URL \
  AWS_PROFILE=vonage-dev .venv/bin/python answer/smoke_local.py

# 4) Cleanup before re-running
ANSWER_BASE_URL=https://YOUR_APP_RUNNER_URL \
  AWS_PROFILE=vonage-dev .venv/bin/python answer/smoke_local.py --leave
```

`smoke_local.py` mints the Vonage token from `private.key` and calls App Runner. App Runner invokes AgentCore; the agent joins with your deployed persona.

### Session lifecycle rules

| Rule | Why |
| --- | --- |
| **Join existing session** in Playground | “Create new session” is a different room |
| One session ID per demo run | Mismatch if `.env` changes while Playground is connected |
| Call **`/start-agent`** | Playground alone does not start the agent |
| Run **`leave`** before re-running | Multiple agent participants stack in one session |

---

## SDK snippets (production)

Authoritative code: [`runtime/agent.py`](../runtime/agent.py).

### Vonage Video Transport for Pipecat

```python
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
        audio_in_channels=1,
        audio_out_sample_rate=24000,
        audio_out_channels=1,
        audio_in_auto_subscribe=True,
        video_in_auto_subscribe=False,
    ),
)
```

### Nova Sonic pipeline

```python
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.services.aws.nova_sonic.llm import AWSNovaSonicLLMService, Params
from pipecat.frames.frames import LLMContextFrame, LLMRunFrame

context = LLMContext(messages=[...])
context_aggregator = LLMContextAggregatorPair(context)

nova_sonic = AWSNovaSonicLLMService(
    access_key_id=creds.access_key,
    secret_access_key=creds.secret_key,
    session_token=creds.token,
    region="us-east-1",
    model="amazon.nova-2-sonic-v1:0",
    params=Params(
        input_sample_rate=16000,
        input_channel_count=1,
        output_sample_rate=24000,
        output_channel_count=1,
    ),
    system_instruction=system_instruction,
)

pipeline = Pipeline([
    transport.input(),
    context_aggregator.user(),
    nova_sonic,
    context_aggregator.assistant(),
    transport.output(),
])

task = PipelineTask(
    pipeline,
    params=PipelineParams(allow_interruptions=True),
    enable_rtvi=False,
    cancel_on_idle_timeout=False,
    idle_timeout_secs=None,
)
await PipelineRunner().run(task)

# On connect — avoid Nova Sonic idle timeout (~55s)
await task.queue_frame(LLMContextFrame(context))
await task.queue_frame(LLMRunFrame())
```

---

## Production checklist

- Full agent on AgentCore (`runtime/`) — ARM64, Python 3.13
- App Runner invokes AgentCore only — no media on orchestrator
- App Runner has `AGENTCORE_RUNTIME_ARN` configured (`runtime_arn_set: true` on health)
- Persona via `agentcore deploy --env`
- Echo mode pass before Nova Sonic full
- Vonage TURN egress from AgentCore microVM
- Secrets via IAM roles; Vonage key in Secrets Manager or inline POC
- CloudWatch + App Runner health `build` field to confirm rollout
- Optional: React client + CORS on `answer/`

---

## Troubleshooting

| Symptom | Likely cause | What to try |
| --- | --- | --- |
| No agent in Playground | `/start-agent` not called | Run `smoke_local.py` after joining |
| Wrong room | Created new session | Join existing + match `VONAGE_SESSION_ID` |
| Join OK, no audio | TURN / networking | Egress, `enable_rtvi=False`, Python 3.13 |
| `opening_chars=0` | Persona missing in container | Redeploy with quoted `.env` |
| Stacked agents | Skipped `leave` | `smoke_local.py --leave` |
| `runtime_arn_set: false` on health | ARN missing on App Runner | Set `AGENTCORE_RUNTIME_ARN` in `.env`, re-run `answer/deploy.sh` |

---

## Conclusion

This production stack:

- Joins Vonage Video as a native WebRTC participant via **Vonage Video Transport for Pipecat**
- Runs **Amazon Nova Sonic** in a streaming Pipecat pipeline on **AgentCore**
- Starts on demand through **App Runner**

**Deploy path:** create session → deploy `runtime/` → deploy `answer/` → smoke test.

**Repository:** [github.com/nexmo-se/vonage-pipecat-aws-agentcore](https://github.com/nexmo-se/vonage-pipecat-aws-agentcore)

---

## References

**Vonage:** [Video API](https://developer.vonage.com/en/video/overview) · [Video Connector](https://developer.vonage.com/en/video/guides/vonage-video-connector) · [Pipecat transport](https://developer.vonage.com/en/video/guides/vonage-video-connector-pipecat-transport)

**AWS:** [Bedrock model IDs](https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html) · [Nova Sonic](https://docs.aws.amazon.com/nova/latest/nova2-userguide/sonic-getting-started.html) · [AgentCore security](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/security.html) · [Pipecat + AgentCore (AWS blog)](https://aws.amazon.com/blogs/machine-learning/deploy-voice-agents-with-pipecat-and-amazon-bedrock-agentcore-runtime-part-1/)

**In this repo:** [README](../README.md) · [runtime/README.md](../runtime/README.md) · [answer/README.md](../answer/README.md) · [docs/AWS_IAM.md](../docs/AWS_IAM.md)

---

## Credits

Built with care by the Vonage API CSE team. [MIT License](../LICENSE).
