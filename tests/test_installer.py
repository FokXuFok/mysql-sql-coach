"""分层修复测试。"""
from sql_coach.diagnostics.checks import CheckResult
from sql_coach.diagnostics.installer import apply_auto_fixes
from sql_coach.diagnostics.report import format_results


def test_apply_auto_fixes_creates_env(tmp_path):
    env_path = tmp_path / ".env"
    results = [CheckResult("配置文件 .env", "warn", "缺失", auto_fixable=True, key="env_file")]
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


def test_apply_auto_fixes_outcome_carries_key(tmp_path):
    """M6: FixOutcome 应带机器可读 key，供上层按 key 匹配而非展示名。"""
    env_path = tmp_path / ".env"
    results = [CheckResult("配置文件 .env", "warn", "缺失",
                           auto_fixable=True, key="env_file")]
    outcomes = apply_auto_fixes(results, str(env_path))
    assert len(outcomes) == 1
    assert outcomes[0].key == "env_file"


def test_create_env_file_skips_when_exists(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("EXISTS=1\n", encoding="utf-8")
    results = [CheckResult("配置文件 .env", "warn", "缺失",
                           auto_fixable=True, key="env_file")]
    outcomes = apply_auto_fixes(results, str(env_path))
    assert outcomes[0].applied is False
    assert outcomes[0].key == "env_file"


def test_format_results_contains_status_and_hint():
    results = [
        CheckResult("配置文件 .env", "ok", "已找到"),
        CheckResult("MySQL 连接", "fail", "连不上", fix_hint="winget install Oracle.MySQL"),
    ]
    text = format_results(results)
    assert "配置文件 .env" in text
    assert "winget install Oracle.MySQL" in text
