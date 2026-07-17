# tests/test_explain_table.py
"""ExplainTableWidget 冒烟测试。"""
import pytest
from PySide6.QtWidgets import QApplication

from sql_coach.models import ExplainRow, ExplainResult
from gui.widgets.explain_table import ExplainTableWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_set_explain_populates_rows(app):
    """填充 EXPLAIN 数据后表格行数正确。"""
    widget = ExplainTableWidget()
    explain = ExplainResult(
        rows=[
            ExplainRow(
                id=1, select_type="SIMPLE", table="users",
                type="ALL", key=None, rows=1000, extra="Using where",
            ),
            ExplainRow(
                id=2, select_type="SIMPLE", table="orders",
                type="ref", key="idx_uid", rows=10, extra="",
            ),
        ],
        is_full_scan=True,
        missing_indexes=["users"],
        problems=["全表扫描"],
    )
    widget.set_explain(explain)
    assert widget.rowCount() == 2
    assert widget.columnCount() == 6


def test_set_explain_none_clears(app):
    """传 None 清空表格。"""
    widget = ExplainTableWidget()
    widget.set_explain(None)
    assert widget.rowCount() == 0
