# sql_coach/db/connector.py
"""MySQL database connector."""
import time
import logging
from typing import Optional

import pymysql

from ..models import DBConfig, ExplainResult
from ..engine.explain_runner import run_explain as _run_explain

logger = logging.getLogger(__name__)


class DBConnector:
    """MySQL database connector."""

    def __init__(self, config: DBConfig):
        self.config = config
        self._conn: Optional[pymysql.Connection] = None

    def connect(self) -> bool:
        """Establish connection. Returns True on success, False on failure."""
        try:
            self._conn = pymysql.connect(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                database=self.config.database,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
            )
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            self._conn = None
            return False

    def is_connected(self) -> bool:
        return self._conn is not None and self._conn.open

    def explain(self, sql: str) -> ExplainResult:
        """Execute EXPLAIN and return parsed result."""
        if not self.is_connected():
            return ExplainResult(rows=[], is_full_scan=False,
                                 missing_indexes=[], problems=["数据库未连接"])
        return _run_explain(self._conn, sql)

    def benchmark(self, sql: str, runs: int = 3) -> float:
        """Execute SQL multiple times, return average elapsed time in seconds."""
        if not self.is_connected():
            return 0.0

        times = []
        for _ in range(runs):
            start = time.perf_counter()
            try:
                with self._conn.cursor() as cursor:
                    cursor.execute(sql)
                    cursor.fetchall()
            except Exception as e:
                logger.warning(f"Benchmark run failed: {e}")
                continue
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        return sum(times) / len(times) if times else 0.0

    def execute(self, sql: str) -> None:
        """Execute a DDL/DML statement."""
        if not self.is_connected():
            raise RuntimeError("Database not connected")
        with self._conn.cursor() as cursor:
            cursor.execute(sql)
        self._conn.commit()

    def close(self) -> None:
        """Close the connection."""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None