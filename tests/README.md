# Tests — Staged Validation Path

This folder is a **staged validation path** for Vonage Video + Pipecat + Nova Sonic + AgentCore — not a collection of isolated smoke tests.

**Goals:**

- Prove each layer before combining everything end to end.
- Keep each stage useful as a building block for `app/` (local dev) and `runtime/` + `answer/` (production).

Run folders **in order**. Details for each stage live in that folder's README.

---

## Validated Results (June 2026)

| Test | What it proves | Status | Notes |
| --- | --- | --- | --- |
| C1 | Vonage session + token API | ✅ Pass | Creates fresh session → root `.env` `VONAGE_SESSION_ID` |
| C2 | Video Connector SDK join | ✅ Pass | Linux/Docker |
| C3 | Pipecat transport echo | ✅ Pass | Distorted echo OK; **control test when C6 fails** |
| C4a | Bedrock credentials | ✅ Pass | Nova Lite preflight |
| C4b | Nova Sonic speech-to-speech | ✅ Pass | Nurse triage persona via `.env` |
| C5 | AgentCore deploy/invoke | ✅ Pass | Hello-world runtime |
| C6 Stage 2 | AgentCore network probe | ✅ Pass | `pass_vonage_sdk` on `video_agent` |
| C6 Stage 3 | Echo in AgentCore | ✅ Pass | `C6 Echo Agent` in Playground |
| C6 Stage 5 | Nova Sonic full in AgentCore | ✅ Pass | Nurse triage; persona via deploy `--env` |
| Phase 1 local | `answer/` orchestrator E2E | ✅ Pass | `smoke_local.py` → nurse triage |
| Phase 1 App Runner | `answer/` on App Runner | ✅ Pass | See [answer/README.md](../answer/README.md) |

**Production runtime ARN:** `arn:aws:bedrock-agentcore:us-east-1:589536902306:runtime/video_agent-ErxQpSHrDP`

**Historical note:** Early C6 on `c6_video_agent-ALpVCJGN0S` — join OK, zero inbound RTP. Fixed with `runtime/agent.py`, Python 3.13, `enable_rtvi=False`.

---

## Test Index

| # | Folder | What it tests | Platform | README |
| --- | --- | --- | --- | --- |
| C1 | [c1_vonage_video_session](c1_vonage_video_session/) | Session creation + client token | Any | [README](c1_vonage_video_session/README.md) |
| C2 | [c2_video_connector_sdk](c2_video_connector_sdk/) | SDK joins as WebRTC participant | Linux / Docker | [README](c2_video_connector_sdk/README.md) |
| C3 | [c3_pipecat_transport](c3_pipecat_transport/) | Pipecat echo over Vonage transport | Linux / Docker | [README](c3_pipecat_transport/README.md) |
| C4a | [c4a_aws_bedrock](c4a_aws_bedrock/) | Bedrock credentials + text inference | Linux / Docker | [README](c4a_aws_bedrock/README.md) |
| C4b | [c4b_bedrock_nova_sonic](c4b_bedrock_nova_sonic/) | Nova Sonic speech-to-speech | Linux / Docker | [README](c4b_bedrock_nova_sonic/README.md) |
| C5 | [c5_agentcore](c5_agentcore/) | AgentCore deploy + invoke | Any (AWS) | [README](c5_agentcore/README.md) |
| C6 | [c6_agentcore_video_transport](c6_agentcore_video_transport/) | Full WebRTC pipeline in AgentCore | ARM64 deploy | [README](c6_agentcore_video_transport/README.md) |

---

## What Each Stage Proves

### C1 — Vonage Video Session Creation

**Validates:** Vonage Video API auth, session provisioning, client token generation.

- Writes `VONAGE_SESSION_ID` to root `.env`
- Provides Playground URL for manual join
- **Platform:** Any (macOS, Linux, Windows)

**When done:** Real session ID in `.env`; you can join in Playground.

---

### C2 — Vonage Video Connector SDK

**Validates:** Native **Video Connector SDK** joins a Vonage session as a server-side WebRTC participant.

- First Linux-native step (Docker on macOS)
- Bridge between Vonage session and Pipecat (foundation for C3)

**When done:** Connector participant visible in Playground.

---

### C3 — Pipecat Transport Echo Bot

**Validates:** **Pipecat** + **VonageVideoConnectorTransport** echo loop.

- Full media path: browser → Vonage → Connector → Pipecat → Vonage → browser
- No LLM — isolates transport
- **Control test:** if C6 fails but C3 passes, debug AgentCore networking — not transport code

**When done:** Distorted echo in Playground; round-trip latency acceptable.

---

### C4a — AWS Bedrock Credential Check

**Validates:** AWS credentials, Bedrock access, Nova Lite text inference.

- Lower-cost preflight before C4b/C6

**When done:** Bedrock connectivity confirmed.

---

### C4b — Bedrock + Nova Sonic Integration

**Validates:** **Nova Sonic** speech-to-speech on the Vonage transport pipeline.

- Same transport shape as C3; adds live ML
- Nurse triage persona via root `.env`

**When done:** Ask a question in Playground; agent responds with AI speech.

---

### C5 — AWS Bedrock AgentCore Runtime

**Validates:** AgentCore runtime **deploy** and **invoke** (hello-world).

- Proves `bedrock-agentcore` API and deployment workflow
- In local `app/` only, C5 pattern can bootstrap persona; **production** embeds persona in `runtime/agent.py` via deploy `--env`

**When done:** Runtime ARN captured; invoke works programmatically.

---

### C6 — AgentCore + Video Connector (production gate)

**Validates:** Full `VonageVideoConnectorTransport` pipeline inside **Bedrock AgentCore Runtime** (Michael's requirement).

- Deploy artifact: [`runtime/`](../runtime/README.md) → `video_agent` (ARM64, Python 3.13)
- Test harness: [c6_agentcore_video_transport/](c6_agentcore_video_transport/README.md)
- **C6 PASS** → deploy `runtime/` + `answer/` (agent in AgentCore)
- Nova Sonic full (`--stage full`) requires persona vars in `agentcore deploy --env`

**When done:** Echo and nurse triage heard in Playground with agent running in AgentCore microVM.

---

## Progression

```text
C1: Vonage auth + session
C2: Video Connector joins session
C3: Pipecat transport over Vonage          ← control for C6 media failures
C4a: Bedrock credentials + text model
C4b: Bedrock + Nova Sonic speech pipeline
C5: AgentCore deploy/invoke
C6: AgentCore + live WebRTC pipeline       ← Michael's gate
Phase 1: answer/ E2E (local + App Runner)  ← production invoke path

app/      = C3 transport + C4b speech (local dev, agent on your machine)
runtime/  = C6 production agent (AgentCore) — same Pipecat pipeline as app/
answer/   = HTTP orchestrator → InvokeAgentRuntime (no media)
```

See root [README.md](../README.md) for the full local vs production code map.

---

## Quick Start

From repo root:

```bash
cp .env.example .env
# Fill in VONAGE_APPLICATION_ID, private key path, AWS settings

export AWS_PROFILE=vonage-dev
aws sts get-caller-identity --profile vonage-dev

# C1 — creates VONAGE_SESSION_ID in root .env
cd tests/c1_vonage_video_session
uv run --with python-dotenv --with vonage python test_session.py
cd ../..

# Continue C2 → C6 in order — see each folder's README
```

**Prerequisites:** Python 3.11+, Docker (C2–C4b), Vonage Video app, AWS profile with Bedrock + AgentCore access. See **[docs/AWS_IAM.md](../docs/AWS_IAM.md)** for credentials, IAM policies, and org SCP rules.

---

## C6 Manual Workflow (validated)

C1 creates a session only. The agent joins when C6 invokes AgentCore — **not** when you open Playground.

```text
0. leave     test_agentcore_video.py --stage leave   (cleanup)
1. C1        test_session.py once → VONAGE_SESSION_ID in root .env
2. Playground  Join existing session → paste Session ID from .env
               API Key if asked: VONAGE_APPLICATION_ID
               Connect → Publish mic
3. C6 echo   test_agentcore_video.py --stage echo → wait for connected: true
4. leave     REQUIRED before switching to Nova Sonic
5. C6 full   test_agentcore_video.py --stage full → nurse triage opening
6. leave     cleanup
```

Run from `tests/c6_agentcore_video_transport/` using repo-root `.venv`:

```bash
../../.venv/bin/python test_agentcore_video.py --stage echo
```

---

## Phase 1 E2E (post-C6)

After C6 passes, validate the production orchestrator path. Same session rule: C1 + Playground do **not** start the agent alone.

```text
1. C1        test_session.py once
2. Playground  Join existing session → publish mic
3. smoke       ANSWER_BASE_URL=https://x9bqavn3zv.us-east-1.awsapprunner.com \
                 .venv/bin/python answer/smoke_local.py    # from repo root
4. leave       same URL + answer/smoke_local.py --leave
```

See [answer/README.md](../answer/README.md) for App Runner deploy and local `answer/server.py` testing.

---

## Rules Learned in Testing

- Playground: **Join existing session** — never **Create new session** (different room than C1/C6).
- Run C1 **once** per test — re-running C1 changes `.env` while Playground still holds the old session.
- Run **`--stage leave`** (C6) or **`smoke_local.py --leave`** before a new agent — one agent per session.
- C6 uses **repo-root** `.venv` — C1's isolated venv lacks `boto3`.
- `agentcore deploy` uses **repo-root** `.venv/bin/agentcore` from `runtime/`.
- Persona in production: pass `AGENTCORE_BOOTSTRAP_PROMPT` and `BEDROCK_INITIAL_USER_MESSAGE` via `agentcore deploy --env` (root `.env` is not mounted in AgentCore).

---

## How Tests Connect to the Full App

The full app in [`app/`](../app/README.md) builds on C3 transport + C4b Nova Sonic for **local dev**.

Production ([`runtime/`](../runtime/README.md) + [`answer/`](../answer/README.md)) builds on **C6 pass** — same transport and pipeline, hosted in AgentCore and triggered via App Runner.

Architecture and rationale: root [`README.md`](../README.md).
