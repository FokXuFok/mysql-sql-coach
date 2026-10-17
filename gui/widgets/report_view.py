# gui/widgets/report_view.py
"""报告容器, QScrollArea 子类。

内部组装: EXPLAIN 表格 + 问题列表 + 优化 SQL + 索引 DDL + 性能图表 + 索引实测。

容错: 每个章节单独渲染，某一节失败（例如打包环境下图表依赖异常）只会在该位置
显示一条错误提示，**不会让后面的章节（尤其是「索引实测」）一起消失**。
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

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

logger = logging.getLogger(__name__)

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
        """清空布局中的所有 widget。

        仅 ``deleteLater()`` 不够：它只是**排队**删除，控件在被真正析构前
        仍是容器的子控件、仍会继续绘制。连续两次渲染时旧图表会与新图表
        叠在一起，看起来就是"柱长和数值对不上"。因此这里先 hide + 解除
        父子关系，让它立刻从界面消失，再交给 deleteLater 释放内存。
        """
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
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

    def _section_error_label(self, name: str, exc: BaseException) -> QLabel:
        """某一节渲染失败时的占位提示（而不是让整份报告残缺）。"""
        label = QLabel(f"⚠️ 本节渲染失败（{name}）：{type(exc).__name__}: {exc}")
        label.setWordWrap(True)
        label.setStyleSheet(
            "color: #d20f39; background: #fde2e0; padding: 8px 10px; "
            "border-radius: 4px;"
        )
        return label

    def _add_section(self, builder: Callable[..., Optional[QWidget]],
                     *args) -> None:
        """渲染单个章节并加入布局；失败则显示错误占位，绝不中断后续章节。"""
        try:
            widget = builder(*args)
        except Exception as e:  # noqa: BLE001 - 单节失败不能拖垮整份报告
            logger.exception("报告章节渲染失败: %s",
                             getattr(builder, "__name__", builder))
            widget = self._section_error_label(
                getattr(builder, "__name__", "section").lstrip("_build_"), e)
        if widget is not None:
            self._layout.addWidget(widget)

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

    def _build_index_impact_section(self, impact) -> Optional[QWidget]:
        """索引实测章节（before/after/提速/是否已回滚）。"""
        if impact is None:
            return None
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._section_label("📈 索引实测"))
        speedup = "无限大" if impact.speedup == float("inf") else f"{impact.speedup:.1f}x"
        rolled = len(impact.applied_ddls) if impact.rolled_back else 0
        lines = [
            f"建索引前: {impact.before_time:.3f}s",
            f"建索引后: {impact.after_time:.3f}s",
            f"实测提速: {speedup}",
            f"已回滚创建索引: {rolled} 个",
        ]
        if impact.verdict:
            lines.append(f"结论: {impact.verdict}")
        if impact.selectivity >= 0:
            lines.append(
                f"命中率: {impact.selectivity * 100:.2f}%"
                f"（{impact.matched_rows}/{impact.total_rows} 行）"
            )
        if impact.error:
            lines.append(f"错误: {impact.error}")
        layout.addWidget(self._code_block("\n".join(lines)))
        return frame

    def _build_explain_table(self, report: Report) -> QWidget:
        """执行计划表格（单独成节，便于隔离渲染失败）。"""
        table = ExplainTableWidget()
        table.set_explain(report.explain)
        return table

    def _build_explanation(self, text: str) -> QWidget:
        """解释说明正文。"""
        expl = QLabel(text)
        expl.setWordWrap(True)
        expl.setStyleSheet("padding: 8px; background: #f5f5f5; border-radius: 4px;")
        return expl

    def _engine_badge(self, report) -> QLabel:
        """引擎 / 复杂度徽章。"""
        engine = "本地规则" if report.engine_used == "local" else report.engine_used
        level = "-"
        if report.complexity is not None:
            level = {"simple": "简单", "medium": "中等", "complex": "复杂"}.get(
                report.complexity.level, report.complexity.level)
            level = f"{level} ({report.complexity.score})"
        label = QLabel(f"优化引擎：{engine}    复杂度：{level}")
        label.setStyleSheet(
            "color: #1e66f5; font-weight: bold; padding: 4px 0;")
        return label

    # ---- 公共 API ----
    def set_report(self, report: Report) -> None:
        """渲染完整报告。

        每个章节独立渲染（见 :meth:`_add_section`）：某一节失败不会影响后续章节，
        因此「索引实测」不会因为「性能对比」图表出问题而消失。
        """
        self._clear_layout()

        # 引擎 / 复杂度徽章
        self._add_section(lambda: self._engine_badge(report))

        # 原始 SQL
        self._add_section(lambda: self._section_label("📝 原始 SQL"))
        self._add_section(lambda: self._code_block(report.sql_info.raw_sql))

        # 执行计划
        if report.explain and report.explain.rows:
            self._add_section(lambda: self._section_label("📋 执行计划"))
            self._add_section(self._build_explain_table, report)

        # 问题列表
        self._add_section(self._build_problems_section, report.analysis.problems)

        # 优化后 SQL
        self._add_section(lambda: self._section_label("✅ 优化后 SQL"))
        self._add_section(lambda: self._code_block(report.analysis.optimized_sql))

        # 索引建议
        self._add_section(self._build_index_section, report.analysis.index_ddls)

        # 解释说明（按引擎动态显示标题）
        if report.analysis.explanation:
            title = "📋 本地规则说明" if report.engine_used == "local" else "🤖 AI 解释"
            self._add_section(lambda t=title: self._section_label(t))
            self._add_section(self._build_explanation, report.analysis.explanation)

        # 性能对比
        self._add_section(self._build_benchmark_section, report.benchmark)

        # 索引实测
        self._add_section(self._build_index_impact_section, report.index_impact)

        # 撑底
        self._layout.addStretch(1)

    def clear(self) -> None:
        """清空报告, 显示空状态。"""
        self._show_placeholder()
