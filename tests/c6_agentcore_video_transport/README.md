# C6 — AgentCore + Vonage Video Connector

**Decision gate:** Can `VonageVideoConnectorTransport` run inside Amazon Bedrock AgentCore Runtime with **Vonage SDK-managed TURN** (no third-party relay)?

## Verdict (June 2026 — updated)

**PASS for WebRTC audio on production runtime `video_agent`.** Nova Sonic full pipeline validated after persona redeploy.

| Stage | Result | Notes |
|---|---|---|
| 0 — pre-flight | ✅ Pass | Vonage creds, token gen, tooling |
| 1 — deploy | ✅ Pass | ARM64 container on AgentCore Runtime |
| 2 — network | ✅ Pass | `pass_vonage_sdk` — imports + HTTPS egress |
| 3 — join + echo | ✅ **Pass** | Agent visible; distorted echo (same as C3 — acceptable) |
| 5 — Nova Sonic full | ✅ Pass | Nurse triage persona after persona `--env` redeploy |

**Production runtime:** `arn:aws:bedrock-agentcore:us-east-1:589536902306:runtime/video_agent-ErxQpSHrDP` (deploy from [`runtime/`](../../runtime/README.md)).

**Historical note:** Earlier `c6_video_agent-ALpVCJGN0S` deploy failed inbound RTP (zero audio frames). Fixed `runtime/agent.py` + Python 3.13 + `enable_rtvi=False` resolved media on redeploy.

**Validate outside AgentCore:** [C3](../c3_pipecat_transport/README.md) on Docker remains the control test if C6 regresses.

---

## Stages

```text
Stage 0  test_integration.py       Local pre-flight (tooling, Vonage creds, scaffold)
Stage 1  runtime/ agentcore deploy ARM64 container to AgentCore Runtime
Stage 2  --stage network             Imports + HTTPS + informational media/STUN probes
Stage 3  --stage echo                WebRTC join + audio echo (authoritative)
Stage 5  --stage full                Nova Sonic pipeline (nurse triage persona)
```

**TURN note:** AgentCore microVMs have no public IP — STUN-only fails by design. Vonage TURN URLs are **session-dynamic** (SDK negotiation), not static FQDNs. Stage 2 does not fail on static hostname probes; Stage 3 echo is the authoritative gate.

Whitelist domains for egress: `*.tokbox.com`, `*.opentok.com`, `*.vonage.com`.

---

## End-to-end test flow

C1 creates a Vonage session only. The agent joins when you run C6 (`--stage echo` or `--stage full`).

```text
0. leave     — clean up any previous agent (optional but recommended)
1. C1        — fresh session → VONAGE_SESSION_ID in root .env (run once)
2. Playground — Join existing session → paste Session ID from .env → Connect → Publish mic
3. C6 echo   — test_agentcore_video.py --stage echo → wait for connected: true
4. leave     — REQUIRED before switching to Nova Sonic or re-running C6
5. C6 full   — test_agentcore_video.py --stage full (optional, after leave)
6. leave     — cleanup when done
```

### Playground (validated flow)

Use **Join existing session** — not **Create new session**. Paste `VONAGE_SESSION_ID` from root `.env`. If prompted for API Key, use `VONAGE_APPLICATION_ID`.

### One agent per session

**Always run `--stage leave` before:**

- Switching from echo to full (or full to echo)
- Running C1 again
- Starting a new test on the same session

If you skip leave, both **C6 Echo Agent** and **C6 Nova Agent** can appear in the same Playground session and audio will be confusing.

```bash
AWS_PROFILE=vonage-dev uv run python test_agentcore_video.py --stage leave
```

Use repo-root `.venv` for C6 if the C1 venv is active (`../../.venv/bin/python` or `deactivate` first).

---

## Folder structure

```text
tests/c6_agentcore_video_transport/
├── agentcore_video_agent.py   C6 deploy artifact (mirror of runtime/agent.py)
├── vonage_env.py              Shared .env + private.key loading (c1–c4 pattern)
├── network_probe.py           Stage 2 probe logic
├── vonage_turn.py             Vonage media domain + optional ICE API probe
├── Dockerfile                 ARM64, Python 3.13
├── requirements.txt
├── test_integration.py        Stage 0
├── test_agentcore_video.py    Stages 2–5 invoke runner
├── .bedrock_agentcore.yaml    Legacy c6_video_agent config
└── CONTEXT.md                 C6-specific architecture notes + findings
```

**Production deploy:** use [`runtime/`](../../runtime/README.md) (`video_agent`). This folder is the **test harness** + legacy `c6_video_agent` config.

---

## Prerequisites

Root `.env`:

```bash
VONAGE_APPLICATION_ID=<your-app-id>
VONAGE_PRIVATE_KEY=private.key
VONAGE_SESSION_ID=...            # from C1 (refreshed every C1 run)
AGENTCORE_AGENT_ARN=arn:...:runtime/video_agent-ErxQpSHrDP
C6_AGENTCORE_RUNTIME_ARN=arn:...:runtime/video_agent-ErxQpSHrDP   # same ARN; test harness reads either
BEDROCK_INITIAL_USER_MESSAGE=... # nurse triage opening (must be in deploy --env)
AGENTCORE_BOOTSTRAP_PROMPT=...   # nurse triage persona (must be in deploy --env)
```

---

## Deploy (production — prefer runtime/)

See [`runtime/README.md`](../../runtime/README.md). Summary:

```bash
cd runtime
cp ../private.key ./private.key
set -a && source ../.env && set +a

export AGENTCORE_SUPPRESS_RECOMMENDATION=1
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

Use repo-root `.venv/bin/agentcore` — `runtime/` has no `pyproject.toml`, so `uv run agentcore` fails.

---

## Run tests

```bash
cd tests/c6_agentcore_video_transport

# Stage 0 — local pre-flight
uv run python test_integration.py

# Stage 2 — network probe (deployed runtime)
AWS_PROFILE=vonage-dev uv run python test_agentcore_video.py --stage network --report

# Stage 3 — echo (Playground: Join existing session + VONAGE_SESSION_ID from .env)
AWS_PROFILE=vonage-dev uv run python test_agentcore_video.py --stage echo

# Leave before switching to Nova Sonic (or you get echo + nova agents in one session)
AWS_PROFILE=vonage-dev uv run python test_agentcore_video.py --stage leave

# Stage 5 — Nova Sonic full
AWS_PROFILE=vonage-dev uv run python test_agentcore_video.py --stage full

# Cleanup
AWS_PROFILE=vonage-dev uv run python test_agentcore_video.py --stage leave
```

---

## Stage 2 decision matrix

| Decision | Cause | Action |
|---|---|---|
| `fail_imports` | Missing native deps / wrong Python | Fix Dockerfile (3.13, ARM64, vonage-video-connector) |
| `fail_https` | Egress blocked to Vonage/AWS APIs | Fix VPC/security group / NAT |
| `pass_vonage_sdk` | Imports + HTTPS OK | Proceed to Stage 3 |

Informational probes (do not block Stage 2):

- `vonage_media_informational` — media domain reachability
- `stun_only_informational` — expected fail in AgentCore

---

## Stage 3 — echo test

Joins a Vonage session with `mode: echo` and polls `status` until `connected: true`.

**Test harness requirements:**

1. **`runtimeSessionId`** — join and status polls must use the same ID (implemented in `test_agentcore_video.py`) or status hits a different microVM.
2. **Runtime env** — deploy with `VONAGE_APPLICATION_ID` + `VONAGE_PRIVATE_KEY`; copy `private.key` into build context.
3. **Playground** — publish microphone (not just camera); agent appears **after** `--stage echo` invokes join.
4. **Idle timeout** — echo pipeline uses `cancel_on_idle_timeout=False` so the agent stays alive while you test.

**Pass criteria:** `C6 Echo Agent` visible; distorted echo back within 1–2 s (same quality bar as C3).

**CloudWatch signals:**

- Join OK: `Subscriber … connected`, `C6 joined session`
- Echo OK: audio frames logged when you speak
- Persona (full): `C6 Nova Sonic persona: opening_chars=N` — must be > 0

---

## What we learned

| Runtime | Echo | Notes |
|---|---|---|
| `c6_video_agent-ALpVCJGN0S` (June 2026 early) | ❌ Fail | Signaling OK; zero inbound RTP frames |
| `video_agent-ErxQpSHrDP` (June 2026) | ✅ Pass | `runtime/agent.py`, Python 3.13, `enable_rtvi=False` |

See root [`CONTEXT.md`](../../CONTEXT.md) for architecture and Michael-ready summary.

---

## References

- [Deploy voice agents with Pipecat and AgentCore Runtime – Part 1](https://aws.amazon.com/blogs/machine-learning/deploy-voice-agents-with-pipecat-and-amazon-bedrock-agentcore-runtime-part-1/)
- [Vonage configurable TURN servers](https://tokbox.com/developer/guides/configurable-turn-servers/)
- [C3 Pipecat echo (control test)](../c3_pipecat_transport/README.md)
- [runtime/ production deploy](../../runtime/README.md)
