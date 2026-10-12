"""启动自检测试。"""
from sql_coach.models import Config, DBConfig
from sql_coach.diagnostics.checks import (
    check_env_file, check_mysql, check_ai, check_runtime, run_all, CheckResult,
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


def test_check_runtime_missing_dep_warns(monkeypatch):
    """源码模式下缺少 GUI/绘图依赖时应降级为 warn 并给出 pip 指引。"""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in ("PySide6", "matplotlib"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    r = check_runtime()
    assert r.status == "warn"
    assert "PySide6" in r.message and "matplotlib" in r.message
    assert r.fix_hint == "pip install PySide6 matplotlib"


def test_check_ai_ollama_probe_disabled_by_default():
    """默认不联网，仍应返回 ok。"""
    assert check_ai(make_config(model="ollama")).status == "ok"


def test_check_ai_ollama_probe_failure(monkeypatch):
    import httpx

    def boom(*args, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "get", boom)
    r = check_ai(make_config(model="ollama"), probe=True)
    assert r.status == "fail"
    assert "无法连接 Ollama" in r.message
    assert r.fix_hint == "确认已执行 ollama serve"


def test_run_all_probe_passthrough(monkeypatch):
    import httpx
    from sql_coach.diagnostics import checks

    monkeypatch.setattr(checks, "check_mysql",
                        lambda cfg: CheckResult("MySQL 连接", "warn", "skip", key="mysql"))

    def boom(*args, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "get", boom)
    results = run_all(make_config(model="ollama"), ".env", probe=True)
    ai = next(r for r in results if r.key == "ai")
    assert ai.status == "fail"


def test_check_results_have_machine_readable_key(tmp_path):
    p = tmp_path / ".env"
    p.write_text("X=1\n", encoding="utf-8")
    assert check_env_file(str(p)).key == "env_file"
    assert check_mysql(make_config(mock=True)).key == "mysql"
    assert check_ai(make_config(mock=True)).key == "ai"
    assert check_runtime().key == "runtime"


def test_run_all_returns_four_results(tmp_path):
    results = run_all(make_config(mock=True), str(tmp_path / ".env"))
    assert len(results) == 4
    assert all(isinstance(r, CheckResult) for r in results)
