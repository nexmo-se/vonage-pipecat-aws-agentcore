# AWS Credentials, IAM, and Policies

What AWS identity, permissions, and org rules this project needs — by **who** uses them and **when**.

**Region:** `us-east-1` (validated POC account `589536902306`).

---

## Credential setup (developer / CI)

Use an AWS CLI **profile** — not long-lived keys in `.env` for day-to-day work.

```bash
aws configure --profile vonage-dev
# Access Key ID, Secret Access Key, region us-east-1, output json

aws sts get-caller-identity --profile vonage-dev
export AWS_PROFILE=vonage-dev
export AWS_REGION=us-east-1
```

Root [`.env.example`](../.env.example):

| Variable | Purpose |
| --- | --- |
| `AWS_PROFILE` | CLI profile name (preferred) |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | Bedrock + AgentCore region |
| `BEDROCK_MODEL_ID` | `amazon.nova-2-sonic-v1:0` (production agent) |
| `AGENTCORE_RUNTIME_ARN` | Runtime ARN after `runtime/` deploy — required for `answer/deploy.sh` |

Legacy aliases accepted by code (prefer canonical name): `C6_AGENTCORE_RUNTIME_ARN`, `AGENTCORE_AGENT_ARN`.

**Docker tests (C2–C4b, `app/`):** mount `~/.aws` into the container (`-v ~/.aws:/root/.aws`) and pass `-e AWS_PROFILE=vonage-dev`.

**Production services (AgentCore microVM, App Runner):** use **IAM roles + instance credentials (IMDS)** — no static AWS keys in containers. Vonage private key is env/Secrets Manager on App Runner only (see [answer/README.md](../answer/README.md)).

---

## Bedrock model access (console — not IAM)

Enable model access in the [Bedrock console](https://console.aws.amazon.com/bedrock/home#/modelaccess) for your region:

| Model | ID | Used in |
| --- | --- | --- |
| Amazon Nova Sonic | `amazon.nova-2-sonic-v1:0` | C4b, C6 full, `runtime/`, `app/` |
| Amazon Nova Lite | `amazon.nova-lite-v1:0` | C4a credential preflight |

Without model access, `InvokeModel` fails even if IAM allows it.

---

## Four AWS identities in this architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│ 1. Developer / deployer (your AWS_PROFILE)                       │
│    Tests C1–C6, agentcore deploy, answer/deploy.sh, smoke invoke │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐
│ 2. AgentCore     │ │ 3. App Runner    │ │ 4. App Runner        │
│ execution role   │ │ instance role    │ │ access role          │
│ (runtime microVM)│ │ (answer/ tasks)  │ │ (ECR pull at deploy) │
│ Bedrock + ECR    │ │ InvokeAgentRuntime│ │ AWS managed policy   │
└──────────────────┘ └──────────────────┘ └──────────────────────┘
```

---

## 1. Developer / deployer identity

Your user or role when running tests, `agentcore deploy`, and `answer/deploy.sh`.

### By test / task

| Task | AWS APIs / permissions | Notes |
| --- | --- | --- |
| **C4a** | `bedrock:GetFoundationModel`, `bedrock:InvokeModel` (Nova Lite) | Credential smoke test |
| **C4b / local `app/`** | `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` (Nova Sonic) | Via `bedrock-runtime` |
| **C5** | AgentCore deploy + `bedrock-agentcore:InvokeAgentRuntime` | Hello-world runtime |
| **C6 / smoke / local `answer/`** | `bedrock-agentcore:InvokeAgentRuntime` on your runtime ARN | Same API App Runner uses |
| **`runtime/` deploy** | AgentCore toolkit: ECR push, `iam:PassRole`, runtime create/update, S3 artifacts, CloudWatch | See managed policies below |
| **`answer/deploy.sh`** | ECR create/push, IAM role create/update, App Runner create/update, optional Secrets Manager | See deploy section |

### Managed policies (POC — broad)

What worked for C5/C6 deploy in this account:

- `BedrockAgentCoreFullAccess`
- `AmazonBedrockFullAccess` (or narrower Bedrock invoke + model read)

### IAM actions for `agentcore deploy` (C5, C6, `runtime/`)

If managed policies are not allowed, an admin needs at minimum:

| Area | Actions |
| --- | --- |
| **AgentCore** | `bedrock-agentcore:*` (or create/update runtime + invoke for your runtime ARN) |
| **Pass role** | `iam:PassRole` on the AgentCore **execution role** |
| **Execution role lifecycle** | `iam:CreateRole`, `iam:GetRole`, `iam:AttachRolePolicy`, `iam:PutRolePolicy` (if auto-create) |
| **ECR** | `ecr:*` on `bedrock-agentcore-*` repos (push from local build) |
| **S3** | `s3:CreateBucket`, `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` (deploy artifacts) |
| **Logs** | `logs:*` on AgentCore log groups (optional; deploy warnings if missing) |

**Execution role must be an IAM role ARN**, not a user ARN (`-er` flag on `agentcore configure`).

Validated execution role (POC):  
`arn:aws:iam::589536902306:role/AmazonBedrockAgentCoreSDKRuntime-us-east-1-c07010a437`

### IAM actions for `answer/deploy.sh`

| Area | Actions |
| --- | --- |
| **STS** | `sts:GetCallerIdentity` |
| **ECR** | `ecr:CreateRepository`, `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:PutImage`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload` |
| **IAM** | `iam:CreateRole`, `iam:GetRole`, `iam:AttachRolePolicy`, `iam:PutRolePolicy` on App Runner roles |
| **App Runner** | `apprunner:CreateService`, `apprunner:UpdateService`, `apprunner:ListServices`, `apprunner:DescribeService` |
| **Secrets Manager** (production path) | `secretsmanager:CreateSecret`, `secretsmanager:DescribeSecret` — **often blocked** for CSE users; use `--inline-private-key` POC |

### Invoke-only (no deploy)

Minimum for C6 tests and `answer/smoke_local.py` against an existing runtime:

```json
{
  "Effect": "Allow",
  "Action": "bedrock-agentcore:InvokeAgentRuntime",
  "Resource": [
    "arn:aws:bedrock-agentcore:us-east-1:<account-id>:runtime/video_agent-*",
    "arn:aws:bedrock-agentcore:us-east-1:<account-id>:runtime/video_agent-*/*"
  ]
}
```

Replace `video_agent-*` with your runtime name/ID.

---

## 2. AgentCore execution role (runtime microVM)

Assumed by the AgentCore Runtime when your container runs. Configured via `agentcore configure -er <role-arn>`.

**Inside the container:** Pipecat calls **Nova Sonic** through Bedrock APIs using this role’s credentials (not the developer profile).

### Required permissions

| Area | Actions | Notes |
| --- | --- | --- |
| **Bedrock** | `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` | Nova Sonic in `runtime/agent.py` |
| **ECR pull** | `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer` | Per repo `bedrock-agentcore-<agent_name>` |

Example ECR supplement (when a **new agent name** creates a new repo):  
[`tests/c6_agentcore_video_transport/c6-ecr-pull-iam-policy.json`](../tests/c6_agentcore_video_transport/c6-ecr-pull-iam-policy.json)

Add the new repository ARN alongside existing ones:

```json
"Resource": [
  "arn:aws:ecr:us-east-1:<account-id>:repository/bedrock-agentcore-c6_video_agent",
  "arn:aws:ecr:us-east-1:<account-id>:repository/bedrock-agentcore-video_agent"
]
```

**Common failure:** deploy pushes image but `CreateAgentRuntime` fails with ECR access denied → execution role missing pull on the new repo ([`runtime/README.md`](../runtime/README.md#ecr-access-denied-on-createagentruntime)).

### Network egress (not IAM)

AgentCore microVM must reach Vonage media (WebRTC/TURN): `*.tokbox.com`, `*.opentok.com`, `*.vonage.com`. No public IP — Vonage SDK supplies session-dynamic TURN.

---

## 3. App Runner instance role (`answer/` at runtime)

**Role name (POC):** `vonage-video-answer-apprunner-instance`  
**Assumed by:** `tasks.apprunner.amazonaws.com`

Only needs to **invoke AgentCore** (and optionally read Vonage secret).

### Inline key POC (current)

[`answer/apprunner-instance-policy-inline.json`](../answer/apprunner-instance-policy-inline.json):

```json
{
  "Effect": "Allow",
  "Action": "bedrock-agentcore:InvokeAgentRuntime",
  "Resource": [
    "arn:aws:bedrock-agentcore:us-east-1:<account-id>:runtime/video_agent-<id>",
    "arn:aws:bedrock-agentcore:us-east-1:<account-id>:runtime/video_agent-<id>/*"
  ]
}
```

Vonage private key is passed as `VONAGE_PRIVATE_KEY_B64` env var — **no Secrets Manager** on instance role.

### Production (Secrets Manager)

[`answer/apprunner-instance-policy.json`](../answer/apprunner-instance-policy.json) adds:

```json
{
  "Effect": "Allow",
  "Action": [
    "secretsmanager:GetSecretValue",
    "secretsmanager:DescribeSecret"
  ],
  "Resource": "arn:aws:secretsmanager:us-east-1:<account-id>:secret:vonage/video/answer-private-key-*"
}
```

`answer/deploy.sh` applies the chosen policy with `iam put-role-policy`.

---

## 4. App Runner access role (ECR pull for deployments)

**Role name (POC):** `vonage-video-answer-apprunner-access`  
**Assumed by:** `build.apprunner.amazonaws.com`

AWS managed policy attached by deploy script:

- `arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess`

Allows App Runner to pull `vonage-video-answer` images from ECR. **Does not** invoke AgentCore or Bedrock.

---

## Organization SCP / guardrails

Observed on POC account `589536902306` — verify in your org before choosing services:

| Action / service | Status | Impact |
| --- | --- | --- |
| `lambda:InvokeFunctionUrl` | Blocked | Use **App Runner** for public HTTPS orchestrator |
| `apigateway:*` | Blocked | No API Gateway front door |
| `kinesisvideo:CreateSignalingChannel` | Blocked | Not used — Vonage SDK TURN instead |
| `secretsmanager:CreateSecret` | Blocked for CSE deploy user | Use IAM admin + `VONAGE_SECRET_ARN`, or `--inline-private-key` POC |
| **App Runner** | Allowed | `answer/` deploy path |
| **AgentCore Runtime** | Allowed | `runtime/` deploy path |
| **Vonage media egress** | Required | WebRTC/TURN from AgentCore microVM |

---

## Policy templates in repo

| File | Used by |
| --- | --- |
| [`answer/apprunner-instance-policy-inline.json`](../answer/apprunner-instance-policy-inline.json) | App Runner instance role — InvokeAgentRuntime only (POC) |
| [`answer/apprunner-instance-policy.json`](../answer/apprunner-instance-policy.json) | App Runner instance role — Invoke + Secrets Manager |
| [`tests/c6_agentcore_video_transport/c6-ecr-pull-iam-policy.json`](../tests/c6_agentcore_video_transport/c6-ecr-pull-iam-policy.json) | AgentCore execution role — ECR pull for C6 repo |

Replace account ID `589536902306` and runtime suffix with your values before applying.

---

## Quick verification

```bash
# Who am I?
aws sts get-caller-identity --profile vonage-dev

# Bedrock model access (C4a)
aws bedrock get-foundation-model \
  --model-identifier amazon.nova-2-sonic-v1:0 \
  --region us-east-1 --profile vonage-dev

# Can I invoke the production runtime? (C6 / smoke — after deploy)
aws bedrock-agentcore invoke-agent-runtime help

# App Runner health (after answer/ deploy)
curl -s https://<your-apprunner-url>/
# expect: runtime_arn_set, vonage_key_set, build
```

---

## Least privilege (customer production)

| Identity | Tighten |
| --- | --- |
| Developer | Scope `InvokeAgentRuntime` to one runtime ARN; drop `BedrockAgentCoreFullAccess` after deploy |
| AgentCore execution role | Bedrock invoke on Nova Sonic model ARN only; ECR pull on one repo |
| App Runner instance | `InvokeAgentRuntime` on one runtime ARN; Secrets Manager on one secret |
| App Runner access | Default AWS managed ECR policy is usually sufficient |

See also: [AgentCore security](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/security.html), [IAM best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html).
