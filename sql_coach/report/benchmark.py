"""Performance benchmark module."""
import logging
from typing import Optional

from ..models import BenchmarkResult

logger = logging.getLogger(__name__)


def benchmark_sqls(conn, original_sql: str, optimized_sql: str,
                   runs: int = 3) -> Optional[BenchmarkResult]:
    """Benchmark original vs optimized SQL.

    Args:
        conn: DBConnector or MockConnector instance
        original_sql: Original SQL string
        optimized_sql: Optimized SQL string
        runs: Number of runs to average

    Returns:
        BenchmarkResult or None if connection unavailable
    """
    if not conn.is_connected():
        return None

    try:
        original_time = conn.benchmark(original_sql, runs=runs)
        optimized_time = conn.benchmark(optimized_sql, runs=runs)

        original_explain = conn.explain(original_sql)
        optimized_explain = conn.explain(optimized_sql)

        original_rows = sum(r.rows for r in original_explain.rows) if original_explain.rows else 0
        optimized_rows = sum(r.rows for r in optimized_explain.rows) if optimized_explain.rows else 0

        if optimized_time > 0:
            speedup = original_time / optimized_time
        else:
            speedup = float("inf") if original_time > 0 else 1.0

        return BenchmarkResult(
            original_time=original_time,
            optimized_time=optimized_time,
            speedup=speedup,
            original_rows=original_rows,
            optimized_rows=optimized_rows,
        )
    except Exception as e:
        logger.warning(f"Benchmark failed: {e}")
        return None