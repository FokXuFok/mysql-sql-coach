"""Configuration loader for SQL Coach."""
import os
from typing import Optional

from .models import Config, DBConfig


def _get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _get_env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def load_env_file(path: str = ".env") -> None:
    """Load .env file into os.environ without overwriting existing vars."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except FileNotFoundError:
        pass


def load_config(env_path: str = ".env", mock: bool = False) -> Config:
    """Load configuration from .env file and environment variables."""
    load_env_file(env_path)
    return Config.from_env(mock=mock)