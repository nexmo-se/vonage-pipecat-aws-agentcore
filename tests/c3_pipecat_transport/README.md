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

- `pipecat-ai[silero,webrtc,vonage-video-connector]` from the official [Vonage/pipecat](https://github.com/Vonage/pipecat) repository
- `vonage>=4.8.0`
- `vonage-video-connector>=1.0.0`
- `websockets>=15.0.0`

> Because the Vonage Pipecat transport is in public beta, this test installs Pipecat from the official Vonage source repository rather than relying only on PyPI package contents.

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
Browser mic → Vonage WebRTC → [Pipecat passthrough pipeline] → Vonage WebRTC → Browser speaker
```

Minimal official flow used by this test:

1. Create a Vonage participant token with the Vonage server SDK.
2. Initialise `VonageVideoConnectorTransport(application_id, session_id, token, params=...)`.
3. Enable audio in/out with `VonageVideoConnectorTransportParams`.
4. Build a simple passthrough pipeline: `transport.input() -> transport.output()`.
5. Register basic lifecycle handlers such as `on_joined`, `on_participant_joined`, and `on_error`.

Official best practices kept in this test:

- `SileroVADAnalyzer()` enabled
- Official Vonage token creation flow via `TokenOptions`
- `audio_in_sample_rate=16000`
- `audio_out_sample_rate=24000`
- `audio_in_channels=1` and `audio_out_channels=1`
- `audio_in_auto_subscribe=True`
- `video_in_auto_subscribe=False`
- `clear_buffers_on_interruption=True`
- `video_connector_log_level="INFO"`
- Session/client lifecycle handlers: `on_joined`, `on_first_participant_joined`, `on_participant_joined`, `on_participant_left`, `on_client_connected`, `on_client_disconnected`, `on_error`

### Optional transport tuning (env vars)

You can tune a few official transport parameters without changing code:

- `VONAGE_VIDEO_CONNECTOR_LOG_LEVEL=INFO|DEBUG|WARNING|ERROR` (default `INFO`)
- `VONAGE_SESSION_ENABLE_MIGRATION=true|false` (default `false`)
- `VONAGE_CLEAR_BUFFERS_ON_INTERRUPTION=true|false` (default `true`)
- `VONAGE_ENABLE_PIPECAT_LOGGER=true|false` (default `true`)
- `VONAGE_MONITOR_ENABLED=true|false` (default `true`)
- `VONAGE_MONITOR_INTERVAL_SECONDS` (default `15`)
- `VONAGE_DEBUG_EVENT_PAYLOADS=true|false` (default `false`)

Additional official transport params supported by this test:

- `VONAGE_PUBLISHER_NAME` (default `Pipecat Echo Bot`)
- `VONAGE_PUBLISHER_ENABLE_OPUS_DTX=true|false` (default `false`)
- `VONAGE_AUDIO_IN_ENABLED=true|false` (default `true`)
- `VONAGE_AUDIO_OUT_ENABLED=true|false` (default `true`)
- `VONAGE_VIDEO_IN_ENABLED=true|false` (default `false`)
- `VONAGE_VIDEO_OUT_ENABLED=true|false` (default `false`)
- `VONAGE_AUDIO_IN_SAMPLE_RATE` (default `16000`)
- `VONAGE_AUDIO_OUT_SAMPLE_RATE` (default `24000`)
- `VONAGE_AUDIO_IN_CHANNELS` (default `1`)
- `VONAGE_AUDIO_OUT_CHANNELS` (default `1`)
- `VONAGE_VIDEO_OUT_WIDTH` (default `1280`)
- `VONAGE_VIDEO_OUT_HEIGHT` (default `720`)
- `VONAGE_VIDEO_OUT_FRAMERATE` (default `30`)
- `VONAGE_VIDEO_OUT_COLOR_FORMAT` (default `RGB`)
- `VONAGE_AUDIO_IN_AUTO_SUBSCRIBE=true|false` (default `true`)
- `VONAGE_VIDEO_IN_AUTO_SUBSCRIBE=true|false` (default `false`)
- `VONAGE_VIDEO_IN_PREFERRED_RESOLUTION` (default `640x480`)
- `VONAGE_VIDEO_IN_PREFERRED_FRAMERATE` (default `15`)

### Optional manual stream subscription mode

Official docs recommend manual subscription for selective stream control. This test supports that mode:

- `VONAGE_MANUAL_SUBSCRIBE=true|false` (default `false`)
- `VONAGE_MANUAL_SUBSCRIBE_VIDEO=true|false` (default `false`)
- `VONAGE_VIDEO_IN_PREFERRED_RESOLUTION=640x480` (default `640x480`)
- `VONAGE_VIDEO_IN_PREFERRED_FRAMERATE=15` (default `15`)

When `VONAGE_MANUAL_SUBSCRIBE=true`, the bot subscribes per participant in `on_participant_joined` using `SubscribeSettings`.
For this echo test, audio is always subscribed; video subscription stays optional.

> Note: Per official docs, subscribed audio is currently mixed into a single audio stream for the pipeline.

### Debugging and monitoring (doc-aligned)

This test now adds lightweight runtime monitoring around official session/client events:

- Tracks active stream IDs and active subscriber IDs
- Counts participant/client connect/disconnect and error events
- Emits periodic monitor snapshots via loguru
- Can emit full event payloads for debugging

Recommended debug run:

```bash
VONAGE_VIDEO_CONNECTOR_LOG_LEVEL=DEBUG \
VONAGE_DEBUG_EVENT_PAYLOADS=true \
VONAGE_MONITOR_INTERVAL_SECONDS=10 \
docker compose run --rm --build c3-pipecat-transport
```

Expected debug log checklist:

- Session lifecycle:
  - `Session connected ...`
  - `ready to publish`
  - `Connected to Vonage Video session ...`
- Participant lifecycle:
  - `First participant joined with stream ...`
  - `Participant joined with stream ...`
  - `Participant left stream ...` (when a participant leaves)
- Client connection events:
  - `Client connected to stream ...`
  - `Client disconnected from stream ...`
- Monitoring snapshots:
  - `monitor: active_streams=... active_subscribers=... event_counts=...`
- Error path (should normally be absent):
  - `ERROR: Transport error — ...`

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
