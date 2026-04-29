# C5 - AWS Bedrock AgentCore Runtime

Minimal steps to reproduce a working C5 run with a real deployed AgentCore runtime.

## What is AWS Bedrock AgentCore?

**Amazon Bedrock AgentCore** is a managed AWS service that provides a serverless runtime environment for deploying and invoking agent logic. It allows you to:

- Package Python code as a deployable agent.
- Deploy that code to AWS without managing servers or containers.
- Invoke the deployed agent via API calls at runtime.

In this project, AgentCore serves as an **optional bootstrap initialization layer**. At session start, if `AGENTCORE_AGENT_ARN` is set in `.env`, the app invokes AgentCore to retrieve a priming message (e.g., custom system instructions, persona, or dynamic context). This message is then injected into the Pipecat pipeline to customize the agent's behavior before real-time conversation begins.

**Key benefit:** Decouples static agent logic (deployment-time) from real-time orchestration (runtime). You deploy your agent logic to a managed AWS runtime, and the FastAPI app simply calls it to bootstrap each session.

## Bedrock vs AgentCore (Why Both?)

These are different layers of the stack:

- **Amazon Bedrock** is the model inference service (for example Nova Lite / Nova Sonic).
- **Amazon Bedrock AgentCore** is the managed runtime for your deployable agent application logic.

In this repository:

1. C4b proves Bedrock model inference for live speech/text responses.
2. C5 proves AgentCore runtime deployment and invocation.
3. In the full app, AgentCore can optionally provide bootstrap instructions/persona, while Bedrock powers live conversational inference.

Short version: **Bedrock answers; AgentCore runs deployable agent app logic.**

## Purpose

This C5 folder validates end-to-end AgentCore runtime invocation.

- `hello_agent.py`: minimal runtime app used for deploy/configure (`agentcore configure -e hello_agent.py ...`)
- `test_agentcore.py`: validation script that invokes the deployed runtime and verifies a response

Keep both files in this folder so C5 remains self-contained (deploy artifact + test).

## When Do You Need AgentCore?

| Scenario                                                           | Use AgentCore? | Why                                                                                  |
| ------------------------------------------------------------------ | -------------- | ------------------------------------------------------------------------------------ |
| Simple echo/reflective agent with no custom logic                  | No             | Nova Sonic defaults are sufficient; skip for minimal latency.                        |
| Custom persona, system instructions, or initialization             | Yes            | AgentCore bootstrap injects these at session start without adding real-time latency. |
| Agent logic requires tools, memory retrieval, or stateful behavior | Yes            | AgentCore's managed runtime safely hosts complex agent patterns.                     |
| Agent logic must be versioned and auditable                        | Yes            | AgentCore deployments are immutable and AWS-managed with full audit trails.          |
| Quick MVP or one-off demo                                          | No             | Run raw Pipecat + Nova Sonic; skip AgentCore overhead.                               |

If `AGENTCORE_AGENT_ARN` is not set in `.env`, the agent runs without bootstrap and uses Nova Sonic defaults. If it is set, AgentCore's bootstrap message customizes behavior before real-time interaction.

## Do I Need Both AWS Files?

Short answer: not always.

- `~/.aws/credentials` is required when using access keys (`aws_access_key_id` / `aws_secret_access_key`).
- `~/.aws/config` is required only if your profile depends on config-only settings (for example `region`, `role_arn`, `source_profile`, or SSO settings).

For this C5 flow, a working profile like `AWS_PROFILE=vonage-dev` is what matters. That profile may use one file or both.

## Prerequisites

- Python 3.11+
- `uv`
- `aws` CLI
- `agentcore` CLI (from `bedrock-agentcore-starter-toolkit`)
- Working AWS profile with Bedrock AgentCore access
- Permissions to deploy runtime resources (`iam:CreateRole`, `iam:PassRole`, S3 write, AgentCore permissions)

## Required CLIs

You need both AWS CLI and AgentCore CLI.

- AWS CLI: used for profile/credential resolution and AWS API auth
- AgentCore CLI: used for `configure`, `deploy`, and `status`

Install and verify:

```bash
command -v aws >/dev/null || brew install awscli

cd tests/c5_agentcore
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install bedrock-agentcore-starter-toolkit
# or with uv: uv venv && uv pip install -r requirements.txt && uv pip install bedrock-agentcore-starter-toolkit

aws --version
agentcore --help
```

## AWS Profile Setup (Recommended)

Create and verify a profile before configure/deploy/test:

```bash
aws configure --profile vonage-dev
# enter AWS Access Key ID, Secret Access Key, region: us-east-1, output: json

aws sts get-caller-identity --profile vonage-dev
export AWS_PROFILE=vonage-dev
```

If this profile command fails, fix AWS credentials first before running C5 steps.

## IAM Policies and Permissions Needed

For this exact C5 flow (auto-create execution role and auto-create S3 bucket), these were required:

- Managed policies attached to the deploying identity:
  - `BedrockAgentCoreFullAccess`
  - `AmazonBedrockFullAccess`
- IAM permissions (directly or via policy) to create and use runtime role:
  - `iam:CreateRole`
  - `iam:AttachRolePolicy`
  - `iam:PutRolePolicy`
  - `iam:GetRole`
  - `iam:PassRole`
- S3 permissions for deployment artifacts:
  - `s3:CreateBucket` (if auto-create)
  - `s3:PutObject`
  - `s3:GetObject`
  - `s3:ListBucket`

If your organization does not allow role creation, ask an admin to pre-create the execution role and provide its IAM role ARN.

## 1. Setup

```bash
cd tests/c5_agentcore

command -v aws >/dev/null || brew install awscli

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install bedrock-agentcore-starter-toolkit
# or with uv: uv venv && uv pip install -r requirements.txt && uv pip install bedrock-agentcore-starter-toolkit
```

## 2. Configure Runtime Deployment

```bash
agentcore configure -e hello_agent.py -r us-east-1
# or with uv: uv run agentcore configure -e hello_agent.py -r us-east-1
```

Choose:

- Deployment type: `Direct Code Deploy`
- Runtime: `PYTHON_3_11`
- Execution role: `Auto-create` (or provide an IAM role ARN)
- S3 bucket: `Auto-create`
- Authorization: `IAM default`

Important:

- Execution role must be an IAM **role** ARN, not an IAM user ARN.

## 3. Deploy

```bash
AWS_PROFILE=vonage-dev agentcore deploy
# or with uv: AWS_PROFILE=vonage-dev uv run agentcore deploy
```

On success, copy the runtime ARN, for example:

```text
arn:aws:bedrock-agentcore:us-east-1:<your-account-id>:runtime/hello_agent-...
```

## 4. Set Runtime ARN

In repo root `.env`, set:

```bash
AGENTCORE_AGENT_ARN=arn:aws:bedrock-agentcore:us-east-1:<your-account-id>:runtime/hello_agent-...
```

## 5. Run C5 Test

```bash
AWS_PROFILE=vonage-dev uv run python test_agentcore.py
# or without uv: source .venv/bin/activate && AWS_PROFILE=vonage-dev python3 test_agentcore.py
```

If you are running from the repo root, use:

```bash
cd tests/c5_agentcore
AWS_PROFILE=vonage-dev uv run python test_agentcore.py
```

Expected success lines:

```text
✓ Using existing runtime: arn:aws:bedrock-agentcore:us-east-1:<your-account-id>:runtime/hello_agent-<runtime-id>
Invoking agent with: "Say hello world"
✓ Agent response:
  Hello, Say hello world! AgentCore is working.
Test C5 PASSED ✓
```

## Common Failure

- `AccessDenied` on `iam:CreateRole`: your AWS identity cannot create roles; ask admin to grant IAM role-creation permissions or pre-create the execution role.
- `ResourceNotFoundException` with `...runtime/<your-runtime-id>`: a placeholder runtime ARN is being used. Check that `AGENTCORE_AGENT_ARN` in `.env` is set to your deployed runtime ARN.
