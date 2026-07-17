# gui/widgets/benchmark_chart.py
"""性能对比柱状图, 用 matplotlib FigureCanvasQTAgg。"""
from __future__ import annotations

from typing import Optional

import matplotlib

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from sql_coach.models import BenchmarkResult

# 配色: 原始 SQL 红色, 优化 SQL 绿色 (Catppuccin 风格)
_COLOR_ORIGINAL = "#f38ba8"
_COLOR_OPTIMIZED = "#a6e3a1"

# 配置中文字体 (DejaVu Sans 默认不支持 CJK)
# Windows: Microsoft YaHei | macOS: PingFang SC | Linux: WenQuanYi/Noto
matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "PingFang SC", "Heiti SC",
    "WenQuanYi Micro Hei", "Noto Sans CJK SC", "SimHei",
    "DejaVu Sans",  # 兜底
]
matplotlib.rcParams["axes.unicode_minus"] = False  # 修复负号显示


class BenchmarkChartWidget(FigureCanvasQTAgg):
    """水平柱状图, 展示原始 vs 优化 SQL 的耗时。"""

    def __init__(self, parent=None) -> None:
        self.fig = Figure(figsize=(5, 2), tight_layout=True)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self._draw_empty()

    def _draw_empty(self) -> None:
        """无数据时的占位。"""
        self.ax.clear()
        self.ax.set_title("无性能对比数据")
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.ax.axis("off")
        self.draw()

    def set_benchmark(self, benchmark: Optional[BenchmarkResult]) -> None:
        """更新图表, 传 None 显示空状态。"""
        if benchmark is None:
            self._draw_empty()
            return

        self.ax.clear()
        labels = ["原始 SQL", "优化 SQL"]
        times = [benchmark.original_time, benchmark.optimized_time]
        colors = [_COLOR_ORIGINAL, _COLOR_OPTIMIZED]

        bars = self.ax.barh(labels, times, color=colors, edgecolor="white")
        self.ax.set_xlabel("耗时 (秒)")
        self.ax.set_title("性能对比")

        # 柱子右侧标注耗时数值
        max_time = max(times) if times else 1.0
        for bar, t in zip(bars, times):
            self.ax.text(
                bar.get_width() + max_time * 0.02,
                bar.get_y() + bar.get_height() / 2,
                f"{t:.3f}s",
                va="center", ha="left", fontsize=10,
            )

        # 底部显示提速倍数
        if benchmark.speedup == float("inf"):
            speedup_text = "提速: 无限大"
        else:
            speedup_text = f"提速: {benchmark.speedup:.1f}x"
        self.ax.figure.text(
            0.5, 0.02, speedup_text,
            ha="center", fontsize=11, color=_COLOR_OPTIMIZED, weight="bold",
        )

        self.draw()
