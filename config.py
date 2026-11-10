"""Configuration and paths for the OpenDART collector."""
from dataclasses import dataclass
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent

@dataclass(frozen=True)
class Settings:
    api_key: str
    timeout: float = 30.0
    retries: int = 3
    request_interval: float = 0.25

def load_settings() -> Settings:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    key = os.getenv("OPENDART_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENDART_API_KEY가 설정되지 않았습니다. .env를 확인하세요.")
    return Settings(key, float(os.getenv("DART_TIMEOUT", "30")), int(os.getenv("DART_RETRIES", "3")), float(os.getenv("DART_REQUEST_INTERVAL", "0.25")))
