# C1 — Vonage Video Session Creation

Isolated test that verifies you can authenticate with the Vonage Video API, create a session, generate a client token, and produce a browser-accessible demo URL.

**Platform:** Any (macOS, Linux, Windows)

## What is Vonage Video API?

**Vonage Video API** (formerly OpenTok) is a real-time communications platform that provides:

- **Session management:** Create and manage persistent communication sessions.
- **Media routing:** Route audio/video between participants (browsers, servers, apps).
- **WebRTC infrastructure:** Handle NAT traversal, codecs, and media negotiation.
- **Client SDKs:** Browser (Web SDK) and server-side (Video Connector) libraries for joining sessions.

In this project, Vonage Video serves as the **session layer and media intermediary**. Browser users and the AI agent both join the same Vonage session; Vonage routes media between them in real time.

## Purpose

This C1 test validates that you can:

- Authenticate to Vonage Video API with your credentials.
- Create a persistent session for use in C2–C3 tests.
- Generate a browser-compatible token to join that session manually.
- See the session accessible in the Vonage Playground.

When complete, you have a real Vonage session ID and understand the browser join flow.

## C1 Checklist

Run C1 with this quick checklist:

1. Create `.env` from `.env.example` at repo root.
2. Set `VONAGE_APPLICATION_ID` and `VONAGE_PRIVATE_KEY`.
3. Ensure your private key file exists at the configured path.
4. Run `test_session.py`.
5. Confirm `VONAGE_SESSION_ID` is saved in root `.env` (C1 writes it automatically when created).
6. Open the printed browser playground URL and confirm you can join.

When all six are complete, you are ready for C2.

## How `.env` Gets Populated

Before running C1, you provide these required values in root `.env`:

- `VONAGE_APPLICATION_ID`
- `VONAGE_PRIVATE_KEY`

At runtime, C1 handles the rest:

1. Reads `VONAGE_SESSION_ID` from `.env`.
2. If the value is missing or a placeholder (for example `your-vonage-session-id`), it creates a new Vonage Video session.
3. Writes the new `VONAGE_SESSION_ID` back to root `.env` automatically.
4. Generates a publisher token for that session.
5. Prints a browser playground URL that includes `apiKey`, `sessionId`, and token.

Token behavior:

- The token is generated dynamically each run.
- It is printed to terminal as part of the URL.
- It is not saved into `.env`.

---

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) installed
- A Vonage account with a **Video API** application created in the [dashboard](https://dashboard.nexmo.com)
- Your application's `private.key` file downloaded to the repo root (or the path set in `VONAGE_PRIVATE_KEY`)
- Official Vonage Python SDK installed from `requirements.txt` (`vonage>=4.0.0`)

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

## Commands To Run In Terminal

### Option A (from repo root)

```bash
# one-time setup
cp .env.example .env
# edit .env and set VONAGE_APPLICATION_ID + VONAGE_PRIVATE_KEY

cd tests/c1_vonage_video_session
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# run C1
python3 test_session.py
```

### Option B (if you are already in this C1 folder)

```bash
source .venv/bin/activate
python3 test_session.py
```

### Command And Expected Result (quick copy/paste)

Command to enter:

```bash
source .venv/bin/activate
python3 test_session.py
```

Expected terminal result (shape):

```text
Creating new Vonage Video session …
✓ Created session: 2_MX...
✓ Saved VONAGE_SESSION_ID to <repo-root>/.env
  ➜ Added VONAGE_SESSION_ID=2_MX... to your .env file

✓ Generated client token (publisher, 24 h)

============================================================
Browser Demo URL:
https://tokbox.com/developer/tools/playground/?apiKey=...&sessionId=...&token=...
============================================================

Open the URL above in a browser to join the video session.

Test C1 PASSED ✓
```

If `.env` already has a real `VONAGE_SESSION_ID`, expected output starts with:

```text
✓ Using existing session: 2_MX...
```

---

## Run

```bash
uv run python test_session.py
# or without uv: source .venv/bin/activate && python3 test_session.py
```

### Expected output

```text
✓ Created session: 2_MX40...
✓ Saved VONAGE_SESSION_ID to /.../.env
  ➜ Added VONAGE_SESSION_ID=2_MX40... to your .env file

✓ Generated client token

============================================================
Browser Demo URL:
https://tokbox.com/developer/tools/playground/?apiKey=...
============================================================

Open the URL above in a browser to join the video session.

Test C1 PASSED ✓
```

C1 now auto-saves `VONAGE_SESSION_ID` into your root `.env` when it creates a new session. Subsequent tests use this value directly.

If `.env` contains a placeholder value such as `your-vonage-session-id`, C1 treats it as missing and creates a real session ID.

## Exit Criteria

C1 is considered complete when all of the following are true:

1. Script ends with `Test C1 PASSED`.
2. `VONAGE_SESSION_ID` is set in root `.env`.
3. Browser playground URL opens successfully.
4. You can join the generated Vonage Video session in the browser.

---

## What it tests

1. Official Vonage Python SDK authentication using `VONAGE_APPLICATION_ID` + `VONAGE_PRIVATE_KEY`
2. Video session creation via the Vonage Video REST API
3. Client token generation with a `publisher` role
4. Produces a Vonage playground URL so you can verify the session visually in a browser

## Why this folder matters later

Even though C1 is the bootstrap step rather than the most reusable transport test, `test_session.py` now keeps the Vonage setup flow in explicit helper functions for:

- loading bootstrap config from `.env`
- creating the Vonage client
- creating or reusing a session
- generating a publisher token
- building the browser playground URL

That makes C1 the cleanest place in the repo to lift the initial Vonage session/token setup from when similar browser bootstrap logic is added to the final app.

## Official Vonage References

Use these as source-of-truth references when reviewing or extending C1:

- [Vonage Video Python Server SDK docs](https://developer.vonage.com/en/video/server-sdks/python)
- [Vonage Python SDK repository](https://github.com/Vonage/vonage-python-sdk)
- [Vonage Python SDK Video examples (`create_session`, `generate_client_token`)](https://github.com/Vonage/vonage-python-sdk/blob/main/video/README.md)
- [Vonage Video API overview](https://developer.vonage.com/en/video/overview)
- [Vonage Video developer playground](https://developer.vonage.com/en/video/developer-tools/playground)

---

## Troubleshooting

| Error                       | Fix                                                                           |
| --------------------------- | ----------------------------------------------------------------------------- |
| `Authentication failed`     | Check `VONAGE_APPLICATION_ID` and that `private.key` path is correct          |
| `vonage.errors.ClientError` | Ensure your application has **Video API** capability enabled in the dashboard |
| `ModuleNotFoundError`       | Run `uv pip install -r requirements.txt` inside the virtual environment       |
