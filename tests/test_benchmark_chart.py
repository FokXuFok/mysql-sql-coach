# tests/test_benchmark_chart.py
"""BenchmarkChartWidget 冒烟测试。"""
import pytest
from PySide6.QtWidgets import QApplication

from sql_coach.models import BenchmarkResult
from gui.widgets.benchmark_chart import BenchmarkChartWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_set_benchmark_draws_bars(app):
    """填充 benchmark 后图表绘制两根柱子。"""
    widget = BenchmarkChartWidget()
    bench = BenchmarkResult(
        original_time=0.5,
        optimized_time=0.02,
        speedup=25.0,
        original_rows=1000,
        optimized_rows=1,
    )
    widget.set_benchmark(bench)
    # ax 应该有 2 个 patch (柱子)
    assert len(widget.ax.patches) == 2


def test_set_benchmark_none_shows_empty_message(app):
    """传 None 显示"无性能对比数据"。"""
    widget = BenchmarkChartWidget()
    widget.set_benchmark(None)
    # 文本应该包含提示
    text = widget.ax.get_title()
    assert "无性能对比数据" in text or "无" in text
