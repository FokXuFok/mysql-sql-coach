# gui/widgets/benchmark_chart.py
"""性能对比柱状图, 用 matplotlib FigureCanvasQTAgg。"""
from __future__ import annotations

from typing import Optional

import matplotlib

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from sql_coach.models import BenchmarkResult

# 配色 (Catppuccin 风格): 原始 SQL 红色; 优化后更快为绿, 未变快为琥珀色
_COLOR_ORIGINAL = "#f38ba8"
_COLOR_FASTER = "#a6e3a1"
_COLOR_SLOWER = "#f9e2af"
# 结论文字用深色, 保证在白底上可读 (浅琥珀作文字色对比度不足)
_TEXT_FASTER = "#2f7d32"
_TEXT_SLOWER = "#b8860b"

# 差异小于该比例时视为测量噪声, 不下"更快/更慢"的结论
_NOISE_RATIO = 0.10

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

    # ---------- 展示辅助 ----------

    @staticmethod
    def _pick_unit(times: list[float]) -> tuple[str, float]:
        """按量级选单位: 最大耗时不足 0.1 秒时用毫秒, 否则用秒。

        返回 (单位名, 换算系数)。用毫秒可避免 ``0.0545`` 与 ``0.0554``
        都被格式化成 ``0.055s`` 而看不出差异。
        """
        peak = max(times) if times else 0.0
        if peak < 0.1:
            return "ms", 1000.0
        return "s", 1.0

    @staticmethod
    def _fmt_value(seconds: float, unit: str, factor: float) -> str:
        """按单位格式化耗时, 保留足够有效位以便区分相近数值。"""
        v = seconds * factor
        if unit == "ms":
            # <1ms 保留 3 位, 其余 2 位
            return f"{v:.3f} ms" if v < 1 else f"{v:.2f} ms"
        return f"{v:.3f} s"

    @staticmethod
    def _verdict(benchmark: BenchmarkResult) -> tuple[str, str]:
        """给出结论文案与配色。

        差异在 ``_NOISE_RATIO`` 以内时明确标注为噪声, 避免把抖动
        误读成"优化生效"或"优化变慢"。
        """
        speedup = benchmark.speedup
        if speedup == float("inf"):
            return "提速：无限大", _TEXT_FASTER
        if speedup >= 1.0 + _NOISE_RATIO:
            return f"提速 {speedup:.2f}x", _TEXT_FASTER
        if speedup > 1.0 - _NOISE_RATIO:
            return "基本持平（差异在测量噪声范围内）", _TEXT_SLOWER
        return f"反而慢了 {1.0 / speedup:.2f}x", _COLOR_ORIGINAL

    # ---------- 主入口 ----------

    def set_benchmark(self, benchmark: Optional[BenchmarkResult]) -> None:
        """更新图表, 传 None 显示空状态。"""
        if benchmark is None:
            self._draw_empty()
            return

        self.ax.clear()
        labels = ["原始 SQL", "优化 SQL"]
        times = [float(benchmark.original_time), float(benchmark.optimized_time)]

        unit, factor = self._pick_unit(times)
        verdict, verdict_color = self._verdict(benchmark)
        # 按单位换算后再绘制, 保证刻度与单位一致 (否则轴刻度仍是秒)
        scaled = [t * factor for t in times]

        # 优化后未变快时, 绿色会误导, 改用琥珀色
        opt_color = _COLOR_FASTER if benchmark.speedup >= 1.0 + _NOISE_RATIO \
            else _COLOR_SLOWER
        colors = [_COLOR_ORIGINAL, opt_color]

        bars = self.ax.barh(labels, scaled, color=colors, edgecolor="white",
                            height=0.55)
        self.ax.set_title("性能对比")
        # 结论并入 x 轴标签, 避免原先画在 figure 底部时压住"耗时"标签
        self.ax.set_xlabel(f"耗时（{unit}）　{verdict}",
                           color=verdict_color, fontsize=10, weight="bold")

        # 柱子末端标注耗时（按单位自适应精度）
        peak = max(scaled) if scaled else 0.0
        pad = peak * 0.02 if peak > 0 else 0.01
        for bar, t in zip(bars, times):
            self.ax.text(
                bar.get_width() + pad,
                bar.get_y() + bar.get_height() / 2,
                self._fmt_value(t, unit, factor),
                va="center", ha="left", fontsize=10,
            )

        # 优化柱右侧补充变化幅度, 让微小差异也能被看见
        if times[0] > 0:
            delta = (times[1] - times[0]) / times[0] * 100.0
            arrow = "↓" if delta < 0 else "↑"
            if abs(delta) < 0.5:
                delta_text = "≈ 0%"
            else:
                delta_text = f"{arrow} {abs(delta):.1f}%"
            bar = bars[1]
            self.ax.text(
                bar.get_width() + pad,
                bar.get_y() + bar.get_height() / 2 - 0.24,
                f"（较原始 {delta_text}）",
                va="center", ha="left", fontsize=9,
                color="#6c7086",
            )

        # 右边留白, 保证标注不被裁掉
        self.ax.set_xlim(0, peak * 1.32 if peak > 0 else 1.0)
        self.ax.grid(axis="x", linestyle=":", alpha=0.4)
        self.ax.set_axisbelow(True)

        self.draw()
