# C5 — AWS Bedrock AgentCore Runtime

Isolated test that deploys a **hello-world AgentCore agent** to AWS Bedrock AgentCore Runtime and invokes it, validating that your account has the necessary permissions and that the AgentCore SDK is wired up correctly.

**Platform:** Any (macOS, Linux, Windows)

---

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- AWS account with IAM permissions for Bedrock AgentCore:
  - `bedrock-agentcore:CreateAgent`
  - `bedrock-agentcore:InvokeAgent`
  - `bedrock-agentcore:DeleteAgent`
- AWS credentials set in `.env` (tests C4a passed)

---

## Setup

```bash
cd tests/c5_agentcore

uv venv
uv pip install -r requirements.txt
```

---

## Run

```bash
uv run python test_agentcore.py
```

### Expected output

```
Creating hello-world AgentCore agent …
✓ Agent created: arn:aws:bedrock-agentcore:us-east-1:123456789012:agent/abc123
Invoking agent with: "Say hello world"
✓ Agent response:
  Hello, World! I'm your AgentCore agent — ready to help.
Cleaning up agent …
✓ Agent deleted

Test C5 PASSED ✓
```

---

## Using an existing agent

If you already have an agent ARN, set it in `.env`:

```bash
AGENTCORE_AGENT_ARN=arn:aws:bedrock-agentcore:us-east-1:123456789012:agent/your-agent-id
```

The test will skip creation and use the existing agent.

---

## What it tests

| Step | Description |
|---|---|
| Agent creation | Creates a minimal hello-world agent via the AgentCore SDK |
| Agent invocation | Sends a text prompt and validates a response is returned |
| Cleanup | Deletes the test agent (unless `AGENTCORE_AGENT_ARN` was pre-set) |

---

## Troubleshooting

| Error | Fix |
|---|---|
| `AccessDeniedException` | Add `bedrock-agentcore:*` permissions to your IAM user/role |
| `ResourceNotFoundException` | Check `AGENTCORE_AGENT_ARN` value in `.env` |
| `ServiceQuotaExceededException` | Delete unused agents in the Bedrock console |
