from dataclasses import dataclass
from pathlib import Path
import os
from urllib.parse import urlsplit
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')

@dataclass(frozen=True)
class Settings:
    base_url: str = os.getenv('PLC_API_BASE_URL', 'http://192.168.x.x:8000').rstrip('/')
    api_key: str = os.getenv('PLC_API_KEY', '')
    timeout: float = float(os.getenv('PLC_REQUEST_TIMEOUT', '5'))
    poll_ms: int = int(os.getenv('PLC_UI_POLL_INTERVAL_MS', '1000'))
    stale_ms: int = int(os.getenv('PLC_STALE_AFTER_MS', '3000'))
    mock_mode: bool = os.getenv('PLC_MOCK_MODE', 'false').lower() == 'true'

    def __post_init__(self):
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            raise ValueError('PLC_API_BASE_URL must be an HTTP(S) origin without credentials, query or fragment')
        if self.timeout <= 0 or self.poll_ms <= 0 or self.stale_ms <= 0:
            raise ValueError('Timeout and polling intervals must be positive')
