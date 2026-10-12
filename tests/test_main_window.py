# tests/test_main_window.py
"""MainWindow 冒烟测试。"""
import pytest
from PySide6.QtWidgets import QApplication

from sql_coach.models import Config, DBConfig
from gui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_config():
    return Config(
        db=DBConfig(host="localhost", port=3306, user="root", password="", database="test"),
        model="deepseek",
        deepseek_api_key="",
        openai_api_key="",
        ollama_url="http://localhost:11434",
        benchmark_runs=3,
        mock=True,
    )


def test_main_window_constructs(app):
    """主窗口能正常构造。"""
    win = MainWindow(config=make_config())
    assert win.windowTitle() == "SQL Coach"
    assert win.sql_input is not None
    assert win.report_view is not None
    assert win.status_bar is not None


def test_clear_action_resets_ui(app):
    """Ctrl+L / 清空按钮重置 UI。"""
    win = MainWindow(config=make_config())
    win.sql_input.editor.setPlainText("SELECT 1")
    win._on_clear()
    assert win.sql_input.get_sql() == ""


def test_analyze_with_empty_sql_does_nothing(app):
    """空 SQL 不触发分析。"""
    win = MainWindow(config=make_config())
    win._on_analyze()  # 输入框为空
    assert win.worker is None


def make_real_config():
    """非 mock 配置: 用于触发 _check_db_connection 的真实分支。"""
    cfg = make_config()
    cfg.mock = False
    return cfg


def test_db_failure_uses_non_modal_dialog(app, monkeypatch):
    """I2: 连库失败时不得弹模态框（模态会阻塞启动 / CI 挂起）。"""
    from PySide6.QtWidgets import QMessageBox
    from sql_coach import coach as coach_mod

    # 让数据库连接失败
    monkeypatch.setattr(coach_mod.SQLCoach, "connect", lambda self: False)
    # 避免测试在用户主目录创建缓存文件
    monkeypatch.setattr(coach_mod, "AnalysisCache", lambda *a, **k: None)

    # 任何模态路径被调用都应立即报错（证明没有进入嵌套事件循环）
    def _boom(*args, **kwargs):
        raise AssertionError("连库失败时走了模态弹窗路径")

    monkeypatch.setattr(QMessageBox, "exec", _boom)
    monkeypatch.setattr(QMessageBox, "warning", _boom)

    # 拦截真正的 show(): 非模态展示在无事件循环的测试进程里会留下原生窗口,
    # 导致解释器退出挂起。仅记录被调用, 以证明走的是非模态路径。
    shown = {}
    monkeypatch.setattr(QMessageBox, "show", lambda self: shown.__setitem__("called", True))

    win = MainWindow(config=make_real_config())
    assert shown.get("called") is True
    assert "模拟模式" in win.status_bar.currentMessage()
