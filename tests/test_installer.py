"""分层修复测试。"""
from sql_coach.diagnostics.checks import CheckResult
from sql_coach.diagnostics.installer import apply_auto_fixes
from sql_coach.diagnostics.report import format_results


def test_apply_auto_fixes_creates_env(tmp_path):
    env_path = tmp_path / ".env"
    results = [CheckResult("配置文件 .env", "warn", "缺失", auto_fixable=True)]
    outcomes = apply_auto_fixes(results, str(env_path))
    assert env_path.exists()
    assert any(o.applied for o in outcomes)
    assert "OPTIMIZER_MODE" in env_path.read_text(encoding="utf-8")


def test_apply_auto_fixes_skips_non_autofixable(tmp_path):
    env_path = tmp_path / ".env"
    results = [CheckResult("MySQL 连接", "fail", "连不上", fix_hint="winget ...",
                           auto_fixable=False)]
    outcomes = apply_auto_fixes(results, str(env_path))
    assert outcomes == []
    assert not env_path.exists()


def test_format_results_contains_status_and_hint():
    results = [
        CheckResult("配置文件 .env", "ok", "已找到"),
        CheckResult("MySQL 连接", "fail", "连不上", fix_hint="winget install Oracle.MySQL"),
    ]
    text = format_results(results)
    assert "配置文件 .env" in text
    assert "winget install Oracle.MySQL" in text
