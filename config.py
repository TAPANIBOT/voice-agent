"""Voice Agent configuration from environment variables."""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # Deepgram STT
    deepgram_api_key: str = field(default_factory=lambda: os.getenv("DEEPGRAM_API_KEY", ""))

    # OpenAI TTS
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))

    # LLM (via OpenRouter, OpenAI-compatible)
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "google/gemini-2.5-flash"))

    # Server
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8302")))

    # OpenClaw gateway (for function calling)
    openclaw_gateway_url: str = field(default_factory=lambda: os.getenv("OPENCLAW_GATEWAY_URL", "http://localhost:18789"))

    # Call limits
    max_call_duration: int = field(default_factory=lambda: int(os.getenv("MAX_CALL_DURATION", "600")))
    max_concurrent_calls: int = field(default_factory=lambda: int(os.getenv("MAX_CONCURRENT_CALLS", "5")))

    # TURN server (Metered.ca)
    turn_api_key: str = field(default_factory=lambda: os.getenv("TURN_API_KEY", ""))
    turn_api_url: str = field(default_factory=lambda: os.getenv(
        "TURN_API_URL", "https://tapani.metered.live/api/v1/turn/credentials"
    ))

    # Telnyx PSTN
    telnyx_api_key: str = field(default_factory=lambda: os.getenv("TELNYX_API_KEY", ""))
    telnyx_phone_number: str = field(default_factory=lambda: os.getenv("TELNYX_PHONE_NUMBER", ""))
    telnyx_connection_id: str = field(default_factory=lambda: os.getenv("TELNYX_CONNECTION_ID", ""))
    public_url: str = field(default_factory=lambda: os.getenv("PUBLIC_URL", ""))

    # Number safety
    allowed_prefixes: list = field(default_factory=lambda: os.getenv(
        "ALLOWED_PREFIXES", "+358,+46,+1"
    ).split(","))
    blocked_prefixes: list = field(default_factory=lambda: os.getenv(
        "BLOCKED_PREFIXES", "+3580700,+3580600"
    ).split(","))

    @property
    def ws_url(self) -> str:
        """WebSocket URL for Telnyx media streaming."""
        if self.public_url:
            scheme = "wss" if self.public_url.startswith("https") else "ws"
            host = self.public_url.replace("https://", "").replace("http://", "")
            return f"{scheme}://{host}/ws/telnyx"
        return f"ws://localhost:{self.port}/ws/telnyx"

    def validate(self) -> list[str]:
        """Return list of missing required config values for WebRTC mode."""
        missing = []
        if not self.deepgram_api_key:
            missing.append("DEEPGRAM_API_KEY")
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.openrouter_api_key:
            missing.append("OPENROUTER_API_KEY")
        return missing


config = Config()
