# sql_coach/db/mock.py
"""Mock database connector for fallback mode."""
from ..models import ExplainResult


class MockConnector:
    """Mock connector used when no real database is available."""

    def __init__(self):
        pass

    def connect(self) -> bool:
        return True

    def is_connected(self) -> bool:
        return True

    def explain(self, sql: str) -> ExplainResult:
        return ExplainResult(rows=[], is_full_scan=False,
                             missing_indexes=[], problems=[])

    def benchmark(self, sql: str, runs: int = 3) -> float:
        return 0.0

    def execute(self, sql: str) -> None:
        pass

    def close(self) -> None:
        pass