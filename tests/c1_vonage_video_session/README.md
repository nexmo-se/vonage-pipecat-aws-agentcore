# C1 — Vonage Video Session Creation

Isolated test that verifies you can authenticate with the Vonage Video API, create a session, generate a client token, and produce a browser-accessible demo URL.

**Platform:** Any (macOS, Linux, Windows)

---

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) installed
- A Vonage account with a **Video API** application created in the [dashboard](https://dashboard.nexmo.com)
- Your application's `private.key` file downloaded to the repo root (or the path set in `VONAGE_PRIVATE_KEY`)

---

## Setup

```bash
# From the repo root, copy and fill in credentials
cp .env.example .env
# Set VONAGE_APPLICATION_ID and VONAGE_PRIVATE_KEY in .env

# Move to this test folder
cd tests/c1_vonage_video_session

# Create virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# or with uv: uv venv && uv pip install -r requirements.txt
```

---

## Run

```bash
uv run python test_session.py
# or without uv: source .venv/bin/activate && python3 test_session.py
```

### Expected output

```
✓ Created session: 2_MX40...
  Add VONAGE_SESSION_ID=2_MX40... to your .env file

✓ Generated client token

============================================================
Browser Demo URL:
https://tokbox.com/developer/tools/playground/?apiKey=...
============================================================

Open the URL above in a browser to join the video session.
```

Copy the `VONAGE_SESSION_ID` value printed above into your root `.env` file — subsequent tests use it.

---

## What it tests

1. Vonage SDK authentication using `VONAGE_APPLICATION_ID` + `VONAGE_PRIVATE_KEY`
2. Video session creation via the Vonage Video REST API
3. Client token generation with a `publisher` role
4. Produces a Vonage playground URL so you can verify the session visually in a browser

---

## Troubleshooting

| Error                       | Fix                                                                           |
| --------------------------- | ----------------------------------------------------------------------------- |
| `Authentication failed`     | Check `VONAGE_APPLICATION_ID` and that `private.key` path is correct          |
| `vonage.errors.ClientError` | Ensure your application has **Video API** capability enabled in the dashboard |
| `ModuleNotFoundError`       | Run `uv pip install -r requirements.txt` inside the virtual environment       |
