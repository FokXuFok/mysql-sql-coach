"""Configuration loader for SQL Coach."""
import os
from typing import Optional

from .models import Config, DBConfig

ENV_TEMPLATE = """# MySQL 连接
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=test

# AI 模型: deepseek / openai / ollama
AI_MODEL=deepseek

# DeepSeek
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# OpenAI
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1

# Ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b

# 优化器分流: auto / local / ai
OPTIMIZER_MODE=auto
# 复杂度阈值（>= 该值走 AI）
COMPLEXITY_THRESHOLD=8
# 是否实测索引收益（会临时建索引再回滚，默认关闭）
MEASURE_INDEX=false

# 通用
BENCHMARK_RUNS=3
LOG_LEVEL=INFO
"""


def _get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _get_env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def _get_env_bool(key: str, default: bool = False) -> bool:
    """读取布尔环境变量，识别 1/true/yes/on（大小写不敏感）。"""
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def load_env_file(path: str = ".env", override: bool = False) -> None:
    """Load .env file into os.environ.

    Args:
        override: True 时用 .env 的值覆盖已存在的环境变量。设置对话框把配置写回
            .env 后需要重新读取才能生效，此时必须 override=True——否则会被
            "只填新键、不覆盖旧值"的逻辑挡住，表现为"设置里改了要重启才生效"。
            默认 False，保持启动时不覆盖真实环境变量的既有行为。
    """
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
                if key and (override or key not in os.environ):
                    os.environ[key] = value
    except FileNotFoundError:
        pass


def load_config(
    env_path: str = ".env",
    mock: bool = False,
    override_env: bool = False,
) -> Config:
    """Load configuration from .env file and environment variables.

    Args:
        override_env: True 时 .env 的值覆盖已有环境变量，用于配置保存后重载，
            使新设置立即生效而无需重启程序。
    """
    load_env_file(env_path, override=override_env)
    return Config.from_env(mock=mock)