# tests/test_sql_input.py
"""SqlInputWidget 测试。"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from gui.widgets.sql_input import SqlInputWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_get_sql_returns_text(app):
    """get_sql() 返回输入框文本。"""
    w = SqlInputWidget()
    w.editor.setPlainText("SELECT 1")
    assert w.get_sql() == "SELECT 1"


def test_clear_empties_editor(app):
    """clear() 清空输入框。"""
    w = SqlInputWidget()
    w.editor.setPlainText("SELECT 1")
    w.clear()
    assert w.get_sql() == ""


def test_set_readonly_disables_editor(app):
    """set_readonly(True) 后输入框只读。"""
    w = SqlInputWidget()
    w.set_readonly(True)
    assert w.editor.isReadOnly() is True
    # 分析按钮变灰
    assert w.analyze_button.isEnabled() is False
    w.set_readonly(False)
    assert w.editor.isReadOnly() is False
    assert w.analyze_button.isEnabled() is True


def test_analyze_button_emits_signal(app):
    """点击分析按钮发射 analyze_requested 信号。"""
    w = SqlInputWidget()
    w.editor.setPlainText("SELECT 1")
    captured = []
    w.analyze_requested.connect(lambda sql: captured.append(sql))
    w.analyze_button.click()
    assert captured == ["SELECT 1"]


def test_empty_sql_does_not_emit(app):
    """空 SQL 不发射信号。"""
    w = SqlInputWidget()
    captured = []
    w.analyze_requested.connect(lambda sql: captured.append(sql))
    w.analyze_button.click()
    assert captured == []
