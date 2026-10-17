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


def test_labels_use_ms_and_are_distinguishable(app):
    """小数值改用毫秒, 且 0.0545 与 0.0554 必须显示成不同的文字。

    历史 bug: 固定 `.3f` 把两者都格式化成 "0.055s", 用户看到"数值一样"。
    """
    widget = BenchmarkChartWidget()
    bench = BenchmarkResult(original_time=0.054527, optimized_time=0.055391,
                            speedup=0.984, original_rows=1, optimized_rows=1)
    widget.set_benchmark(bench)

    texts = [t.get_text() for t in widget.ax.texts]
    assert any("ms" in t for t in texts), texts
    vals = [t for t in texts if "ms" in t]
    assert len(set(vals)) == 2, f"两个数值应可区分, 实得 {vals}"


def test_axis_unit_matches_ticks(app):
    """单位标 ms 时, 柱子宽度也必须是毫秒量级 (刻度与单位一致)。"""
    widget = BenchmarkChartWidget()
    bench = BenchmarkResult(original_time=0.041, optimized_time=0.001,
                            speedup=41.0, original_rows=1, optimized_rows=1)
    widget.set_benchmark(bench)

    assert "ms" in widget.ax.get_xlabel()
    widths = [p.get_width() for p in widget.ax.patches]
    assert max(widths) > 1, f"柱子宽度应在毫秒量级, 实得 {widths}"


def test_verdict_faster(app):
    widget = BenchmarkChartWidget()
    widget.set_benchmark(BenchmarkResult(0.5, 0.02, 25.0, 1, 1))
    assert "提速" in widget.ax.get_xlabel()


def test_verdict_within_noise(app):
    """差异在噪声内时明确说"基本持平", 不谎称提速。"""
    widget = BenchmarkChartWidget()
    widget.set_benchmark(BenchmarkResult(0.053717, 0.054645, 0.983, 1, 1))
    label = widget.ax.get_xlabel()
    assert "持平" in label and "提速" not in label


def test_verdict_slower(app):
    widget = BenchmarkChartWidget()
    widget.set_benchmark(BenchmarkResult(0.1, 0.5, 0.2, 1, 1))
    assert "反而慢" in widget.ax.get_xlabel()


def test_delta_annotation_present(app):
    """优化柱旁应标注相对原始的变化幅度。"""
    widget = BenchmarkChartWidget()
    widget.set_benchmark(BenchmarkResult(0.041, 0.001, 41.0, 1, 1))
    assert any("较原始" in t.get_text() for t in widget.ax.texts)


def test_no_figure_level_text_overlaps_xlabel(app):
    """结论应并入 xlabel, 不能再画一个 figure 级文本压住轴标签。"""
    widget = BenchmarkChartWidget()
    widget.set_benchmark(BenchmarkResult(0.041, 0.001, 41.0, 1, 1))
    fig_texts = [t.get_text() for t in widget.fig.texts]
    assert not any("提速" in t for t in fig_texts), fig_texts
