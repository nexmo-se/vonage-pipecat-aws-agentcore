# C3 — Pipecat Transport Echo Bot

Isolated test that runs a **Pipecat audio echo bot** using the official **Vonage Video Connector Pipecat transport**. Audio received from a browser participant is passed straight back into the session, validating the full Pipecat ↔ Vonage transport layer before adding model logic.

**Platform: Linux only** (Vonage Video Connector SDK is a native Linux binary). Use Docker on macOS.

> **Public Beta:** The Vonage Video Connector Pipecat integration is currently in beta. The official documentation is [the Vonage Pipecat transport guide](https://developer.vonage.com/en/video/guides/vonage-video-connector-pipecat-transport), and the published code source is [the Vonage Pipecat repository](https://github.com/Vonage/pipecat).

---

## Prerequisites

- Docker + Docker Compose (macOS) **or** Linux host with Python 3.13+ on Linux AMD64/ARM64
- Completed test **C1** — `VONAGE_SESSION_ID` must be set in `.env`
- `VONAGE_APPLICATION_ID` and `VONAGE_PRIVATE_KEY` set in `.env`
- A browser tab open on the Vonage playground URL from test C1 (to provide audio input)

### SDK versions (latest baseline)

This test tracks the latest stable SDK line and is currently validated with:

- `pipecat-ai[silero,webrtc]>=1.0.0`
- `vonage>=4.8.0`
- `vonage-video-connector>=1.0.0`

If you already created a virtualenv, refresh to the newest compatible packages before running:

```bash
pip install --upgrade -r requirements.txt
```

---

## Setup (macOS — Docker)

```bash
# From the repo root
docker compose run --rm --build c3-pipecat-transport
```

## Setup (native Linux)

```bash
cd tests/c3_pipecat_transport

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# or with uv: uv venv && uv pip install -r requirements.txt

uv run python echo_bot.py
# or without uv: source .venv/bin/activate && python3 echo_bot.py
```

---

## Expected output

```text
Initialising Vonage Pipecat transport for session 2_MX40...
✓ Connected to Vonage Video session 2_MX40...
Pipecat pipeline running — speak into your browser microphone
  Audio received → echoed back as audio
Press Ctrl+C to stop.
```

---

## How it works

```text
Browser mic → Vonage WebRTC → [Pipecat EchoService] → Vonage WebRTC → Browser speaker
```

Minimal official flow used by this test:

1. Create a Vonage participant token with the Vonage server SDK.
2. Initialise `VonageVideoConnectorTransport(application_id, session_id, token, params=...)`.
3. Enable audio in/out with `VonageVideoConnectorTransportParams`.
4. Build a simple pipeline: `transport.input() -> EchoService() -> transport.output()`.
5. Register basic lifecycle handlers such as `on_joined`, `on_participant_joined`, and `on_error`.

Official best practices kept in this test:

- `SileroVADAnalyzer()` enabled
- Official Vonage token creation flow via `TokenOptions`
- `audio_in_sample_rate=16000`
- `audio_out_sample_rate=24000`
- `audio_in_auto_subscribe=True`
- `video_in_auto_subscribe=False`
- `clear_buffers_on_interruption=True`
- `video_connector_log_level="INFO"`

## Official References

- [Vonage Video Connector Pipecat transport guide](https://developer.vonage.com/en/video/guides/vonage-video-connector-pipecat-transport)
- [Vonage Video Connector guide](https://developer.vonage.com/en/video/guides/vonage-video-connector)
- [Vonage Video Python Server SDK docs](https://developer.vonage.com/en/video/server-sdks/python)
- [Vonage Pipecat repository](https://github.com/Vonage/pipecat)

> **Note:** This test intentionally does not use STT, TTS, or an LLM. Its only purpose is to prove that the Vonage transport can receive and return live audio frames inside a Pipecat pipeline.

---

## Troubleshooting

| Error                                      | Fix                                                                                    |
| ------------------------------------------ | -------------------------------------------------------------------------------------- |
| `OSError: libvideo_connector.so not found` | Must run on Linux — use Docker on macOS                                                |
| No audio echo                              | Ensure a browser tab is joined and microphone is active                                |
| `ModuleNotFoundError: pipecat`             | Run `pip install -r requirements.txt`                                                  |
| Official beta API changes                  | Check the Vonage beta docs and `Vonage/pipecat` repo for the current transport surface |
