# gui/widgets/query_result_widget.py
"""查询结果表格, QWidget 子类。

标题显示行数 + QTableWidget; 超过行数上限时截断并在标题提示;
空结果时显示占位提示。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


class QueryResultWidget(QWidget):
    """查询结果表格: 标题(行数) + QTableWidget, 上限 1000 行。"""

    MAX_ROWS = 1000

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    # ---- UI ----
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.title_label = QLabel("查询结果")
        f = self.title_label.font()
        f.setBold(True); f.setPointSize(11)
        self.title_label.setFont(f)
        layout.addWidget(self.title_label)

        # 占位 / 表格 二选一
        self._stack = QStackedWidget()
        placeholder = QLabel("暂无查询结果，请先在左侧生成 SQL")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color: #888; font-size: 13px; padding: 40px;")
        self.placeholder = placeholder

        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)

        self._stack.addWidget(placeholder)  # index 0
        self._stack.addWidget(self.table)   # index 1
        self._stack.setCurrentIndex(0)
        layout.addWidget(self._stack, 1)

    # ---- 公共 API ----
    def set_result(self, columns, rows) -> None:
        """填充查询结果。

        Args:
            columns: 列名列表。
            rows: 行数据列表, 超过 ``MAX_ROWS`` 时仅展示前 ``MAX_ROWS`` 行。
        """
        columns = list(columns or [])
        rows = list(rows or [])

        if not rows:
            self.title_label.setText("查询结果")
            self.table.clear()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self._stack.setCurrentIndex(0)
            return

        truncated = len(rows) > self.MAX_ROWS
        shown = rows[: self.MAX_ROWS]

        if truncated:
            self.title_label.setText(
                f"查询结果（{len(rows)} 行，仅显示前 {self.MAX_ROWS} 行）")
        else:
            self.title_label.setText(f"查询结果（{len(rows)} 行）")

        # 列名缺失时用序号占位, 避免列数与数据不匹配
        if not columns:
            width = len(shown[0]) if shown else 0
            columns = [f"col{i + 1}" for i in range(width)]

        self.table.clear()
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels([str(c) for c in columns])
        self.table.setRowCount(len(shown))

        for r, row in enumerate(shown):
            for c in range(len(columns)):
                value = row[c] if c < len(row) else ""
                item = QTableWidgetItem("" if value is None else str(value))
                self.table.setItem(r, c, item)

        self._stack.setCurrentIndex(1)

    def clear(self) -> None:
        """清空结果, 回到占位提示。"""
        self.set_result([], [])
