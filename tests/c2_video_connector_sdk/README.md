# C2 — Vonage Video Connector SDK

Isolated test that verifies the **Vonage Video Connector SDK** can join an existing Vonage Video session as a server-side WebRTC participant.

**Platform: Linux only** (the SDK ships as a native Linux binary). Use Docker on macOS.

---

## Prerequisites

- Docker + Docker Compose (macOS) **or** Linux host with Python 3.11+
- Completed test **C1** — `VONAGE_SESSION_ID` must be set in `.env`
- `VONAGE_APPLICATION_ID` and `VONAGE_PRIVATE_KEY` set in `.env`

---

## Setup (macOS — Docker)

```bash
# From the repo root
docker compose run --rm --build c2-video-connector
```

## Setup (native Linux)

```bash
cd tests/c2_video_connector_sdk

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# or with uv: uv venv && uv pip install -r requirements.txt

uv run python test_connector.py
# or without uv: source .venv/bin/activate && python3 test_connector.py
```

---

## Expected output

```
✓ Generated publisher token
Connecting to session 2_MX40... as WebRTC participant …
✓ Connected to session as WebRTC participant
Staying connected for 5 seconds …
✓ Disconnected from session

Test C2 PASSED ✓
```

While the script is running you should also see a new participant appear in the browser tab you opened during test C1.

---

## What it tests

1. Generates a Vonage publisher token from existing session
2. Initialises the Video Connector SDK with that token
3. Joins the session as a WebRTC participant (audio/video capable)
4. Stays connected for 5 seconds then disconnects cleanly

---

## Troubleshooting

| Error                                      | Fix                                                         |
| ------------------------------------------ | ----------------------------------------------------------- |
| `OSError: libvideo_connector.so not found` | Must run on Linux — use Docker on macOS                     |
| `Connection refused`                       | Check `VONAGE_SESSION_ID` is correct and the session exists |
| `Unauthorized`                             | Verify `VONAGE_APPLICATION_ID` and `VONAGE_PRIVATE_KEY`     |
