# Agent: voice-agent
# Security Level: 3 (HIGH)
# Purpose: AI voice calls with Telnyx + Deepgram STT + ElevenLabs TTS

FROM python:3.11-slim

# Metadata
LABEL agent.name="voice-agent"
LABEL agent.version="1.0.0"
LABEL agent.security_level="3"
LABEL agent.port="8302"

# Security: Update packages and install dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gcc \
        python3-dev \
        libffi-dev \
        libssl-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Working directory
WORKDIR /app

# Copy shared libraries
COPY lib/ ./lib/

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Remove build tools after install (security)
RUN apt-get purge -y gcc python3-dev libffi-dev libssl-dev && \
    apt-get autoremove -y && \
    apt-get clean

# Copy agent code
COPY api_server.py .
COPY websocket_server.py .
COPY config.yaml .
COPY scripts/ ./scripts/

# Create non-root user
RUN useradd -m -u 1000 voice-agent && \
    chown -R voice-agent:voice-agent /app && \
    mkdir -p /var/log/agent && \
    chown voice-agent:voice-agent /var/log/agent

# Switch to non-root user
USER voice-agent

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Expose ports
# 8080 = HTTP API
# 8081 = WebSocket (internal, Telnyx media stream)
EXPOSE 8080 8081

# Start servers
CMD ["python", "api_server.py"]
