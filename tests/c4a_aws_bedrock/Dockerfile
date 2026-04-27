FROM python:3.13-slim

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

COPY test_bedrock.py .
COPY bedrock_transport_integration.py .
COPY bedrock_echo_agent.py .

# Default command: credential test (Stage 1)
# Override with: docker run c4a-bedrock python bedrock_echo_agent.py (for Stage 2)
CMD ["python", "test_bedrock.py"]
