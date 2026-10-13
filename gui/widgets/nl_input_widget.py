# gui/widgets/nl_input_widget.py
"""自然语言输入区, QWidget 子类。

与 SqlInputWidget 结构对称: 标题 + QPlainTextEdit + 生成按钮,
额外支持 Ctrl+Enter 快捷键触发。
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

_PLACEHOLDER = (
    "用自然语言描述你想查询的数据 ...\n"
    "例如：查询销售额最高的10个客户"
)


class NlInputWidget(QWidget):
    """自然语言输入区: QPlainTextEdit + 生成 SQL 按钮。

    Signals:
        generate_requested(str): 用户点击生成按钮或 Ctrl+Enter, 携带自然语言文本
    """

    generate_requested = Signal(str)

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
        title = QLabel("自然语言查询")
        f = title.font(); f.setBold(True); f.setPointSize(11); title.setFont(f)
        layout.addWidget(title)

        # 编辑器
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(_PLACEHOLDER)
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(11)
        self.editor.setFont(font)
        layout.addWidget(self.editor, 1)

        # 底部按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        hint = QLabel("Ctrl+Enter 生成")
        hint.setStyleSheet("color: #888; padding-right: 8px;")
        btn_row.addWidget(hint)
        self.generate_button = QPushButton("✨ 生成 SQL")
        self.generate_button.setDefault(True)
        btn_row.addWidget(self.generate_button)
        layout.addLayout(btn_row)

    def _connect_signals(self) -> None:
        """绑定信号 + Ctrl+Enter。

        Ctrl+Enter 用事件过滤器实现（而非 QShortcut）: 焦点在 ``editor`` 上,
        事件过滤器直接收到按键, 不依赖窗口是否处于激活状态, 便于测试。
        """
        self.generate_button.clicked.connect(self._on_generate_clicked)
        self.editor.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt 命名
        """拦截 editor 上的 Ctrl+Enter。"""
        if obj is self.editor and event.type() == QEvent.KeyPress:
            if (event.key() in (Qt.Key_Return, Qt.Key_Enter)
                    and event.modifiers() & Qt.ControlModifier):
                self._on_generate_clicked()
                return True
        return super().eventFilter(obj, event)

    def _on_generate_clicked(self) -> None:
        """点击生成: 取文本, 非空则发射信号。"""
        text = self.get_text()
        if text.strip():
            self.generate_requested.emit(text)

    # ---- 公共 API ----
    def get_text(self) -> str:
        """返回输入框的自然语言文本。"""
        return self.editor.toPlainText()

    def set_readonly(self, readonly: bool) -> None:
        """设置只读状态 (生成中禁用, 完成后恢复)。"""
        self.editor.setReadOnly(readonly)
        self.generate_button.setEnabled(not readonly)

    def clear(self) -> None:
        """清空输入框。"""
        self.editor.clear()
