# tests/test_history_dialog.py
"""HistoryDialog 测试。"""
import pytest
from PySide6.QtWidgets import QApplication

from gui.storage.history_store import HistoryStore
from gui.widgets.history_dialog import HistoryDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_dialog_populates_list(tmp_path, app):
    """对话框打开时填充历史列表。"""
    store = HistoryStore(path=str(tmp_path / "h.json"))
    # 写两条假数据
    store._write([
        {
            "id": "abc123", "sql": "SELECT 1",
            "timestamp": "2026-07-13T14:30",
            "optimized_sql": "SELECT 1;",
            "speedup": 25.0,
            "ai_time_ms": 100.0,
            "problem_count": 0,
        },
        {
            "id": "def456", "sql": "SELECT 2",
            "timestamp": "2026-07-13T15:30",
            "optimized_sql": "SELECT 2;",
            "speedup": None,
            "ai_time_ms": 50.0,
            "problem_count": 1,
        },
    ])
    dialog = HistoryDialog(store=store)
    assert dialog.list_widget.count() == 2


def test_double_click_emits_sql_signal(tmp_path, app):
    """双击列表项发射 sql_selected 信号。"""
    store = HistoryStore(path=str(tmp_path / "h.json"))
    store._write([{
        "id": "abc123", "sql": "SELECT 1",
        "timestamp": "2026-07-13T14:30",
        "optimized_sql": "SELECT 1;",
        "speedup": 25.0,
        "ai_time_ms": 100.0,
        "problem_count": 0,
    }])
    dialog = HistoryDialog(store=store)

    captured = []
    dialog.sql_selected.connect(lambda sql: captured.append(sql))

    # 模拟双击第 0 项
    item = dialog.list_widget.item(0)
    dialog.list_widget.setCurrentItem(item)
    dialog._on_item_double_clicked(dialog.list_widget.item(0))

    assert captured == ["SELECT 1"]


def test_delete_button_removes_record(tmp_path, app):
    """删除按钮移除选中记录。"""
    store = HistoryStore(path=str(tmp_path / "h.json"))
    store._write([{
        "id": "abc123", "sql": "SELECT 1",
        "timestamp": "2026-07-13T14:30",
        "optimized_sql": "SELECT 1;",
        "speedup": 25.0,
        "ai_time_ms": 100.0,
        "problem_count": 0,
    }])
    dialog = HistoryDialog(store=store)
    dialog.list_widget.setCurrentRow(0)
    dialog._on_delete_clicked()
    assert dialog.list_widget.count() == 0
    assert store.list() == []


def test_clear_button_empties_all(tmp_path, app):
    """清空按钮清空全部历史。"""
    store = HistoryStore(path=str(tmp_path / "h.json"))
    store._write([{
        "id": "abc123", "sql": "SELECT 1",
        "timestamp": "2026-07-13T14:30",
        "optimized_sql": "SELECT 1;",
        "speedup": 25.0,
        "ai_time_ms": 100.0,
        "problem_count": 0,
    }])
    dialog = HistoryDialog(store=store)
    dialog._on_clear_clicked()
    assert dialog.list_widget.count() == 0
    assert store.list() == []
