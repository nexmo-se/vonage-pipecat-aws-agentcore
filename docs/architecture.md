# Architecture Reference

Detailed architecture notes and diagrams for the `vonage-pipecat-aws-agentcore` project.

---

## Component Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                         External Services                             │
│                                                                      │
│  ┌──────────────────┐   ┌─────────────────┐   ┌──────────────────┐  │
│  │   Vonage Video   │   │  AWS Bedrock    │   │  AWS Bedrock     │  │
│  │   API Platform   │   │  Nova Sonic     │   │  AgentCore       │  │
│  │  (cloud, SaaS)   │   │  (us-east-1)    │   │  Runtime         │  │
│  └────────┬─────────┘   └────────┬────────┘   └────────┬─────────┘  │
│           │ WebRTC                │ HTTPS/WSS            │ HTTPS      │
└───────────│───────────────────────│──────────────────────│───────────┘
            │                       │                      │
┌───────────▼───────────────────────▼──────────────────────▼───────────┐
│                     Python Agent  (Linux · Docker)                    │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                      FastAPI Application                        │  │
│  │                        (port 8000)                              │  │
│  │                                                                 │  │
│  │  GET /          POST /join    POST /leave    WS /ws             │  │
│  └────────────────────────┬────────────────────────────────────── ┘  │
│                           │ asyncio.create_task                       │
│  ┌────────────────────────▼────────────────────────────────────── ┐  │
│  │                    Pipecat Pipeline                              │  │
│  │                                                                 │  │
│  │  VonageTransport.input()                                        │  │
│  │       │ AudioRawFrame (16 kHz, mono, PCM16)                    │  │
│  │       ▼                                                         │  │
│  │  SileroVADAnalyzer  (voice activity detection)                  │  │
│  │       │ UserStartedSpeakingFrame / UserStoppedSpeakingFrame     │  │
│  │       ▼                                                         │  │
│  │  NovaSonicService.stt()  (streaming speech → text)             │  │
│  │       │ TranscriptionFrame                                      │  │
│  │       ▼                                                         │  │
│  │  AgentCoreService  (LLM reasoning)                              │  │
│  │       │ TextFrame                                               │  │
│  │       ▼                                                         │  │
│  │  NovaSonicService.tts()  (text → streaming speech)             │  │
│  │       │ AudioRawFrame                                           │  │
│  │       ▼                                                         │  │
│  │  VonageTransport.output()                                       │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │           Video Connector SDK  (native Linux binary)            │  │
│  │           Joins Vonage session as WebRTC participant            │  │
│  └────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
            │
┌───────────▼───────────────────────────────────────────────────────────┐
│                     Browser / Mobile Client                            │
│              (Vonage Video Web SDK · OpenTok.js)                      │
│              Sends microphone audio · Receives agent speech           │
└───────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Inbound (Browser → Agent)

1. Browser captures microphone audio via WebRTC
2. Vonage Video Platform routes the media stream to the Video Connector SDK
3. The SDK surfaces audio as PCM16 frames to `VonageTransport.input()`
4. Silero VAD detects speech start/end events
5. Nova Sonic STT converts speech frames to a `TranscriptionFrame`
6. AgentCore receives the transcript and returns an LLM text response

### Outbound (Agent → Browser)

1. Nova Sonic TTS converts the AgentCore text response to audio frames
2. `VonageTransport.output()` sends audio frames to the Video Connector SDK
3. The SDK publishes synthesised speech into the WebRTC session
4. Vonage routes the audio to all browser subscribers

---

## Frame Types (Pipecat)

| Frame | Direction | Description |
|---|---|---|
| `AudioRawFrame` | In / Out | Raw PCM audio (16 kHz, mono, 16-bit) |
| `UserStartedSpeakingFrame` | Internal | VAD detected speech start |
| `UserStoppedSpeakingFrame` | Internal | VAD detected speech end |
| `TranscriptionFrame` | Internal | STT output text |
| `TextFrame` | Internal | AgentCore LLM response text |

---

## Latency Budget

| Stage | Typical latency |
|---|---|
| VAD detection | < 50 ms |
| Nova Sonic STT (first token) | ~200–400 ms |
| AgentCore inference (first token) | ~300–600 ms |
| Nova Sonic TTS (first audio chunk) | ~100–200 ms |
| Vonage media routing | < 50 ms |
| **Total (time-to-first-audio)** | **~650–1300 ms** |

All stages are streaming — audio playback starts as soon as the first TTS chunk is ready, without waiting for the complete response.

---

## Security Notes

- **Credentials** — Store in `.env` (gitignored). Use AWS Secrets Manager or IAM instance roles in production.
- **Vonage tokens** — Tokens are scoped to a single session with a 2-hour expiry (`expire_time=7200`). Rotate on each pipeline start.
- **Network** — The agent runs with `network_mode: host` in Docker to allow WebRTC ICE negotiation with the Vonage TURN servers. Restrict inbound traffic to port 8000 (FastAPI) only.
- **AgentCore** — Agent ARNs are not secret but should not be exposed publicly. The management API (`/join`, `/leave`) should be placed behind authentication in production.
