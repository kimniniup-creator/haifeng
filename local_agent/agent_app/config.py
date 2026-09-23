import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env', override=False)

@dataclass
class Config:
    root: Path = ROOT
    data: Path = ROOT / os.getenv('DATA_DIR', 'data')
    api_key: str = os.getenv('OPENAI_API_KEY', '')
    base_url: str = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    vision_model: str = os.getenv('VISION_MODEL', 'gpt-4o-mini')
    agent_model: str = os.getenv('AGENT_MODEL', 'gpt-4o-mini')
    response_format: str = os.getenv('MODEL_RESPONSE_FORMAT', 'json_schema')
    disable_thinking: bool = os.getenv('MODEL_DISABLE_THINKING', 'false').lower() == 'true'
    luma_exe: str = os.getenv('LUMA_EXE', '')
    luma_python_script: str = os.getenv('LUMA_PYTHON_SCRIPT', '')
    luma_device: str = os.getenv('LUMA_DEVICE', 'D8:53:65:00:00:55')
    reachy_url: str = os.getenv('REACHY_API_URL', 'http://127.0.0.1:8000').rstrip('/')
    reachy_mode: str = os.getenv('REACHY_MODE', 'real')
    motion_enabled: bool = os.getenv('ROBOT_MOTION_ENABLED', 'false').lower() == 'true'
    speech_enabled: bool = os.getenv('ROBOT_SPEECH_ENABLED', 'true').lower() == 'true'
    voice: str = os.getenv('TTS_VOICE_ID', '')
    rate: int = int(os.getenv('TTS_RATE', '170'))
    agent_host: str = os.getenv('AGENT_HOST', '127.0.0.1')
    allowed_hosts: tuple[str, ...] = tuple(
        value.strip().lower()
        for value in os.getenv('AGENT_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
        if value.strip()
    )
    port: int = int(os.getenv('PORT', '8765'))
    token: str = os.getenv('BRIDGE_TOKEN', '')
    auto_memory: bool = os.getenv('AUTO_MEMORY', 'true').lower() == 'true'
    model_timeout: float = float(os.getenv('MODEL_TIMEOUT', '35'))
    capture_timeout: float = float(os.getenv('CAPTURE_TIMEOUT', '45'))
    turn_timeout: float = float(os.getenv('TURN_TIMEOUT', '150'))
    max_steps: int = int(os.getenv('MAX_STEPS', '6'))
    max_pending: int = int(os.getenv('MAX_PENDING', '3'))

    def prepare(self):
        if self.response_format not in ('json_schema', 'json_object'):
            raise ValueError('MODEL_RESPONSE_FORMAT must be json_schema or json_object')
        self.data = self.data.resolve()
        for name in ('images', 'audio', 'tmp'):
            (self.data / name).mkdir(parents=True, exist_ok=True)
        if self.reachy_mode not in ('real', 'text_only'):
            raise ValueError('REACHY_MODE must be real or text_only (no silent mock)')
        if not self.allowed_hosts:
            raise ValueError('AGENT_ALLOWED_HOSTS must not be empty')
        if self.luma_exe:
            self.luma_exe = str((self.root / self.luma_exe).resolve())
