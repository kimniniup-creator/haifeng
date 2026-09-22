from dataclasses import dataclass
from pathlib import Path
import os


def _boolean(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    bridge_host: str = os.getenv("BRIDGE_HOST", "127.0.0.1")
    bridge_port: int = int(os.getenv("BRIDGE_PORT", "8088"))
    bridge_token: str = os.getenv("BRIDGE_TOKEN", "")
    data_dir: Path = Path(os.getenv("DATA_DIR", "./data"))
    reachy_host: str = os.getenv("REACHY_HOST", "127.0.0.1")
    reachy_port: int = int(os.getenv("REACHY_PORT", "8000"))
    reachy_connection_mode: str = os.getenv("REACHY_CONNECTION_MODE", "localhost_only")
    luma_mode: str = os.getenv("LUMA_MODE", "cli")
    luma_cli_path: str = os.getenv("LUMA_CLI_PATH", "")
    model_base_url: str = os.getenv("MODEL_BASE_URL", "")
    model_api_key: str = os.getenv("MODEL_API_KEY", "")
    vision_model: str = os.getenv("VISION_MODEL", "")
    tts_enabled: bool = _boolean("TTS_ENABLED")

    @property
    def database_path(self) -> Path:
        return self.data_dir / "bridge.sqlite3"

    @property
    def image_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def reachy_base_url(self) -> str:
        return f"http://{self.reachy_host}:{self.reachy_port}"


settings = Settings()
