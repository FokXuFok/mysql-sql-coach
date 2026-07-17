# gui/widgets/history_dialog.py
"""历史记录对话框, QDialog 子类。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from gui.storage.history_store import HistoryStore


def _format_record(rec: dict) -> str:
    """格式化列表项显示文本。"""
    ts = rec.get("timestamp", "")
    # 取 "YYYY-MM-DD HH:MM" 部分
    ts_short = ts.replace("T", " ").rsplit(":", 1)[0] if ts else ""
    sql = rec.get("sql", "")
    if len(sql) > 50:
        sql = sql[:50] + "..."
    speedup = rec.get("speedup")
    if speedup is None:
        speedup_text = "无提速"
    elif speedup == float("inf"):
        speedup_text = "提速: 无限大"
    else:
        speedup_text = f"提速: {speedup:.1f}x"
    return f"[{ts_short}] {sql} ({speedup_text})"


class HistoryDialog(QDialog):
    """历史记录对话框。

    Signals:
        sql_selected(str): 双击历史项, 携带 SQL 文本
    """

    sql_selected = Signal(str)

    def __init__(self, store: HistoryStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("历史记录")
        self.resize(640, 480)
        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 标题
        title = QLabel("🕘 历史记录 (双击填入输入框)")
        f = title.font(); f.setBold(True); title.setFont(f)
        layout.addWidget(title)

        # 列表
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget, 1)

        # 底部按钮行
        btn_row = QHBoxLayout()
        btn_row.addWidget(QLabel("提示: 双击选择 SQL"))

        self.delete_button = QPushButton("🗑 删除选中")
        self.delete_button.clicked.connect(self._on_delete_clicked)
        btn_row.addWidget(self.delete_button)

        self.clear_button = QPushButton("🧹 清空全部")
        self.clear_button.clicked.connect(self._on_clear_clicked)
        btn_row.addWidget(self.clear_button)

        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        btn_row.addWidget(close_button)

        layout.addLayout(btn_row)

    def _reload(self) -> None:
        """重新加载列表。"""
        self.list_widget.clear()
        for rec in self.store.list():
            item = QListWidgetItem(_format_record(rec))
            item.setData(Qt.UserRole, rec)  # 存原始数据
            self.list_widget.addItem(item)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """双击: 发射 sql_selected 信号并关闭对话框。"""
        rec = item.data(Qt.UserRole)
        if rec:
            self.sql_selected.emit(rec.get("sql", ""))
            self.accept()

    def _on_delete_clicked(self) -> None:
        """删除选中记录。"""
        current = self.list_widget.currentItem()
        if current is None:
            return
        rec = current.data(Qt.UserRole)
        if rec:
            self.store.delete(rec["id"])
            self._reload()

    def _on_clear_clicked(self) -> None:
        """清空全部历史。"""
        self.store.clear()
        self._reload()
