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
