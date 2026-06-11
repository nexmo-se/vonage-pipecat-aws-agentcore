# Answer — Orchestration API (App Runner)

Lightweight **HTTPS orchestrator** that starts the AgentCore video agent for a Vonage session. Mirrors the Voice app pattern: public endpoint receives `session_id` + `token`, invokes AgentCore Runtime.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Health check |
| POST | `/start-agent` | Invoke AgentCore `join` (default `nova_sonic`) |
| GET | `/status` | Poll AgentCore pipeline status |
| POST | `/leave` | Stop AgentCore pipeline |

### Start agent

```bash
curl -s -X POST http://localhost:8080/start-agent \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"YOUR_SESSION_ID","token":"YOUR_TOKEN"}'
```

If `token` is omitted, the server generates one from `VONAGE_APPLICATION_ID` + `private.key`.

Response includes `runtime_session_id` — required for status/leave affinity on the same AgentCore microVM.

## Run locally

```bash
cd answer
pip install -r requirements.txt

# Root .env must have:
#   AGENTCORE_RUNTIME_ARN (or C6_AGENTCORE_RUNTIME_ARN / AGENTCORE_AGENT_ARN)
#   VONAGE_APPLICATION_ID=...
#   VONAGE_PRIVATE_KEY=private.key
#   AWS_PROFILE=vonage-dev

AWS_PROFILE=vonage-dev python server.py
```

### Phase 1 smoke test (validated workflow)

See [`dev/DEV.txt`](../dev/DEV.txt) — answer section. Summary:

1. C1 → `VONAGE_SESSION_ID` in root `.env`
2. Start `server.py` (port 8080)
3. Playground → **Join existing session** → publish mic
4. `python smoke_local.py` — invokes `/start-agent`, polls `/status` until `connected: true`
5. `python smoke_local.py --leave` when done

```bash
# From repo root .venv:
cd answer
AWS_PROFILE=vonage-dev ../.venv/bin/python smoke_local.py
AWS_PROFILE=vonage-dev ../.venv/bin/python smoke_local.py --leave
```

## Deploy to App Runner

Build and push the Docker image, then create an App Runner service with:

- `AGENTCORE_RUNTIME_ARN`
- `VONAGE_APPLICATION_ID`
- `AWS_REGION=us-east-1`
- IAM role with `bedrock-agentcore:InvokeAgentRuntime`

(Vonage private key: use Secrets Manager or mount at deploy — do not bake into public images.)

## Production client flow

```text
1. React app creates Vonage session + participant token (or reuses C1 flow)
2. User clicks "Start AI"
3. POST /start-agent { session_id, token } → answer server
4. answer invokes AgentCore runtime join (nova_sonic)
5. Agent joins session as publisher; user hears nurse triage / Nova Sonic
```
