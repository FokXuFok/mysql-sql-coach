# gui/widgets/explain_table.py
"""EXPLAIN 结果表格, QTableWidget 子类。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from sql_coach.models import ExplainResult

# 列定义: (字段, 标题, 宽度)
_COLUMNS = [
    ("id", "id", 50),
    ("table", "table", 120),
    ("type", "type", 80),
    ("key", "key", 120),
    ("rows", "rows", 100),
    ("extra", "extra", 280),
]

# type=ALL 的红色背景
_FULL_SCAN_COLOR = QColor(253, 226, 224)  # 浅红 #fde2e0


class ExplainTableWidget(QTableWidget):
    """展示 ExplainResult 的表格, 全表扫描行标红。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._setup_columns()
        self.setEditTriggers(QTableWidget.NoEditTriggers)  # 只读
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)

    def _setup_columns(self) -> None:
        """初始化列。"""
        self.setColumnCount(len(_COLUMNS))
        for col_idx, (_, header, width) in enumerate(_COLUMNS):
            item = QTableWidgetItem(header)
            self.setHorizontalHeaderItem(col_idx, item)
            self.setColumnWidth(col_idx, width)

    def set_explain(self, explain: Optional[ExplainResult]) -> None:
        """填充 EXPLAIN 数据, 传 None 清空。"""
        # 没有数据
        if explain is None or not explain.rows:
            self.setRowCount(0)
            return

        self.setRowCount(len(explain.rows))
        for row_idx, row in enumerate(explain.rows):
            values = [
                str(row.id),
                row.table,
                row.type,
                row.key or "NULL",
                f"{row.rows:,}",
                row.extra or "",
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                # type=ALL 整行标红
                if row.type == "ALL":
                    item.setBackground(_FULL_SCAN_COLOR)
                if col_idx == 2:  # type 列加粗
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self.setItem(row_idx, col_idx, item)
