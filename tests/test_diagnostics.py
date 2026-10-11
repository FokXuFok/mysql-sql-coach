"""启动自检测试。"""
from sql_coach.models import Config, DBConfig
from sql_coach.diagnostics.checks import (
    check_env_file, check_ai, check_runtime, run_all, CheckResult,
)


def make_config(model="deepseek", key="sk-real", mock=False):
    return Config(db=DBConfig(host="localhost", port=3306, user="root", password="", database="test"),
                  model=model, deepseek_api_key=key, openai_api_key="",
                  ollama_url="http://localhost:11434", benchmark_runs=3, mock=mock)


def test_check_env_file_missing(tmp_path):
    missing = str(tmp_path / "nope.env")
    r = check_env_file(missing)
    assert r.status == "warn"
    assert r.auto_fixable is True


def test_check_env_file_exists(tmp_path):
    p = tmp_path / ".env"
    p.write_text("AI_MODEL=deepseek\n", encoding="utf-8")
    assert check_env_file(str(p)).status == "ok"


def test_check_ai_missing_key():
    r = check_ai(make_config(key=""))
    assert r.status == "fail"
    assert "API Key" in r.message or "Key" in r.message


def test_check_ai_placeholder_key():
    r = check_ai(make_config(key="sk-xxx"))
    assert r.status == "fail"


def test_check_ai_ok():
    assert check_ai(make_config(key="sk-abcdef123456")).status == "ok"


def test_check_ai_ollama_ok():
    assert check_ai(make_config(model="ollama")).status == "ok"


def test_check_ai_mock_mode():
    assert check_ai(make_config(mock=True)).status == "warn"


def test_check_runtime_ok():
    assert check_runtime().status == "ok"


def test_run_all_returns_four_results(tmp_path):
    results = run_all(make_config(mock=True), str(tmp_path / ".env"))
    assert len(results) == 4
    assert all(isinstance(r, CheckResult) for r in results)
