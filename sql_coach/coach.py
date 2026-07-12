# sql_coach/coach.py
"""Main orchestration service."""
import logging
from dataclasses import dataclass
from typing import Optional

from .models import (
    Config, SQLInfo, ExplainResult, AnalysisResult, BenchmarkResult
)
from .engine.sql_parser import parse as parse_sql
from .ai.factory import create_ai_engine
from .db.connector import DBConnector
from .db.mock import MockConnector
from .report.benchmark import benchmark_sqls

logger = logging.getLogger(__name__)


@dataclass
class Report:
    """Final analysis report."""
    sql_info: SQLInfo
    explain: Optional[ExplainResult]
    analysis: AnalysisResult
    benchmark: Optional[BenchmarkResult]


class SQLCoach:
    """Main orchestration service."""

    def __init__(self, config: Config):
        self.config = config
        if config.mock:
            self.db = MockConnector()
        else:
            self.db = DBConnector(config.db)
        self.ai = create_ai_engine(config.model, config)

    def connect(self) -> bool:
        """Connect to database. Returns True on success."""
        if self.config.mock:
            return True
        return self.db.connect()

    def analyze(self, sql: str) -> Report:
        """Run full analysis pipeline on a SQL string."""
        # Step 1: Parse SQL
        sql_info = parse_sql(sql)

        # Step 2: Run EXPLAIN (skip in mock mode)
        explain = None
        if not self.config.mock and self.db.is_connected():
            explain = self.db.explain(sql)

        # Step 3: AI analysis
        analysis = self.ai.analyze(sql_info, explain)

        # Step 4: Benchmark (skip in mock mode or if no optimized SQL)
        benchmark = None
        if (not self.config.mock
                and self.db.is_connected()
                and analysis.optimized_sql
                and analysis.optimized_sql != sql):
            benchmark = benchmark_sqls(
                self.db, sql, analysis.optimized_sql,
                runs=self.config.benchmark_runs,
            )

        return Report(
            sql_info=sql_info,
            explain=explain,
            analysis=analysis,
            benchmark=benchmark,
        )

    def close(self) -> None:
        """Clean up resources."""
        self.db.close()
