FROM python:3.13-slim

# Install system dependencies required by the Video Connector native library
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl-dev \
    libexpat1 \
    libpulse0 \
    alsa-utils \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

# Copy test script
COPY test_connector.py .

CMD ["python", "test_connector.py"]
