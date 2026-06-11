# Runtime — AgentCore Video Agent (Production)

**Bedrock AgentCore Runtime** hosts the full live agent: `VonageVideoConnectorTransport` + Pipecat + **amazon.nova-2-sonic-v1:0**.

Validated locally via C3 (transport) and C4b (Nova Sonic). This is the deploy artifact Michael's requirement targets — **not** the local `app/` FastAPI server.

## Architecture role

```text
Browser (Playground / React app)
    ↓ WebRTC
Vonage Video Session
    ↑ join {session_id, token} via AgentCore invoke
AgentCore Runtime (this folder — ARM64 container)
    agent.py → Nova Sonic pipeline
```

Orchestration (session + invoke) lives in [`../answer/`](../answer/).

## Prerequisites

- Docker Desktop (for `--local-build` on macOS)
- `agentcore` CLI in repo-root `.venv` (`uv pip install bedrock-agentcore-starter-toolkit` from repo root)
- Root `.env`: `VONAGE_APPLICATION_ID`, `AWS_PROFILE`, `BEDROCK_MODEL_ID`, persona vars
- `private.key` in repo root

## Deploy

```bash
cd runtime

# 1) Copy Vonage private key into build context
cp ../private.key ./private.key

# 2) Load root .env so persona vars expand in --env flags
#    Persona lines MUST be double-quoted in .env (zsh breaks on unquoted spaces/?)
set -a && source ../.env && set +a
echo "opening msg chars: ${#BEDROCK_INITIAL_USER_MESSAGE} bootstrap chars: ${#AGENTCORE_BOOTSTRAP_PROMPT}"
# expect opening > 100, bootstrap > 50 — if 0, fix .env quoting and re-source
export AGENTCORE_SUPPRESS_RECOMMENDATION=1
# 2a) One-time configure (creates .bedrock_agentcore.yaml — gitignored, local only)
#     -n names the agent; -a is only valid on deploy, not configure
AWS_PROFILE=vonage-dev ../.venv/bin/agentcore configure --create \
  -e agent.py \
  -n video_agent \
  -r us-east-1 \
  -dt container \
  -ni \
  -er arn:aws:iam::589536902306:role/AmazonBedrockAgentCoreSDKRuntime-us-east-1-c07010a437

# 2a-ii) Generate Dockerfile in .bedrock_agentcore/video_agent/
#        (--create skips this step — required before deploy)
AWS_PROFILE=vonage-dev ../.venv/bin/agentcore configure \
  -e agent.py \
  -n video_agent \
  -r us-east-1 \
  -dt container \
  -ni \
  -er arn:aws:iam::589536902306:role/AmazonBedrockAgentCoreSDKRuntime-us-east-1-c07010a437

# 2b) Build + deploy (ARM64 container via Docker Desktop)
AWS_PROFILE=vonage-dev ../.venv/bin/agentcore deploy \
  -a video_agent \
  --local-build \
  --auto-update-on-conflict \
  --env "VONAGE_APPLICATION_ID=${VONAGE_APPLICATION_ID}" \
  --env "VONAGE_PRIVATE_KEY=private.key" \
  --env "BEDROCK_MODEL_ID=${BEDROCK_MODEL_ID}" \
  --env "BEDROCK_INITIAL_USER_MESSAGE=${BEDROCK_INITIAL_USER_MESSAGE}" \
  --env "AGENTCORE_BOOTSTRAP_PROMPT=${AGENTCORE_BOOTSTRAP_PROMPT}"

# 3) Set runtime ARN in root .env from deploy output
# AGENTCORE_AGENT_ARN=arn:aws:bedrock-agentcore:us-east-1:...:runtime/video_agent-...
# C6_AGENTCORE_RUNTIME_ARN=<same ARN>
```

Skip step 2a if `runtime/.bedrock_agentcore.yaml` already exists. If deploy fails with
`Dockerfile not found at .../.bedrock_agentcore/video_agent/Dockerfile`, run step 2a-ii only.

**Note:** `logs:PutDeliverySource` observability warnings during deploy are non-fatal — memory and deploy continue.

## Persona / nurse triage

Root `.env` is **not** read inside the container. Persona must be passed at deploy:

| Variable | Role in `agent.py` |
|---|---|
| `AGENTCORE_BOOTSTRAP_PROMPT` | Nova Sonic `system_instruction` (behavior / persona) |
| `BEDROCK_INITIAL_USER_MESSAGE` | Required opening line the agent speaks first |

After `--stage full`, check CloudWatch for `opening_chars=N`. If `N=0`, redeploy with `set -a && source ../.env` before deploy.

## Test after deploy

```text
0. leave (optional cleanup)
1. C1  → VONAGE_SESSION_ID in .env (once per test)
2. Playground → Join existing session → Session ID from .env → Publish mic
3. C6  → --stage echo OR --stage full (wait for connected: true)
4. leave → REQUIRED before switching echo ↔ full or re-running C1
```

```bash
cd tests/c1_vonage_video_session && uv run python test_session.py

cd tests/c6_agentcore_video_transport
AWS_PROFILE=vonage-dev ../../.venv/bin/python test_agentcore_video.py --stage leave
AWS_PROFILE=vonage-dev ../../.venv/bin/python test_agentcore_video.py --stage echo
AWS_PROFILE=vonage-dev ../../.venv/bin/python test_agentcore_video.py --stage leave   # before full
AWS_PROFILE=vonage-dev ../../.venv/bin/python test_agentcore_video.py --stage full
AWS_PROFILE=vonage-dev ../../.venv/bin/python test_agentcore_video.py --stage leave
```

## Invoke actions (HTTP payload)

| Action | Payload |
|---|---|
| Join Nova Sonic | `{"action":"join","session_id":"...","token":"...","mode":"nova_sonic"}` |
| Join echo (debug) | `{"action":"join","session_id":"...","token":"...","mode":"echo"}` |
| Status | `{"action":"status"}` |
| Leave | `{"action":"leave"}` |

**Important:** Use the same `runtimeSessionId` across join/status/leave (handled by `answer/server.py` and `test_agentcore_video.py`).

Or use orchestration API:

```bash
cd answer && pip install -r requirements.txt
AWS_PROFILE=vonage-dev python server.py
# POST /start-agent with session_id from C1
```

## Troubleshooting

### ECR access denied on CreateAgentRuntime

If deploy builds/pushes the image but fails with:

```text
Access denied while validating ECR URI ... bedrock-agentcore-video_agent:...
The execution role requires permissions for ecr:GetAuthorizationToken, ecr:BatchGetImage, and ecr:GetDownloadUrlForLayer
```

The runtime execution role is scoped per ECR repo. A new agent name creates a **new** repo (`bedrock-agentcore-<agent_name>`). The shared role
`AmazonBedrockAgentCoreSDKRuntime-us-east-1-c07010a437` was originally limited to `bedrock-agentcore-c6_video_agent`.

**Fix (IAM admin):** add the new repo ARN to the role’s ECR pull policy, e.g.:

```json
"Resource": [
  "arn:aws:ecr:us-east-1:589536902306:repository/bedrock-agentcore-c6_video_agent",
  "arn:aws:ecr:us-east-1:589536902306:repository/bedrock-agentcore-video_agent"
]
```

**Workaround (no IAM change):** redeploy to the existing C6 runtime instead — copy `agent.py` → `tests/c6_agentcore_video_transport/agentcore_video_agent.py` and run `agentcore deploy -a c6_video_agent ...` from that folder.

## C6 validation note

C6 Stage 3 echo **passes** on `video_agent-ErxQpSHrDP` (June 2026): agent joins Playground, distorted echo returns. This matches the C3 quality bar. Run `--stage full` after persona redeploy for Nova Sonic nurse triage.
