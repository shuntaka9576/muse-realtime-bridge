import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    openai_api_key: str = field(repr=False)
    bridge_token: str = field(repr=False)
    host: str = "127.0.0.1"
    port: int = 8787
    model: str = "gpt-realtime"
    voice: str = "marin"
    instructions: str = "日本語で、短く自然に話してください。"
    max_connections: int = 1
    session_seconds: int = 600
    idle_seconds: int = 60
    connect_seconds: int = 20
    send_seconds: int = 5

    def __post_init__(self):
        if not self.openai_api_key or self.openai_api_key.startswith("replace-"):
            raise ValueError("OPENAI_API_KEY is required")
        if len(self.bridge_token) < 32 or self.bridge_token.startswith("replace-"):
            raise ValueError("BRIDGE_TOKEN must be a random token of at least 32 characters")
        if self.openai_api_key == self.bridge_token:
            raise ValueError("BRIDGE_TOKEN must differ from OPENAI_API_KEY")
        if not 0 <= self.port <= 65535:
            raise ValueError("BRIDGE_PORT must be between 0 and 65535")
        for name in (
            "max_connections",
            "session_seconds",
            "idle_seconds",
            "connect_seconds",
            "send_seconds",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")

    @classmethod
    def from_env(cls):
        return cls(
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            bridge_token=os.environ.get("BRIDGE_TOKEN", ""),
            host=os.environ.get("BRIDGE_HOST", "127.0.0.1"),
            port=int(os.environ.get("BRIDGE_PORT", "8787")),
            model=os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime"),
            voice=os.environ.get("OPENAI_REALTIME_VOICE", "marin"),
            instructions=os.environ.get("OPENAI_REALTIME_INSTRUCTIONS", cls.instructions),
            max_connections=int(os.environ.get("BRIDGE_MAX_CONNECTIONS", "1")),
            session_seconds=int(os.environ.get("BRIDGE_SESSION_SECONDS", "600")),
            idle_seconds=int(os.environ.get("BRIDGE_IDLE_SECONDS", "60")),
        )
