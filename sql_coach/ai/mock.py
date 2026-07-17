"""Mock AI engine for mock mode (no real API calls)."""
from typing import Callable, Optional

from ..models import SQLInfo, ExplainResult, AnalysisResult, Problem
from .base import AIEngine


class MockAIEngine(AIEngine):
    """Returns canned analysis results without calling any API."""

    def name(self) -> str:
        return "mock"

    def analyze(
        self,
        sql_info: SQLInfo,
        explain_result: Optional[ExplainResult],
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> AnalysisResult:
        """Return a demo analysis result based on SQL structure."""
        problems = []
        index_ddls = []
        optimized = sql_info.raw_sql

        # Demo: flag SELECT * as a problem
        if sql_info.columns == ["*"] and sql_info.tables:
            table = sql_info.tables[0]
            problems.append(Problem(
                severity="warning",
                table=table,
                description="使用了 SELECT *",
                suggestion="只查询需要的列，减少数据传输",
            ))

        # Demo: flag WHERE without index hint
        if sql_info.where_conditions and sql_info.tables:
            table = sql_info.tables[0]
            # Try to extract column from first WHERE condition (best effort)
            cond = sql_info.where_conditions[0]
            col = ""
            for sep in ["=", ">", "<", " LIKE ", " IN "]:
                if sep in cond:
                    col = cond.split(sep)[0].strip()
                    break
            if col:
                problems.append(Problem(
                    severity="critical",
                    table=table,
                    description=f"WHERE 条件列 {col} 可能缺少索引",
                    suggestion=f"在 {table}({col}) 上创建索引",
                ))
                index_ddls.append(
                    f"CREATE INDEX idx_{col} ON {table}({col});"
                )
                optimized = optimized.replace(
                    "SELECT *", f"SELECT id", 1
                ) if "SELECT *" in optimized else optimized

        return AnalysisResult(
            problems=problems,
            optimized_sql=optimized,
            index_ddls=index_ddls,
            explanation="(模拟模式) 以上为示例分析结果，未调用真实 AI。",
        )
