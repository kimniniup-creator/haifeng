from dataclasses import dataclass
from pathlib import Path
import json
import os
import secrets
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv(override=False)


def _boolean(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def _valid_model_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not parsed.username and not parsed.password


@dataclass
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
    model_settings_managed: bool = False
    tts_enabled: bool = _boolean("TTS_ENABLED")

    @property
    def database_path(self) -> Path:
        return self.data_dir / "bridge.sqlite3"

    @property
    def image_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def settings_path(self) -> Path:
        return self.data_dir / "settings.json"

    @property
    def reachy_base_url(self) -> str:
        return f"http://{self.reachy_host}:{self.reachy_port}"

    def bootstrap(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        saved: dict = {}
        try:
            if self.settings_path.exists():
                saved = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            saved = {}
        self.model_settings_managed = bool(saved.get("model_settings_managed"))
        for key in ("model_base_url", "model_api_key", "vision_model"):
            if (self.model_settings_managed or not getattr(self, key)) and isinstance(saved.get(key), str):
                setattr(self, key, saved[key])
        if not self.bridge_token or self.bridge_token == "local-development-token":
            token = saved.get("bridge_token")
            self.bridge_token = token if isinstance(token, str) and len(token) >= 32 else secrets.token_urlsafe(32)
        self._persist(saved)

    def _persist(self, previous: dict | None = None) -> None:
        value = dict(previous or {})
        value.update({"bridge_token": self.bridge_token, "model_base_url": self.model_base_url,
                      "model_api_key": self.model_api_key, "vision_model": self.vision_model,
                      "model_settings_managed": self.model_settings_managed})
        temporary = self.settings_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.settings_path)

    def update_model(self, *, base_url: str, api_key: str | None, model: str) -> None:
        base_url = base_url.strip().rstrip("/")
        if not _valid_model_url(base_url):
            raise ValueError("MODEL_BASE_URL_INVALID")
        if not model.strip():
            raise ValueError("VISION_MODEL_REQUIRED")
        self.model_base_url, self.vision_model = base_url, model.strip()
        if api_key is not None and api_key.strip():
            self.model_api_key = api_key.strip()
        self.model_settings_managed = True
        self._persist()

    def model_status(self) -> dict:
        return {"configured": bool(self.model_base_url and self.model_api_key and self.vision_model),
                "base_url": self.model_base_url or None, "vision_model": self.vision_model or None,
                "api_key_configured": bool(self.model_api_key)}


settings = Settings()
