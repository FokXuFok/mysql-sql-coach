# tests/test_benchmark.py
from unittest.mock import MagicMock

from sql_coach.report.benchmark import benchmark_sqls, BenchmarkResult


def test_benchmark_returns_result():
    mock_conn = MagicMock()
    mock_conn.benchmark.return_value = 2.5
    mock_conn.is_connected.return_value = True

    # Mock explain to return rows count
    from sql_coach.models import ExplainResult, ExplainRow
    original_explain = ExplainResult(
        rows=[ExplainRow(id=1, select_type="SIMPLE", table="t",
                         type="ALL", key=None, rows=420000, extra="")],
        is_full_scan=True, missing_indexes=[], problems=[]
    )
    optimized_explain = ExplainResult(
        rows=[ExplainRow(id=1, select_type="SIMPLE", table="t",
                         type="ref", key="idx", rows=200, extra="")],
        is_full_scan=False, missing_indexes=[], problems=[]
    )

    mock_conn.explain.side_effect = [original_explain, optimized_explain]

    result = benchmark_sqls(mock_conn, "SELECT * FROM t", "SELECT id FROM t", runs=3)

    assert isinstance(result, BenchmarkResult)
    assert result.original_time == 2.5
    assert result.optimized_time == 2.5
    assert result.original_rows == 420000
    assert result.optimized_rows == 200
    assert result.speedup == 1.0


def test_benchmark_with_zero_optimized_time():
    """Test speedup calculation when optimized time is very small."""
    from sql_coach.models import ExplainResult, ExplainRow
    mock_conn = MagicMock()
    mock_conn.is_connected.return_value = True
    mock_conn.benchmark.side_effect = [2.0, 0.0]

    original_explain = ExplainResult(
        rows=[ExplainRow(id=1, select_type="SIMPLE", table="t",
                         type="ALL", key=None, rows=1000, extra="")],
        is_full_scan=True, missing_indexes=[], problems=[]
    )
    optimized_explain = ExplainResult(
        rows=[ExplainRow(id=1, select_type="SIMPLE", table="t",
                         type="ref", key="idx", rows=10, extra="")],
        is_full_scan=False, missing_indexes=[], problems=[]
    )
    mock_conn.explain.side_effect = [original_explain, optimized_explain]

    result = benchmark_sqls(mock_conn, "SELECT * FROM t", "SELECT id FROM t")
    assert result.speedup == float("inf") or result.speedup > 0


def test_benchmark_not_connected_returns_none():
    mock_conn = MagicMock()
    mock_conn.is_connected.return_value = False

    result = benchmark_sqls(mock_conn, "SELECT 1", "SELECT 1")
    assert result is None