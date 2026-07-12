# tests/test_config.py
import os
from sql_coach.config import Config, DBConfig


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_USER", "root")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    monkeypatch.setenv("DB_NAME", "testdb")
    monkeypatch.setenv("AI_MODEL", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-xxx")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    monkeypatch.setenv("BENCHMARK_RUNS", "5")

    config = Config.from_env()

    assert config.db.host == "localhost"
    assert config.db.port == 3306
    assert config.db.user == "root"
    assert config.db.password == "secret"
    assert config.db.database == "testdb"
    assert config.model == "deepseek"
    assert config.deepseek_api_key == "sk-xxx"
    assert config.benchmark_runs == 5
    assert config.mock is False


def test_config_mock_flag(monkeypatch):
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_USER", "root")
    monkeypatch.setenv("DB_PASSWORD", "x")
    monkeypatch.setenv("DB_NAME", "test")
    monkeypatch.setenv("AI_MODEL", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    monkeypatch.setenv("BENCHMARK_RUNS", "3")

    config = Config.from_env(mock=True)
    assert config.mock is True