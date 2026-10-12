"""自检对话框测试。"""
from PySide6.QtWidgets import QApplication, QLabel

from sql_coach.diagnostics.checks import CheckResult
from gui.widgets.diagnostics_dialog import DiagnosticsDialog


def _app():
    return QApplication.instance() or QApplication([])


def test_dialog_lists_results():
    _app()
    results = [
        CheckResult("配置文件 .env", "ok", "已找到"),
        CheckResult("MySQL 连接", "fail", "连不上", fix_hint="winget install Oracle.MySQL"),
    ]
    dlg = DiagnosticsDialog(results, env_path=".env")
    texts = " ".join(w.text() for w in dlg.findChildren(QLabel))
    assert "MySQL 连接" in texts
    assert "winget install Oracle.MySQL" in texts


def test_dialog_autofix_button_only_when_needed():
    _app()
    no_fix = DiagnosticsDialog([CheckResult("运行环境", "ok", "ok")], env_path=".env")
    assert no_fix.fix_button.isEnabled() is False
    with_fix = DiagnosticsDialog(
        [CheckResult("配置文件 .env", "warn", "缺失", auto_fixable=True)], env_path=".env")
    assert with_fix.fix_button.isEnabled() is True


def test_dialog_skip_writes_marker(tmp_path, monkeypatch):
    _app()
    from gui.widgets import diagnostics_dialog as mod
    monkeypatch.setattr(mod, "SKIP_MARKER", tmp_path / ".skip_diagnostics")
    dlg = DiagnosticsDialog([CheckResult("运行环境", "ok", "ok")], env_path=".env")
    dlg.dont_ask.setChecked(True)
    dlg._on_skip()
    assert (tmp_path / ".skip_diagnostics").exists()


def test_copy_failure_shows_feedback(monkeypatch):
    """M7: 复制失败时按钮给出可见反馈。"""
    _app()
    from gui.widgets import diagnostics_dialog as mod
    monkeypatch.setattr(mod, "copy_hint", lambda hint: False)
    dlg = DiagnosticsDialog(
        [CheckResult("MySQL 连接", "fail", "连不上",
                     fix_hint="winget install Oracle.MySQL")],
        env_path=".env",
    )
    dlg._on_copy()
    assert "失败" in dlg.copy_button.text()


def test_fix_without_config_respects_outcome(monkeypatch):
    """M8: config 为 None 时，只有真正 applied 的项才标为 ok。"""
    _app()
    from gui.widgets import diagnostics_dialog as mod
    from sql_coach.diagnostics.installer import FixOutcome

    monkeypatch.setattr(
        mod, "apply_auto_fixes",
        lambda results, env_path: [FixOutcome("配置文件 .env", False, "生成失败: 无权限",
                                              key="env_file")],
    )
    dlg = DiagnosticsDialog(
        [CheckResult("配置文件 .env", "warn", "缺失",
                     auto_fixable=True, key="env_file")],
        env_path=".env", config=None,
    )
    dlg._on_fix()
    assert dlg.results[0].status != "ok"


def test_fix_without_config_applied_marks_ok(monkeypatch):
    """M8: applied=True 的项才标为 ok。"""
    _app()
    from gui.widgets import diagnostics_dialog as mod
    from sql_coach.diagnostics.installer import FixOutcome

    monkeypatch.setattr(
        mod, "apply_auto_fixes",
        lambda results, env_path: [FixOutcome("配置文件 .env", True, "已生成模板",
                                              key="env_file")],
    )
    dlg = DiagnosticsDialog(
        [CheckResult("配置文件 .env", "warn", "缺失",
                     auto_fixable=True, key="env_file")],
        env_path=".env", config=None,
    )
    dlg._on_fix()
    assert dlg.results[0].status == "ok"


def test_fix_matches_by_key_not_display_name(monkeypatch):
    """M6: 即使展示名不同，只要 key 匹配就应标为已修复。"""
    _app()
    from gui.widgets import diagnostics_dialog as mod
    from sql_coach.diagnostics.installer import FixOutcome

    monkeypatch.setattr(
        mod, "apply_auto_fixes",
        lambda results, env_path: [FixOutcome("重命名后的展示名", True, "已生成模板",
                                              key="env_file")],
    )
    dlg = DiagnosticsDialog(
        [CheckResult("配置文件 .env", "warn", "缺失",
                     auto_fixable=True, key="env_file")],
        env_path=".env", config=None,
    )
    dlg._on_fix()
    assert dlg.results[0].status == "ok"
