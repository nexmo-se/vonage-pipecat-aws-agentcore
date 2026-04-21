# C4b — AWS Nova Sonic Speech-to-Speech Pipeline

Isolated test that runs **Amazon Nova Sonic** (`amazon.nova-sonic-v1:0`) as a standalone Pipecat speech-to-speech pipeline — without Vonage or AgentCore. Audio is read from a local file (or microphone), sent to Nova Sonic for bidirectional speech processing, and the response audio is written to a local file.

This validates the Nova Sonic ↔ Pipecat integration before adding the Vonage transport in the full app.

**Platform:** Any (macOS, Linux, Windows)

---

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- AWS credentials with Bedrock access (`test C4a` passed)
- **Amazon Nova Sonic** model access enabled in the Bedrock console
- `ffmpeg` installed on your system (used by pipecat for audio conversion)

---

## Setup

```bash
cd tests/c4b_nova_sonic

uv venv
uv pip install -r requirements.txt
```

---

## Run

```bash
uv run python test_nova_sonic.py
```

### Expected output

```
✓ Nova Sonic pipeline initialised
Sending audio input: test_input.wav
✓ Nova Sonic responded (1.4 s)
Response audio saved to: response_output.wav

Test C4b PASSED ✓
```

The script writes `response_output.wav` to the current directory. Play it to verify Nova Sonic responded correctly.

---

## What it tests

| Step | Description |
|---|---|
| Bedrock session | Opens a bidirectional streaming session with Nova Sonic |
| Audio input | Sends a short WAV file as the user's speech input |
| Audio output | Receives synthesised speech from Nova Sonic |
| Pipecat pipeline | Wires input → Nova Sonic → output through Pipecat frame types |

---

## Troubleshooting

| Error | Fix |
|---|---|
| `AccessDeniedException` | Enable `amazon.nova-sonic-v1:0` model access in the Bedrock console |
| `ffmpeg not found` | Install ffmpeg: `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux) |
| Empty output file | Nova Sonic may have rejected the audio format — ensure input is 16 kHz mono WAV |
