# gui/widgets/diagnostics_dialog.py
"""环境自检对话框。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from sql_coach.diagnostics.checks import CheckResult, run_all
from sql_coach.diagnostics.installer import apply_auto_fixes, copy_hint
from sql_coach.diagnostics.report import format_results

_ICONS = {"ok": "✓", "warn": "!", "fail": "✗"}
_COLORS = {"ok": "#40a02b", "warn": "#df8e1d", "fail": "#d20f39"}

SKIP_MARKER = Path.home() / ".sql-coach" / ".skip_diagnostics"


class DiagnosticsDialog(QDialog):
    """展示自检结果，提供"自动修复"与"复制命令"。"""

    def __init__(self, results: list[CheckResult], env_path: str = ".env",
                 config=None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.results = results
        self.env_path = env_path
        self.config = config
        self.setWindowTitle("环境自检")
        self.resize(620, 460)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("启动环境自检")
        f = title.font(); f.setBold(True); f.setPointSize(12); title.setFont(f)
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self._inner_layout = QVBoxLayout(inner)
        self._inner_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        self._render()

        btn_row = QHBoxLayout()
        self.fix_button = QPushButton("🔧 自动修复可修复项")
        self.fix_button.setEnabled(any(r.auto_fixable and r.status != "ok"
                                       for r in self.results))
        self.fix_button.clicked.connect(self._on_fix)
        btn_row.addWidget(self.fix_button)

        self.copy_button = QPushButton("📋 复制安装命令")
        self.copy_button.clicked.connect(self._on_copy)
        btn_row.addWidget(self.copy_button)

        btn_row.addStretch(1)
        self.dont_ask = QCheckBox("不再提示")
        btn_row.addWidget(self.dont_ask)
        skip = QPushButton("跳过")
        skip.clicked.connect(self._on_skip)
        btn_row.addWidget(skip)
        layout.addLayout(btn_row)

    def _render(self) -> None:
        while self._inner_layout.count():
            item = self._inner_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for r in self.results:
            head = QLabel(f"{_ICONS.get(r.status, '?')}  {r.name}: {r.message}")
            head.setStyleSheet(f"color: {_COLORS.get(r.status, '#888')}; font-weight: bold;")
            head.setWordWrap(True)
            self._inner_layout.addWidget(head)
            if r.fix_hint:
                hint = QLabel(f"    → {r.fix_hint}")
                hint.setStyleSheet("color: #666;")
                hint.setWordWrap(True)
                hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
                self._inner_layout.addWidget(hint)

    def _on_fix(self) -> None:
        outcomes = apply_auto_fixes(self.results, self.env_path)
        if self.config is not None:
            self.results = run_all(self.config, self.env_path)
        else:
            # 无 config 时无法重跑自检，只能依据实际修复结果标记：
            # 仅 applied=True 且 name 匹配的项才视为已修复。
            fixed = {o.name for o in outcomes if o.applied}
            self.results = [
                CheckResult(r.name, "ok", "已修复") if r.auto_fixable and r.name in fixed
                else r
                for r in self.results
            ]
        self.fix_button.setEnabled(False)
        self._render()

    def _on_copy(self) -> None:
        hints = "\n".join(r.fix_hint for r in self.results if r.fix_hint)
        if not hints:
            return
        if copy_hint(hints):
            self.copy_button.setText("✅ 已复制")
        else:
            self.copy_button.setText("❌ 复制失败，请手动选择命令")

    def _on_skip(self) -> None:
        if self.dont_ask.isChecked():
            try:
                SKIP_MARKER.parent.mkdir(parents=True, exist_ok=True)
                SKIP_MARKER.touch()
            except OSError:
                pass
        self.reject()

    def summary_text(self) -> str:
        return format_results(self.results)
