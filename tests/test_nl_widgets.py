# tests/test_nl_widgets.py
"""Task 14: NL 模式三个 GUI 组件的测试。"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from gui.widgets.nl_input_widget import NlInputWidget
from gui.widgets.sql_display_widget import SqlDisplayWidget
from gui.widgets.query_result_widget import QueryResultWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ---------------- NlInputWidget ----------------

def test_nl_input_constructs(app):
    """组件可独立构造。"""
    w = NlInputWidget()
    assert w.get_text() == ""
    assert w.editor.isReadOnly() is False
    assert w.generate_button.isEnabled() is True


def test_nl_input_placeholder_mentions_natural_language(app):
    """placeholder 含自然语言描述与示例提示。"""
    w = NlInputWidget()
    ph = w.editor.placeholderText()
    assert "用自然语言描述你想查询的数据" in ph
    assert "查询销售额最高的10个客户" in ph


def test_nl_input_get_and_clear(app):
    """get_text() 返回文本, clear() 清空。"""
    w = NlInputWidget()
    w.editor.setPlainText("查询10条订单")
    assert w.get_text() == "查询10条订单"
    w.clear()
    assert w.get_text() == ""


def test_nl_input_set_readonly(app):
    """set_readonly(True) 后编辑器只读且按钮禁用。"""
    w = NlInputWidget()
    w.set_readonly(True)
    assert w.editor.isReadOnly() is True
    assert w.generate_button.isEnabled() is False
    w.set_readonly(False)
    assert w.editor.isReadOnly() is False
    assert w.generate_button.isEnabled() is True


def test_nl_input_button_emits(app):
    """点击按钮发射 generate_requested。"""
    w = NlInputWidget()
    w.editor.setPlainText("查询10条订单")
    captured = []
    w.generate_requested.connect(captured.append)
    w.generate_button.click()
    assert captured == ["查询10条订单"]


def test_nl_input_empty_does_not_emit(app):
    """空文本不发射信号。"""
    w = NlInputWidget()
    captured = []
    w.generate_requested.connect(captured.append)
    w.generate_button.click()
    assert captured == []


def test_nl_input_ctrl_enter_emits(app, qtbot):
    """Ctrl+Enter 触发 generate_requested。"""
    w = NlInputWidget()
    qtbot.addWidget(w)
    w.editor.setPlainText("查询10条订单")
    captured = []
    w.generate_requested.connect(captured.append)
    qtbot.keyClick(w.editor, Qt.Key_Return, Qt.ControlModifier)
    assert captured == ["查询10条订单"]


# ---------------- SqlDisplayWidget ----------------

def test_sql_display_constructs(app):
    """组件可独立构造, 初始为空且只读。"""
    w = SqlDisplayWidget()
    assert w.get_sql() == ""
    assert w.editor.isReadOnly() is True


def test_sql_display_set_sql(app):
    """set_sql 生效。"""
    w = SqlDisplayWidget()
    w.set_sql("SELECT * FROM orders LIMIT 10;")
    assert w.get_sql() == "SELECT * FROM orders LIMIT 10;"


def test_sql_display_optimize_emits(app):
    """点击送入优化模式发射 optimize_requested。"""
    w = SqlDisplayWidget()
    w.set_sql("SELECT 1;")
    captured = []
    w.optimize_requested.connect(captured.append)
    w.optimize_button.click()
    assert captured == ["SELECT 1;"]


def test_sql_display_copy_success(app, monkeypatch):
    """复制成功调用 pyperclip.copy。"""
    import gui.widgets.sql_display_widget as mod

    copied = []
    monkeypatch.setattr(mod.pyperclip, "copy", lambda t: copied.append(t))
    w = SqlDisplayWidget()
    w.set_sql("SELECT 1;")
    w.copy_button.click()
    assert copied == ["SELECT 1;"]


def test_sql_display_copy_failure_feedback(app, monkeypatch):
    """复制失败不能静默, 按钮文案给出反馈。"""
    import gui.widgets.sql_display_widget as mod

    def _boom(text):
        raise RuntimeError("no clipboard")

    monkeypatch.setattr(mod.pyperclip, "copy", _boom)
    w = SqlDisplayWidget()
    w.set_sql("SELECT 1;")
    w.copy_button.click()
    assert "失败" in w.copy_button.text()


# ---------------- QueryResultWidget ----------------

def test_query_result_constructs(app):
    """组件可独立构造, 初始显示占位提示。"""
    w = QueryResultWidget()
    assert w.table.rowCount() == 0
    assert w._stack.currentIndex() == 0


def test_query_result_set_result(app):
    """set_result 填充表格并更新标题行数。"""
    w = QueryResultWidget()
    w.set_result(["id", "name"], [(1, "张三"), (2, "李四")])
    assert w.table.rowCount() == 2
    assert w.table.columnCount() == 2
    assert w.table.item(0, 1).text() == "张三"
    assert "2 行" in w.title_label.text()
    assert w._stack.currentIndex() == 1


def test_query_result_row_limit(app):
    """超过 1000 行截断并在标题提示。"""
    w = QueryResultWidget()
    rows = [(i,) for i in range(1005)]
    w.set_result(["id"], rows)
    assert w.table.rowCount() == 1000
    assert "仅显示前 1000 行" in w.title_label.text()


def test_query_result_empty_shows_placeholder(app):
    """空结果时显示占位提示。"""
    w = QueryResultWidget()
    w.set_result([], [])
    assert w._stack.currentIndex() == 0
    assert w.table.rowCount() == 0


def test_query_result_columns_without_rows_shows_placeholder(app):
    """有列名但无行数据同样显示占位。"""
    w = QueryResultWidget()
    w.set_result(["id"], [])
    assert w._stack.currentIndex() == 0
