# C4a — AWS Bedrock Credentials & Nova Lite Text Chat

Isolated test that verifies:

1. AWS credentials are correctly configured
2. Amazon Bedrock model access is enabled for your account
3. A simple text conversation works using **Amazon Nova Lite** (`amazon.nova-lite-v1:0`)

Nova Lite is a lightweight text model used here to validate the Bedrock pipeline before moving on to Nova Sonic (speech-to-speech) in test C4b.

**Platform:** Any (macOS, Linux, Windows)

---

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- AWS account with IAM credentials set in `.env`
- **Amazon Nova Lite** model access enabled in the [Bedrock console](https://console.aws.amazon.com/bedrock/home#/modelaccess) (us-east-1 recommended)

---

## Setup

```bash
cd tests/c4a_aws_bedrock

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# or with uv: uv venv && uv pip install -r requirements.txt
```

---

## Run

```bash
uv run python test_bedrock.py
# or without uv: source .venv/bin/activate && python3 test_bedrock.py
```

### Expected output

```
✓ AWS credentials found (region: us-east-1)
✓ Bedrock client initialised
✓ Model access verified: amazon.nova-lite-v1:0

Sending test prompt: "Say hello in exactly one sentence."
✓ Response received:
  Hello! I'm Nova Lite, an AI assistant — how can I help you today?

Test C4a PASSED ✓
```

---

## What it tests

| Step           | Description                                                                     |
| -------------- | ------------------------------------------------------------------------------- |
| Credentials    | Confirms `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION` are valid |
| Model listing  | Calls `ListFoundationModels` to verify Bedrock API access                       |
| Text inference | Calls `InvokeModel` with Nova Lite and a simple prompt                          |

---

## Troubleshooting

| Error                     | Fix                                                                    |
| ------------------------- | ---------------------------------------------------------------------- |
| `NoCredentialsError`      | Set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in `.env`          |
| `AccessDeniedException`   | Enable model access for `amazon.nova-lite-v1:0` in the Bedrock console |
| `EndpointResolutionError` | Check `AWS_REGION` — Bedrock is not available in all regions           |
| `ValidationException`     | Ensure `BEDROCK_MODEL_ID` format is correct                            |
