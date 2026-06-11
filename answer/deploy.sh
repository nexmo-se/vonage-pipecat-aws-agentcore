#!/usr/bin/env bash
# Deploy answer/ orchestrator to AWS App Runner (ECR + service).
#
# Usage (from repo root):
#   AWS_PROFILE=vonage-dev bash answer/deploy.sh
#   AWS_PROFILE=vonage-dev bash answer/deploy.sh --update-only
#
# CSE users often lack secretsmanager:CreateSecret. Options:
#   A) IAM admin creates secret → re-run with VONAGE_SECRET_ARN=arn:...
#   B) POC inline key (no Secrets Manager) → bash answer/deploy.sh --inline-private-key

set -euo pipefail

UPDATE_ONLY=false
INLINE_PRIVATE_KEY=false
for arg in "$@"; do
  case "${arg}" in
    --update-only) UPDATE_ONLY=true ;;
    --inline-private-key) INLINE_PRIVATE_KEY=true ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${SCRIPT_DIR}"

if [[ -f "${REPO_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.env"
  set +a
fi

AWS_PROFILE="${AWS_PROFILE:-vonage-dev}"
export AWS_PROFILE
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID="589536902306"
ECR_REPO="vonage-video-answer"
SERVICE_NAME="vonage-video-answer"
SECRET_NAME="vonage/video/answer-private-key"
INSTANCE_ROLE="vonage-video-answer-apprunner-instance"
ACCESS_ROLE="vonage-video-answer-apprunner-access"
DEFAULT_RUNTIME_ARN="arn:aws:bedrock-agentcore:${REGION}:${ACCOUNT_ID}:runtime/video_agent-ErxQpSHrDP"
RUNTIME_ARN="${AGENTCORE_RUNTIME_ARN:-${C6_AGENTCORE_RUNTIME_ARN:-${AGENTCORE_AGENT_ARN:-${DEFAULT_RUNTIME_ARN}}}}"
echo "==> AgentCore runtime ARN: ${RUNTIME_ARN}"

VONAGE_APPLICATION_ID="${VONAGE_APPLICATION_ID:-}"
if [[ -z "${VONAGE_APPLICATION_ID}" ]]; then
  echo "ERROR: VONAGE_APPLICATION_ID not set — add to root .env"
  exit 1
fi

if [[ ! -f "${REPO_ROOT}/private.key" ]]; then
  echo "ERROR: ${REPO_ROOT}/private.key not found"
  exit 1
fi

echo "==> Account / region: $(aws sts get-caller-identity --query Account --output text) / ${REGION}"

if ! aws ecr describe-repositories --repository-names "${ECR_REPO}" --region "${REGION}" >/dev/null 2>&1; then
  echo "==> Creating ECR repository ${ECR_REPO}"
  aws ecr create-repository \
    --repository-name "${ECR_REPO}" \
    --image-scanning-configuration scanOnPush=true \
    --region "${REGION}" >/dev/null
else
  echo "==> ECR repository ${ECR_REPO} exists"
fi

ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"
GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo nogit)"
IMAGE_TAG="${GIT_SHA}-$(date -u +%Y%m%d%H%M%S)"
IMAGE_URI="${ECR_URI}:${IMAGE_TAG}"

echo "==> Docker login to ECR"
aws ecr get-login-password --region "${REGION}" | \
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "==> Building ${IMAGE_URI}"
docker build --platform linux/amd64 -t "${IMAGE_URI}" -t "${ECR_URI}:latest" .

echo "==> Pushing image"
docker push "${IMAGE_URI}"
docker push "${ECR_URI}:latest"

_secret_admin_instructions() {
  cat <<EOF

ERROR: Cannot create Secrets Manager secret (AccessDenied on aws-connect-cse).

Option A — ask IAM admin to create the secret once:

  aws secretsmanager create-secret \\
    --name ${SECRET_NAME} \\
    --secret-string file://private.key \\
    --region ${REGION}

Then re-run:
  VONAGE_SECRET_ARN='arn:aws:secretsmanager:...' AWS_PROFILE=${AWS_PROFILE} bash answer/deploy.sh

Option B — POC without Secrets Manager (key as base64 env var in App Runner config):

  AWS_PROFILE=${AWS_PROFILE} bash answer/deploy.sh --inline-private-key

  Not for production — migrate to Secrets Manager before customer deploy.
EOF
}

_resolve_secret_arn() {
  if [[ -n "${VONAGE_SECRET_ARN:-}" ]]; then
    echo "==> Using VONAGE_SECRET_ARN from environment"
    SECRET_ARN="${VONAGE_SECRET_ARN}"
    return 0
  fi

  if aws secretsmanager describe-secret --secret-id "${SECRET_NAME}" --region "${REGION}" >/dev/null 2>&1; then
    SECRET_ARN="$(aws secretsmanager describe-secret --secret-id "${SECRET_NAME}" --region "${REGION}" --query ARN --output text)"
    echo "==> Secret ${SECRET_NAME} exists — using ${SECRET_ARN}"
    aws secretsmanager put-secret-value \
      --secret-id "${SECRET_NAME}" \
      --secret-string "file://${REPO_ROOT}/private.key" \
      --region "${REGION}" >/dev/null 2>&1 \
      && echo "==> Updated secret value" \
      || echo "==> Skipping secret update (no PutSecretValue permission)"
    return 0
  fi

  echo "==> Creating secret ${SECRET_NAME}"
  if ! aws secretsmanager create-secret \
    --name "${SECRET_NAME}" \
    --secret-string "file://${REPO_ROOT}/private.key" \
    --region "${REGION}" >/dev/null 2>&1; then
    _secret_admin_instructions
    exit 1
  fi
  SECRET_ARN="$(aws secretsmanager describe-secret --secret-id "${SECRET_NAME}" --region "${REGION}" --query ARN --output text)"
}

if [[ "${UPDATE_ONLY}" == "false" ]]; then
  if [[ "${INLINE_PRIVATE_KEY}" == "true" ]]; then
    echo "==> --inline-private-key: skipping Secrets Manager (POC only)"
  else
    _resolve_secret_arn
  fi
fi

# Always refresh IAM (idempotent) — --update-only previously skipped this
if ! aws iam get-role --role-name "${ACCESS_ROLE}" >/dev/null 2>&1; then
  echo "==> Creating access role ${ACCESS_ROLE}"
  aws iam create-role \
    --role-name "${ACCESS_ROLE}" \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "build.apprunner.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }]
    }' >/dev/null
  aws iam attach-role-policy \
    --role-name "${ACCESS_ROLE}" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
fi
ACCESS_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ACCESS_ROLE}"

POLICY_FILE="apprunner-instance-policy.json"
if [[ "${INLINE_PRIVATE_KEY}" == "true" ]]; then
  POLICY_FILE="apprunner-instance-policy-inline.json"
fi

if ! aws iam get-role --role-name "${INSTANCE_ROLE}" >/dev/null 2>&1; then
  echo "==> Creating instance role ${INSTANCE_ROLE}"
  aws iam create-role \
    --role-name "${INSTANCE_ROLE}" \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "tasks.apprunner.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }]
    }' >/dev/null
fi
echo "==> Updating instance role policy (${POLICY_FILE})"
aws iam put-role-policy \
  --role-name "${INSTANCE_ROLE}" \
  --policy-name "VonageVideoAnswerAppRunner" \
  --policy-document "file://${SCRIPT_DIR}/${POLICY_FILE}"
INSTANCE_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${INSTANCE_ROLE}"

if [[ "${UPDATE_ONLY}" == "false" ]]; then
  echo "==> Waiting for IAM propagation (10s)"
  sleep 10
else
  echo "==> Waiting for IAM propagation (5s)"
  sleep 5
fi

if [[ "${UPDATE_ONLY}" == "true" ]]; then
  if [[ "${INLINE_PRIVATE_KEY}" == "true" ]]; then
    : # inline key in SOURCE_CONFIG below
  elif [[ -n "${VONAGE_SECRET_ARN:-}" ]]; then
    SECRET_ARN="${VONAGE_SECRET_ARN}"
  else
    SECRET_ARN="$(aws secretsmanager describe-secret --secret-id "${SECRET_NAME}" --region "${REGION}" --query ARN --output text 2>/dev/null || true)"
  fi
fi

echo "==> Building App Runner source configuration"
SOURCE_CONFIG="$(
  INLINE_PRIVATE_KEY="${INLINE_PRIVATE_KEY}" \
  SECRET_ARN="${SECRET_ARN:-}" \
  IMAGE_URI="${IMAGE_URI}" \
  ACCESS_ROLE_ARN="${ACCESS_ROLE_ARN}" \
  REGION="${REGION}" \
  RUNTIME_ARN="${RUNTIME_ARN}" \
  VONAGE_APPLICATION_ID="${VONAGE_APPLICATION_ID}" \
  PRIVATE_KEY_FILE="${REPO_ROOT}/private.key" \
  python3 <<'PY'
import json, os, base64
from pathlib import Path

inline = os.environ.get("INLINE_PRIVATE_KEY") == "true"
image_uri = os.environ["IMAGE_URI"]
access_role = os.environ["ACCESS_ROLE_ARN"]
region = os.environ["REGION"]
runtime_arn = os.environ["RUNTIME_ARN"]
app_id = os.environ["VONAGE_APPLICATION_ID"]

env_vars = {
    "AWS_REGION": region,
    "AGENTCORE_RUNTIME_ARN": runtime_arn,
    "VONAGE_APPLICATION_ID": app_id,
    "BUILD_VERSION": image_uri.rsplit(":", 1)[-1],
}
secrets = {}

if inline:
    pem = Path(os.environ["PRIVATE_KEY_FILE"]).read_text(encoding="utf-8")
    # App Runner env vars must be single-line (no raw PEM newlines)
    env_vars["VONAGE_PRIVATE_KEY_B64"] = base64.b64encode(pem.encode("utf-8")).decode("ascii")
else:
    secrets["VONAGE_PRIVATE_KEY_PEM"] = os.environ["SECRET_ARN"]

image_cfg = {
    "Port": "8080",
    "RuntimeEnvironmentVariables": env_vars,
}
if secrets:
    image_cfg["RuntimeEnvironmentSecrets"] = secrets

print(json.dumps({
    "ImageRepository": {
        "ImageIdentifier": image_uri,
        "ImageConfiguration": image_cfg,
        "ImageRepositoryType": "ECR",
    },
    "AuthenticationConfiguration": {"AccessRoleArn": access_role},
    "AutoDeploymentsEnabled": False,
}))
PY
)"

INSTANCE_CONFIG=$(cat <<EOF
{
  "Cpu": "1024",
  "Memory": "2048",
  "InstanceRoleArn": "${INSTANCE_ROLE_ARN}"
}
EOF
)

if aws apprunner list-services --region "${REGION}" --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn | [0]" --output text | grep -q "arn:aws:apprunner"; then
  SERVICE_ARN="$(aws apprunner list-services --region "${REGION}" --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn | [0]" --output text)"
  echo "==> Updating App Runner service ${SERVICE_NAME}"
  aws apprunner update-service \
    --service-arn "${SERVICE_ARN}" \
    --source-configuration "${SOURCE_CONFIG}" \
    --instance-configuration "${INSTANCE_CONFIG}" \
    --region "${REGION}" >/dev/null
else
  echo "==> Creating App Runner service ${SERVICE_NAME}"
  SERVICE_ARN="$(aws apprunner create-service \
    --service-name "${SERVICE_NAME}" \
    --source-configuration "${SOURCE_CONFIG}" \
    --instance-configuration "${INSTANCE_CONFIG}" \
    --health-check-configuration '{"Protocol":"HTTP","Path":"/","Interval":10,"Timeout":5,"HealthyThreshold":1,"UnhealthyThreshold":3}' \
    --region "${REGION}" \
    --query Service.ServiceArn --output text)"
fi

echo "==> Waiting for service to reach RUNNING (this may take several minutes)…"
for _ in $(seq 1 60); do
  STATUS="$(aws apprunner describe-service --service-arn "${SERVICE_ARN}" --region "${REGION}" --query Service.Status --output text)"
  URL="$(aws apprunner describe-service --service-arn "${SERVICE_ARN}" --region "${REGION}" --query Service.ServiceUrl --output text)"
  echo "    status=${STATUS}  url=https://${URL}"
  if [[ "${STATUS}" == "RUNNING" ]]; then
    echo ""
    echo "Deploy complete."
    echo "  Service URL: https://${URL}"
    echo "  Health:      curl -s https://${URL}/"
    echo "  Smoke test:  ANSWER_BASE_URL=https://${URL} AWS_PROFILE=${AWS_PROFILE} .venv/bin/python answer/smoke_local.py"
    exit 0
  fi
  if [[ "${STATUS}" == "CREATE_FAILED" || "${STATUS}" == "UPDATE_FAILED" ]]; then
    echo "ERROR: App Runner deploy failed — check AWS console for ${SERVICE_NAME}"
    exit 1
  fi
  sleep 15
done

echo "WARN: Timed out waiting for RUNNING — check console. ServiceArn: ${SERVICE_ARN}"
exit 0
