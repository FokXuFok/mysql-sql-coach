# sql_coach/coach.py
"""Main orchestration service."""
import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .models import (
    Config, SQLInfo, ExplainResult, AnalysisResult, BenchmarkResult, Complexity,
    IndexImpact, NLQueryResult,
)
from .local.complexity import ComplexityScorer
from .local.engine import LocalOptimizer
from .local.schema import Schema, SchemaProvider
from .nl.parser import NLParser
from .nl_to_sql.builder import SQLBuilder
from .optimizer import select_optimizer, AIOptimizerAdapter
from .engine.sql_parser import parse as parse_sql
from .ai.factory import create_ai_engine
from .db.connector import DBConnector
from .db.mock import MockConnector
from .report.benchmark import benchmark_sqls
from .index_experiment import measure_index_impact
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
    index_impact: Optional[IndexImpact] = None


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
            try:
                analysis = optimizer.optimize(sql_info, explain, schema, on_chunk=on_chunk)
            except Exception as e:
                if engine_name != "local":
                    raise
                # 本地规则引擎整体失败 -> 降级到 AI（spec §12），不把异常抛给上层
                logger.warning("本地规则引擎失败，降级到 AI: %s", e)
                ai_engine = self.ai
                optimizer = AIOptimizerAdapter(ai_engine)
                engine_name = ai_engine.name()
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

        # Step 5: 索引实测（可选，临时建索引 → 复测 → 回滚）
        index_impact = None
        if (self.config.measure_index and not self.config.mock
                and self.db.is_connected() and analysis.index_ddls):
            index_impact = measure_index_impact(
                self.db, sql, analysis.index_ddls,
                runs=self.config.benchmark_runs,
            )
        logger.debug('timing total: %.2f ms', (time.perf_counter() - t_total) * 1000)

        return Report(
            sql_info=sql_info,
            explain=explain,
            analysis=analysis,
            benchmark=benchmark,
            engine_used=engine_name,
            complexity=complexity,
            index_impact=index_impact,
        )

    def close(self) -> None:
        """Clean up resources."""
        self.db.close()

    def generate_sql(
        self,
        text: str,
        execute: bool = True,
        verify: bool = True,
    ) -> NLQueryResult:
        """自然语言转 SQL。

        Args:
            text: 自然语言描述。
            execute: 是否执行生成的 SQL（mock 或未连接时不执行）。
            verify: 是否用本地规则引擎校验生成的 SQL（仅取 problems 作提示，
                不改写 SQL，避免改变用户意图）。
        """
        # 1. 读取 schema（连不上库时降级为空 schema）
        if not self.config.mock and self.db.is_connected():
            schema = self.schema_provider.load_all()
        else:
            schema = Schema()

        # 2. 解析自然语言 → 3. 生成 SQL
        nl_query = NLParser(schema).parse(text)
        sql = SQLBuilder().build(nl_query)

        # 4. 校验（可选）：仅取 problems 的描述作为 warnings，不使用 optimized_sql
        warnings: list[str] = []
        if verify and schema:
            sql_info = parse_sql(sql)
            analysis = LocalOptimizer().optimize(sql_info, schema)
            warnings = [p.description for p in analysis.problems]

        # 5. 表名识别失败提示
        if not nl_query.tables or "unknown_table" in nl_query.tables:
            warnings.append(
                "未能识别表名，已使用 unknown_table 占位，请补充表名或检查数据库 schema。")

        # 6. 执行查询（可选）
        columns: list[str] = []
        rows: list[tuple] = []
        executed = False
        error = ""
        if execute and not self.config.mock and self.db.is_connected():
            try:
                columns, rows = self.db.query_with_columns(sql)
                executed = True
            except Exception as e:  # noqa: BLE001 - 执行失败仅记录，不中断
                logger.warning("执行生成的 SQL 失败: %s", e)
                error = str(e)

        return NLQueryResult(
            nl_query=nl_query,
            generated_sql=sql,
            columns=columns,
            rows=rows,
            warnings=warnings,
            executed=executed,
            error=error,
        )
