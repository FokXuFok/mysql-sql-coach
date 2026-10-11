# sql_coach/coach.py
"""Main orchestration service."""
import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .models import (
    Config, SQLInfo, ExplainResult, AnalysisResult, BenchmarkResult, Complexity
)
from .local.complexity import ComplexityScorer
from .local.schema import Schema, SchemaProvider
from .optimizer import select_optimizer
from .engine.sql_parser import parse as parse_sql
from .ai.factory import create_ai_engine
from .db.connector import DBConnector
from .db.mock import MockConnector
from .report.benchmark import benchmark_sqls
from .cache import AnalysisCache

logger = logging.getLogger(__name__)


@dataclass
class Report:
    """Final analysis report."""
    sql_info: SQLInfo
    explain: Optional[ExplainResult]
    analysis: AnalysisResult
    benchmark: Optional[BenchmarkResult]
    engine_used: str = "ai"
    complexity: Optional[Complexity] = None


class SQLCoach:
    """Main orchestration service."""

    def __init__(self, config: Config, use_cache: bool = True):
        self.config = config
        if config.mock:
            self.db = MockConnector()
        else:
            self.db = DBConnector(config.db)
        self._ai = None
        self.schema_provider = SchemaProvider(self.db)
        # SQLite 永久缓存 (mock 模式跳过)
        if use_cache and not config.mock:
            self.cache = AnalysisCache()
        else:
            self.cache = None

    @property
    def ai(self):
        """惰性创建 AI 引擎：纯本地模式不需要 API Key。"""
        if self._ai is None:
            self._ai = create_ai_engine(self.config.model, self.config)
        return self._ai

    def connect(self) -> bool:
        """Connect to database. Returns True on success."""
        if self.config.mock:
            return True
        return self.db.connect()

    def analyze(
        self,
        sql: str,
        on_stage: Optional[Callable[[str, int, int, str], None]] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> Report:
        """Run full analysis pipeline on a SQL string.

        Args:
            sql: SQL string to analyze.
            on_stage: Callback(stage_name, step, total, status) for progress.
            on_chunk: Callback(text) for AI streaming output.
        """
        t_total = time.perf_counter()

        # Step 1: Parse SQL
        if on_stage:
            on_stage("parse", 1, 4, "start")
        t = time.perf_counter()
        sql_info = parse_sql(sql)
        logger.debug('timing parse_sql: %.2f ms', (time.perf_counter() - t) * 1000)
        if on_stage:
            on_stage("parse", 1, 4, "done")

        # Step 1.5: 读取 schema（尽力而为，连不上库时为空）
        schema = Schema()
        if not self.config.mock and self.db.is_connected():
            schema = self.schema_provider.load(sql_info.tables)

        # Step 2: Run EXPLAIN (skip in mock mode)
        if on_stage:
            on_stage("explain", 2, 4, "start")
        t = time.perf_counter()
        explain = None
        if not self.config.mock and self.db.is_connected():
            explain = self.db.explain(sql)
        logger.debug('timing explain: %.2f ms', (time.perf_counter() - t) * 1000)
        if on_stage:
            on_stage("explain", 2, 4, "done")

        # Step 3: 评分 + 分流（本地规则引擎 / AI）
        complexity = ComplexityScorer(self.config.complexity_threshold).score(sql_info)
        optimizer, engine_name = select_optimizer(
            self.config, complexity, lambda: self.ai)

        if on_stage:
            on_stage("ai", 3, 4, "start")
        t = time.perf_counter()
        analysis = None
        if engine_name != "local" and self.cache:
            analysis = self.cache.get(sql)
        if analysis is not None:
            logger.debug('timing optimize: %.2f ms (cached)', (time.perf_counter() - t) * 1000)
        else:
            analysis = optimizer.optimize(sql_info, explain, schema, on_chunk=on_chunk)
            logger.debug('timing optimize: %.2f ms', (time.perf_counter() - t) * 1000)
            if engine_name != "local" and self.cache:
                self.cache.put(sql, analysis)
        if on_stage:
            on_stage("ai", 3, 4, "done")

        # Step 4: Benchmark (skip in mock mode or if no optimized SQL)
        if on_stage:
            on_stage("benchmark", 4, 4, "start")
        t = time.perf_counter()
        benchmark = None
        if (not self.config.mock
                and self.db.is_connected()
                and analysis.optimized_sql
                and analysis.optimized_sql != sql):
            benchmark = benchmark_sqls(
                self.db, sql, analysis.optimized_sql,
                runs=self.config.benchmark_runs,
            )
        logger.debug('timing benchmark: %.2f ms', (time.perf_counter() - t) * 1000)
        if on_stage:
            on_stage("benchmark", 4, 4, "done")
        logger.debug('timing total: %.2f ms', (time.perf_counter() - t_total) * 1000)

        return Report(
            sql_info=sql_info,
            explain=explain,
            analysis=analysis,
            benchmark=benchmark,
            engine_used=engine_name,
            complexity=complexity,
        )

    def close(self) -> None:
        """Clean up resources."""
        self.db.close()
