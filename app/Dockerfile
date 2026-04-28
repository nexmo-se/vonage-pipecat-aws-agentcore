FROM python:3.13-slim

# System dependencies for Video Connector + audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libssl-dev \
    libexpat1 \
    libpulse0 \
    alsa-utils \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install runtime dependencies (aligned with validated C4 setup)
COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt

# Copy application source
COPY main.py agent.py ./

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
