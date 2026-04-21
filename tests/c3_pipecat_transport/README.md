# C3 — Pipecat Transport Echo Bot

Isolated test that runs a **Pipecat AI echo bot** using the Vonage Video Connector transport. Audio received from a browser participant is captured, transcribed, and echoed back — validating the full Pipecat ↔ Vonage transport layer before adding an LLM.

**Platform: Linux only** (Vonage Video Connector SDK is a native Linux binary). Use Docker on macOS.

---

## Prerequisites

- Docker + Docker Compose (macOS) **or** Linux host with Python 3.11+
- Completed test **C1** — `VONAGE_SESSION_ID` must be set in `.env`
- `VONAGE_APPLICATION_ID` and `VONAGE_PRIVATE_KEY` set in `.env`
- A browser tab open on the Vonage playground URL from test C1 (to provide audio input)

---

## Setup (macOS — Docker)

```bash
# From the repo root
docker compose run --rm --build c3-pipecat-transport
```

## Setup (native Linux)

```bash
cd tests/c3_pipecat_transport

uv venv
uv pip install -r requirements.txt

uv run python echo_bot.py
```

---

## Expected output

```
Initialising Vonage transport for session 2_MX40...
✓ Connected to Vonage Video session
Pipecat pipeline running — speak into your browser microphone
  Audio received → transcribed → echoed back as TTS
Press Ctrl+C to stop.
```

---

## How it works

```
Browser mic → Vonage WebRTC → [Pipecat] → STT → passthrough → TTS → Vonage WebRTC → Browser speaker
```

The pipeline uses:
- `VonageTransport` — receives audio frames from the Vonage session
- `DeepgramSTTService` (or built-in Whisper) — speech-to-text
- `EchoProcessor` — passes transcript straight back
- `CartesiaTTSService` (or built-in pyttsx3) — text-to-speech
- `VonageTransport` — sends audio back into the session

> **Note:** For simplicity this test uses placeholder STT/TTS services. Swap in your preferred provider for production use.

---

## Troubleshooting

| Error | Fix |
|---|---|
| `OSError: libvideo_connector.so not found` | Must run on Linux — use Docker on macOS |
| No audio echo | Ensure a browser tab is joined and microphone is active |
| `ModuleNotFoundError: pipecat` | Run `uv pip install -r requirements.txt` |
