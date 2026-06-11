# AgentCore Runtime requires ARM64 containers.
# Build: docker buildx build --platform linux/arm64 -t c6-agentcore-video .
FROM --platform=linux/arm64 python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libssl-dev \
    libexpat1 \
    libpulse0 \
    alsa-utils \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

COPY vonage_env.py .
COPY network_probe.py .
COPY vonage_turn.py .
COPY agentcore_video_agent.py .
# Copied from repo root at deploy time (see README — same as c4 private.key mount)
COPY private.key .

EXPOSE 8080

# Default: run AgentCore runtime entrypoint (deploy artifact)
CMD ["python", "agentcore_video_agent.py"]
