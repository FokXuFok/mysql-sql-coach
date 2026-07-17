# gui/widgets/sql_input.py
"""SQL 输入区, QWidget 子类。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)


class SqlInputWidget(QWidget):
    """SQL 输入区: QPlainTextEdit + 分析按钮。

    Signals:
        analyze_requested(str): 用户点击分析按钮或 Ctrl+Enter, 携带 SQL 文本
    """

    analyze_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._connect_signals()

    # ---- UI ----
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 标题
        title = QLabel("SQL 输入")
        f = title.font(); f.setBold(True); f.setPointSize(11); title.setFont(f)
        layout.addWidget(title)

        # 编辑器
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("在此输入 SQL 语句 ...")
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(11)
        self.editor.setFont(mono)
        # Tab 替换为 4 空格
        self.editor.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        layout.addWidget(self.editor, 1)

        # 底部按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        hint = QLabel("Ctrl+Enter 分析")
        hint.setStyleSheet("color: #888; padding-right: 8px;")
        btn_row.addWidget(hint)
        self.analyze_button = QPushButton("🔍 分析")
        self.analyze_button.setDefault(True)
        btn_row.addWidget(self.analyze_button)
        layout.addLayout(btn_row)

    def _connect_signals(self) -> None:
        """绑定信号。"""
        self.analyze_button.clicked.connect(self._on_analyze_clicked)
        # Ctrl+Enter 快捷键
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self._on_analyze_clicked)

    def _on_analyze_clicked(self) -> None:
        """点击分析: 取 SQL 文本, 非空则发射信号。"""
        sql = self.get_sql()
        if sql.strip():
            self.analyze_requested.emit(sql)

    # ---- 公共 API ----
    def get_sql(self) -> str:
        """返回输入框的 SQL 文本。"""
        return self.editor.toPlainText()

    def set_readonly(self, readonly: bool) -> None:
        """设置只读状态 (分析时禁用, 完成后恢复)。"""
        self.editor.setReadOnly(readonly)
        self.analyze_button.setEnabled(not readonly)

    def clear(self) -> None:
        """清空输入框。"""
        self.editor.clear()
