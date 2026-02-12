# Tapani Voice Agent — Pipecat WebRTC + Deepgram + OpenAI TTS
# Security Level: 3 (HIGH)

FROM python:3.12-slim

LABEL agent.name="voice-agent"
LABEL agent.version="2.0.0"
LABEL agent.security_level="3"
LABEL agent.port="8302"

# System dependencies (libxcb etc. needed by OpenCV which pipecat webrtc pulls in)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        libxcb1 \
        libgl1 \
        libglib2.0-0 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download NLTK data (read-only filesystem needs this baked in)
ENV NLTK_DATA=/app/nltk_data
RUN mkdir -p /app/nltk_data && \
    python -c "import nltk; nltk.download('punkt_tab', download_dir='/app/nltk_data')" || true

# Copy application code
COPY config.py .
COPY bot.py .
COPY server.py .

# Non-root user
RUN useradd -m -u 1000 voice-agent && \
    chown -R voice-agent:voice-agent /app && \
    mkdir -p /var/log/agent && \
    chown voice-agent:voice-agent /var/log/agent

USER voice-agent

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8302/health || exit 1

EXPOSE 8302

CMD ["python", "server.py"]
