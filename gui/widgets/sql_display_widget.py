# gui/widgets/sql_display_widget.py
"""生成的 SQL 展示区, QWidget 子类。

标题 + 只读等宽 QPlainTextEdit + 按钮行（复制 / 送入优化模式）。
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

import pyperclip


class SqlDisplayWidget(QWidget):
    """SQL 展示区: 只读编辑器 + 复制 / 送入优化模式按钮。

    Signals:
        optimize_requested(str): 用户点击"送入优化模式", 携带当前 SQL 文本
    """

    optimize_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._connect_signals()

    # ---- UI ----
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("生成的 SQL")
        f = title.font(); f.setBold(True); f.setPointSize(11); title.setFont(f)
        layout.addWidget(title)

        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setPlaceholderText("生成的 SQL 会显示在这里 ...")
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(11)
        self.editor.setFont(font)
        layout.addWidget(self.editor, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.copy_button = QPushButton("📋 复制 SQL")
        btn_row.addWidget(self.copy_button)
        self.optimize_button = QPushButton("🔍 送入优化模式")
        btn_row.addWidget(self.optimize_button)
        layout.addLayout(btn_row)

    def _connect_signals(self) -> None:
        self.copy_button.clicked.connect(self._on_copy_clicked)
        self.optimize_button.clicked.connect(self._on_optimize_clicked)

    # ---- 槽 ----
    def _on_copy_clicked(self) -> None:
        """复制 SQL 到剪贴板, 失败时改按钮文案给出反馈。"""
        try:
            pyperclip.copy(self.get_sql())
        except Exception:  # noqa: BLE001 - 剪贴板不可用时不能静默失败
            self.copy_button.setText("📋 复制失败")
            return
        self.copy_button.setText("📋 已复制")

    def _on_optimize_clicked(self) -> None:
        """发射 optimize_requested, 携带当前 SQL。"""
        self.optimize_requested.emit(self.get_sql())

    # ---- 公共 API ----
    def set_sql(self, sql: str) -> None:
        """设置展示的 SQL。"""
        self.editor.setPlainText(sql)

    def get_sql(self) -> str:
        """返回展示的 SQL 文本。"""
        return self.editor.toPlainText()

    def clear(self) -> None:
        """清空展示区。"""
        self.editor.clear()
