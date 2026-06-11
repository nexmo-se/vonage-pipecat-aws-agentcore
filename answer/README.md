# Answer — Orchestration API (App Runner)

Lightweight **HTTPS orchestrator** that starts the AgentCore video agent for a Vonage session. Mirrors the Voice app pattern: public endpoint receives `session_id` + `token`, invokes AgentCore Runtime.

**Status (June 2026):** Phase 1 validated — local + App Runner E2E, nurse triage in Playground.

**Production URL:** `https://x9bqavn3zv.us-east-1.awsapprunner.com`

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Health + config flags (`build`, `runtime_arn_set`, `vonage_key_set`) |
| POST | `/start-agent` | Invoke AgentCore `join` (default `nova_sonic`) |
| GET | `/status` | Poll AgentCore pipeline status |
| POST | `/leave` | Stop AgentCore pipeline |

## Architecture

```text
Playground / React client
  → POST /start-agent { session_id, token? }
  → App Runner (this service)
  → bedrock-agentcore InvokeAgentRuntime (runtimeSessionId per client)
  → runtime/agent.py on video_agent-ErxQpSHrDP
  → VonageVideoConnectorTransport + Pipecat + Nova Sonic
```

C1 creates the Vonage session only. **The agent joins when `/start-agent` is called** — not when Playground opens.

**Token flow:** `smoke_local.py` mints the Vonage publisher token locally and passes it to App Runner. If the client omits `token`, App Runner can mint one (`answer/server.py`). AgentCore (`runtime/agent.py`) can also mint a token if the join payload has none.

**Session affinity:** App Runner stores `runtimeSessionId` in process memory. `/status` and `/leave` must hit the same instance that handled `/start-agent` (single-instance POC; multi-instance App Runner would need sticky sessions or external state).

---

## App Runner smoke test (validated)

From repo root. Use **repo `.venv`** — not bare `python`.

```bash
# 1) Fresh session
cd tests/c1_vonage_video_session && uv run python test_session.py

# 2) Playground → Join existing session → VONAGE_SESSION_ID from .env → Publish mic

# 3) Start agent
ANSWER_BASE_URL=https://x9bqavn3zv.us-east-1.awsapprunner.com \
  AWS_PROFILE=vonage-dev .venv/bin/python answer/smoke_local.py

# 4) Cleanup
ANSWER_BASE_URL=https://x9bqavn3zv.us-east-1.awsapprunner.com \
  AWS_PROFILE=vonage-dev .venv/bin/python answer/smoke_local.py --leave
```

`smoke_local.py` mints the Vonage publisher token **locally** from `private.key` and passes it to App Runner. App Runner invokes AgentCore (HTTP only — no media path through App Runner).

Verify deploy health:

```bash
curl -s https://x9bqavn3zv.us-east-1.awsapprunner.com/
# {"status":"ok","build":"...","runtime_arn_set":true,"vonage_app_id_set":true,"vonage_key_set":true}
```

See also: [`dev/june11-dev.txt`](../dev/june11-dev.txt), [`dev/DEV.txt`](../dev/DEV.txt).

---

## Run locally

```bash
cd answer
../.venv/bin/pip install -r requirements.txt

# Root .env: AGENTCORE_RUNTIME_ARN, VONAGE_APPLICATION_ID, VONAGE_PRIVATE_KEY=private.key
# Listens on ANSWER_PORT (default 8080) — not root .env PORT=8000

AWS_PROFILE=vonage-dev ../.venv/bin/python server.py
```

Smoke test against localhost (separate terminal, Playground connected first):

```bash
AWS_PROFILE=vonage-dev .venv/bin/python answer/smoke_local.py
AWS_PROFILE=vonage-dev .venv/bin/python answer/smoke_local.py --leave
```

---

## Deploy to App Runner

**Prerequisite:** `AGENTCORE_RUNTIME_ARN` in root `.env` (from `runtime/` deploy output).

```bash
grep AGENTCORE_RUNTIME_ARN ../.env   # from repo root

# First deploy (creates ECR, IAM roles, App Runner service)
AWS_PROFILE=vonage-dev bash answer/deploy.sh --inline-private-key
# Expect log line: ==> AgentCore runtime ARN: arn:aws:bedrock-agentcore:...

# Updates (rebuild image + rollout + refresh IAM)
AWS_PROFILE=vonage-dev bash answer/deploy.sh --inline-private-key --update-only
```

### What deploy creates

| Resource | Name |
|---|---|
| ECR repo | `vonage-video-answer` |
| App Runner service | `vonage-video-answer` |
| Instance IAM role | `vonage-video-answer-apprunner-instance` |
| Access IAM role | `vonage-video-answer-apprunner-access` (ECR pull) |

Runtime env: `AGENTCORE_RUNTIME_ARN`, `VONAGE_APPLICATION_ID`, `VONAGE_PRIVATE_KEY_B64` (POC inline key).

### Secrets Manager (production)

User `aws-connect-cse` **cannot** `CreateSecret`. Options:

- **POC (current):** `--inline-private-key` — key as base64 env var in App Runner config
- **Production:** IAM admin creates secret, then:

```bash
VONAGE_SECRET_ARN='arn:aws:secretsmanager:us-east-1:589536902306:secret:...' \
  AWS_PROFILE=vonage-dev bash answer/deploy.sh
```

### Deploy gotchas (learned June 2026)

- App Runner env vars **cannot contain multiline PEM** — deploy uses `VONAGE_PRIVATE_KEY_B64`
- **Unique ECR image tags** required to force rollout (deploy uses `gitsha-timestamp`)
- Health must show `build` + `runtime_arn_set` — plain `{"status":"ok"}` means old image still serving
- IAM policy: `bedrock-agentcore:InvokeAgentRuntime` on `video_agent-ErxQpSHrDP`

IAM policy templates: [`apprunner-instance-policy-inline.json`](apprunner-instance-policy-inline.json), [`apprunner-instance-policy.json`](apprunner-instance-policy.json).

**Full IAM reference:** [docs/AWS_IAM.md](../docs/AWS_IAM.md) — developer vs App Runner vs AgentCore roles, SCP constraints, least privilege.

---

## Next steps (optional)

Michael's AgentCore requirement is **met** with Playground + App Runner as the demo client. These are deferred enhancements:

**Legacy Phase 2 — React client (`client/`)**

- Fork Vonage Video React JS Reference App, add Start AI → App Runner `/start-agent`, CORS on `answer/`

**Optional hardening**

- Secrets Manager for Vonage key (replace `--inline-private-key` POC)
- Customer deploy guide and blog post

See root [`README.md`](../README.md) for architecture and milestone status.
