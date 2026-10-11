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
