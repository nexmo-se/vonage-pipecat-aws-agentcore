FROM python:3.11-slim

# System dependencies for Video Connector + audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl-dev \
    libpulse0 \
    alsa-utils \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy project definition and install dependencies
COPY pyproject.toml .
RUN uv pip install --system -e .

# Copy application source
COPY main.py agent.py ./

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
