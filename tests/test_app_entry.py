# tests/test_app_entry.py
"""GUI 入口冒烟测试。"""
import pytest
from PySide6.QtWidgets import QApplication

from gui import app as app_module


def test_run_creates_application_and_window(monkeypatch):
    """run() 创建 QApplication 并显示主窗口, exec 被立刻退出。"""
    # 拦截 exec 防止阻塞
    called = {}
    def fake_exec(self):
        called["exec"] = True
        return 0
    monkeypatch.setattr(QApplication, "exec", fake_exec)

    # 不调用 sys.exit
    def fake_exit(code=0):
        called["exit"] = code
    monkeypatch.setattr("sys.exit", fake_exit)

    # 拦截 MainWindow.show 防止真显示
    monkeypatch.setattr("gui.main_window.MainWindow.show", lambda self: None)

    app_module.run()

    assert called.get("exec") is True
    assert "exit" in called
