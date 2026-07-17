# gui/widgets/report_view.py
"""报告容器, QScrollArea 子类。

内部组装: EXPLAIN 表格 + 问题列表 + 优化 SQL + 索引 DDL + 性能图表。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from sql_coach.coach import Report
from sql_coach.models import Problem

from .explain_table import ExplainTableWidget
# 注意: benchmark_chart 故意不在顶部导入, 避免启动时加载 matplotlib/numpy/PIL
# (省 ~2-3 秒启动时间). 仅在首次渲染报告时延迟导入.

# 严重度图标
_SEVERITY_ICONS = {
    "critical": "🔴",
    "warning": "🟡",
    "info": "🔵",
}

# 等宽字体样式
_MONO_FONT = QFont("Consolas")
_MONO_FONT.setStyleHint(QFont.Monospace)
_MONO_FONT.setPointSize(10)


class ReportView(QScrollArea):
    """报告展示容器, 垂直滚动。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # 内部容器
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignTop)
        self._layout.setSpacing(16)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self.setWidget(self._container)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._show_placeholder()

    # ---- 内部 UI 构建 ----
    def _show_placeholder(self) -> None:
        """显示空状态提示。"""
        self._clear_layout()
        placeholder = QLabel("请在左侧输入 SQL 后点击 [分析] 按钮")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
        self._layout.addWidget(placeholder)

    def _clear_layout(self) -> None:
        """清空布局中的所有 widget。"""
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _section_label(self, text: str) -> QLabel:
        """章节标题。"""
        label = QLabel(text)
        f = label.font()
        f.setBold(True)
        f.setPointSize(12)
        label.setFont(f)
        label.setStyleSheet("color: #1e66f5; padding-top: 8px;")
        return label

    def _code_block(self, text: str) -> QLabel:
        """代码块 (等宽字体, 深色背景)。"""
        label = QLabel(text)
        label.setFont(_MONO_FONT)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet(
            "background: #1e1e2e; color: #cdd6f4; "
            "padding: 10px 12px; border-radius: 4px;"
        )
        label.setWordWrap(True)
        return label

    def _build_problems_section(self, problems: list[Problem]) -> Optional[QWidget]:
        """问题列表章节, 无问题返回 None。"""
        if not problems:
            return None

        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #fff5e6; border-radius: 4px; }")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel(f"⚠️ 发现 {len(problems)} 个问题")
        f = title.font(); f.setBold(True); f.setPointSize(11); title.setFont(f)
        layout.addWidget(title)

        for p in problems:
            icon = _SEVERITY_ICONS.get(p.severity, "•")
            row = QLabel(
                f"{icon} <b>[{p.severity}]</b> <code>{p.table}</code>: "
                f"{p.description}"
            )
            row.setTextFormat(Qt.RichText)
            row.setWordWrap(True)
            layout.addWidget(row)
            if p.suggestion:
                sugg = QLabel(f"&nbsp;&nbsp;&nbsp;&nbsp;→ {p.suggestion}")
                sugg.setTextFormat(Qt.RichText)
                sugg.setStyleSheet("color: #666; padding-left: 16px;")
                sugg.setWordWrap(True)
                layout.addWidget(sugg)

        return frame

    def _build_index_section(self, ddls: list[str]) -> Optional[QWidget]:
        """索引建议章节。"""
        if not ddls:
            return None
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._section_label("📌 索引建议"))
        for ddl in ddls:
            layout.addWidget(self._code_block(ddl))
        return frame

    def _build_benchmark_section(
        self, benchmark
    ) -> Optional[QWidget]:
        """性能对比章节。"""
        if benchmark is None:
            return None
        # 延迟导入: 首次渲染报告时才加载 matplotlib/numpy (省启动时间)
        from .benchmark_chart import BenchmarkChartWidget
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._section_label("📊 性能对比"))
        chart = BenchmarkChartWidget()
        chart.set_benchmark(benchmark)
        layout.addWidget(chart)
        return frame

    # ---- 公共 API ----
    def set_report(self, report: Report) -> None:
        """渲染完整报告。"""
        self._clear_layout()

        # 原始 SQL
        self._layout.addWidget(self._section_label("📝 原始 SQL"))
        self._layout.addWidget(self._code_block(report.sql_info.raw_sql))

        # 执行计划
        if report.explain and report.explain.rows:
            self._layout.addWidget(self._section_label("📋 执行计划"))
            table = ExplainTableWidget()
            table.set_explain(report.explain)
            self._layout.addWidget(table)

        # 问题列表
        problems_widget = self._build_problems_section(report.analysis.problems)
        if problems_widget is not None:
            self._layout.addWidget(problems_widget)

        # 优化后 SQL
        self._layout.addWidget(self._section_label("✅ 优化后 SQL"))
        self._layout.addWidget(self._code_block(report.analysis.optimized_sql))

        # 索引建议
        index_widget = self._build_index_section(report.analysis.index_ddls)
        if index_widget is not None:
            self._layout.addWidget(index_widget)

        # AI 解释
        if report.analysis.explanation:
            self._layout.addWidget(self._section_label("🤖 AI 解释"))
            expl = QLabel(report.analysis.explanation)
            expl.setWordWrap(True)
            expl.setStyleSheet("padding: 8px; background: #f5f5f5; border-radius: 4px;")
            self._layout.addWidget(expl)

        # 性能对比
        bench_widget = self._build_benchmark_section(report.benchmark)
        if bench_widget is not None:
            self._layout.addWidget(bench_widget)

        # 撑底
        self._layout.addStretch(1)

    def clear(self) -> None:
        """清空报告, 显示空状态。"""
        self._show_placeholder()
