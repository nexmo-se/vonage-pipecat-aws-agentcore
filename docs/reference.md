# Reference Notes

Collected reference information for packages, APIs, and configuration used in this project.

---

## Python Packages

| Package                  | Version   | Purpose                                                 |
| ------------------------ | --------- | ------------------------------------------------------- |
| `vonage`                 | ≥ 4.0.0   | Vonage Video API — session management, token generation |
| `vonage-video-connector` | ≥ 1.0.0   | Server-side WebRTC participant (Linux native binary)    |
| `pipecat-ai`             | ≥ 0.0.50  | Real-time audio/video pipeline framework                |
| `boto3`                  | ≥ 1.34.0  | AWS SDK — Bedrock, BedrockRuntime, AgentCore clients    |
| `bedrock-agentcore`      | ≥ 0.1.0   | AWS Bedrock AgentCore SDK                               |
| `fastapi`                | ≥ 0.110.0 | ASGI web framework                                      |
| `uvicorn`                | ≥ 0.29.0  | ASGI server                                             |
| `python-dotenv`          | ≥ 1.0.0   | `.env` file loader                                      |
| `structlog`              | ≥ 24.1.0  | Structured logging                                      |

---

## AWS Bedrock Model IDs

| Model             | ID                       | Notes                                             |
| ----------------- | ------------------------ | ------------------------------------------------- |
| Amazon Nova Sonic | `amazon.nova-sonic-v1:0` | Speech-to-speech, primary agent model             |
| Amazon Nova Lite  | `amazon.nova-lite-v1:0`  | Text-only, used for credential testing in C4a     |
| Amazon Nova Pro   | `amazon.nova-pro-v1:0`   | Larger text model, optional AgentCore backing LLM |

Enable model access at:  
`https://console.aws.amazon.com/bedrock/home#/modelaccess`

---

## AWS IAM Permissions Required

Minimum IAM policy for the agent's AWS credentials:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:ListFoundationModels",
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:CreateAgent",
        "bedrock-agentcore:InvokeAgent",
        "bedrock-agentcore:DeleteAgent",
        "bedrock-agentcore:GetAgent",
        "bedrock-agentcore:ListAgents"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## Vonage Video API

### Session media modes

| Mode      | Description                                                               |
| --------- | ------------------------------------------------------------------------- |
| `routed`  | Media routes through Vonage cloud (required for server-side participants) |
| `relayed` | Peer-to-peer (not compatible with Video Connector SDK)                    |

Always use `routed` mode when using the Video Connector SDK.

### Token roles

| Role         | Capabilities                                    |
| ------------ | ----------------------------------------------- |
| `publisher`  | Can publish audio/video and subscribe to others |
| `subscriber` | Can only subscribe (listen/watch)               |
| `moderator`  | Publisher + can force-disconnect participants   |

The agent uses the `publisher` role.

---

## Pipecat Frame Pipeline

Frames flow left → right through pipeline stages:

```
AudioRawFrame
  └── [VonageTransport.input]
        └── [SileroVADAnalyzer]
              ├── UserStartedSpeakingFrame
              └── UserStoppedSpeakingFrame
                    └── [NovaSonicService.stt]
                          └── TranscriptionFrame
                                └── [AgentCoreService]
                                      └── TextFrame
                                            └── [NovaSonicService.tts]
                                                  └── AudioRawFrame
                                                        └── [VonageTransport.output]
```

---

## Nova Sonic Audio Requirements

| Parameter   | Value          |
| ----------- | -------------- |
| Sample rate | 16,000 Hz      |
| Channels    | 1 (mono)       |
| Bit depth   | 16-bit PCM     |
| Container   | Raw PCM or WAV |

The Pipecat `VonageTransport` outputs audio in this format by default.

---

## Environment Variables Reference

| Variable                | Required | Default                  | Description                            |
| ----------------------- | -------- | ------------------------ | -------------------------------------- |
| `VONAGE_APPLICATION_ID` | ✅       | —                        | Vonage application UUID                |
| `VONAGE_PRIVATE_KEY`    | ✅       | `private.key`            | Path to private key file               |
| `VONAGE_SESSION_ID`     | ✅       | —                        | Vonage Video session ID                |
| `AWS_PROFILE`           | ❌       | —                        | AWS CLI profile name (recommended)     |
| `AWS_ACCESS_KEY_ID`     | ❌       | —                        | AWS IAM access key (optional fallback) |
| `AWS_SECRET_ACCESS_KEY` | ❌       | —                        | AWS IAM secret key (optional fallback) |
| `AWS_REGION`            | ❌       | `us-east-1`              | AWS region                             |
| `BEDROCK_MODEL_ID`      | ❌       | `amazon.nova-sonic-v1:0` | Bedrock model ID                       |
| `AGENTCORE_AGENT_ARN`   | ✅       | —                        | AgentCore agent ARN                    |
| `PORT`                  | ❌       | `8000`                   | FastAPI server port                    |

---

## Useful Links

- [Vonage Video API Documentation](https://developer.vonage.com/en/video/overview)
- [Vonage Video Connector SDK](https://developer.vonage.com/en/video/guides/video-connector)
- [Pipecat AI Documentation](https://docs.pipecat.ai)
- [AWS Bedrock Nova Sonic](https://docs.aws.amazon.com/bedrock/latest/userguide/nova-sonic.html)
- [AWS Bedrock AgentCore](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [boto3 Bedrock Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock.html)
