# Tests

This folder is a staged validation path for the full Vonage + Pipecat + AWS agent, not just a collection of isolated smoke tests.

The goal is twofold:

- Prove each layer works before combining everything end to end.
- Keep each stage's code useful as a building block for the next stage or the full app.

## Execution Order

Run the folders in this order:

1. `c1_vonage_video_session`
2. `c2_video_connector_sdk`
3. `c3_pipecat_transport`
4. `c4a_aws_bedrock`
5. `c4b_bedrock_nova_sonic`
6. `c5_agentcore`

C1 is the bootstrap step for the Vonage side. It creates or confirms the session state that C2 and C3 need.

## What Each Folder Proves

### C1 — Vonage session bootstrap

C1 proves Vonage auth, session creation, and token generation in `tests/c1_vonage_video_session/test_session.py`.

It also gives you the browser playground URL and `VONAGE_SESSION_ID` that later Vonage transport tests depend on.

### C2 — Video Connector SDK join

C2 proves the Video Connector join flow in `tests/c2_video_connector_sdk/test_connector.py`.

This is the first Linux-native step and verifies that the Vonage server-side participant can join the session as a WebRTC client.

### C3 — Pipecat transport wiring

C3 proves the Pipecat transport wiring in `tests/c3_pipecat_transport/echo_bot.py`.

This is the key bridge between the raw Video Connector layer and the full app pipeline. It validates that Pipecat can receive audio from Vonage and send audio back into the same session.

### C4a — Bedrock credentials and low-cost text check

C4a validates the AWS-side basics separately before speech and runtime deployment are introduced.

It verifies AWS credentials, Bedrock access, and a simple Nova Lite text inference flow.

### C4b — Bedrock + Nova Sonic transport integration

C4b validates the Nova Sonic speech-to-speech layer combined with the Vonage transport path used by the full app.

It proves the integrated Pipecat + Vonage + Nova Sonic path is working.

### C5 — AgentCore deployable runtime

C5 keeps the deployable AgentCore artifact and the invocation check together, which is also reusable later.

That folder contains both the minimal runtime app and the script that invokes the deployed runtime.

## How This Connects To The Full App

The full app in `app/agent.py` clearly builds on the same transport shape proven in C3 and swaps `EchoService` for Nova Sonic plus AgentCore.

Conceptually, the progression is:

```text
C1: Vonage auth + session
C2: Video Connector joins session
C3: Pipecat transport over Vonage
C4a: Bedrock credentials + text model
C4b: Bedrock + Nova Sonic speech pipeline
C5: AgentCore deploy/invoke
App: C3 transport + C4b speech + C5 runtime
```

## Practical Guidance

For POC speed, treat these folders as validation stages first and refactor targets second.

That means:

- Use them to prove the path works.
- Reuse patterns and code snippets from them while building the app.
- Defer extracting shared helpers until the end-to-end flow is confirmed.
