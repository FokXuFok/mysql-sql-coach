# sql_coach/ai/deepseek.py
"""DeepSeek AI engine implementation."""
import json
import logging
import re
import time
from typing import Optional

from openai import OpenAI

from ..models import SQLInfo, ExplainResult, AnalysisResult, Problem
from .base import AIEngine

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是 MySQL 优化专家。分析用户的 SQL 和 EXPLAIN 结果，给出优化建议。

必须返回 JSON 格式：
{
  "problems": [
    {"severity": "critical|warning|info", "table": "表名",
     "description": "问题描述", "suggestion": "改进建议"}
  ],
  "optimized_sql": "优化后的 SQL 语句",
  "index_ddls": ["CREATE INDEX ...", ...],
  "explanation": "自然语言解释"
}

只返回 JSON，不要其他文字。"""


def _build_user_message(sql_info: SQLInfo, explain_result: Optional[ExplainResult]) -> str:
    parts = [f"SQL: {sql_info.raw_sql}"]
    parts.append(f"SQL 类型: {sql_info.sql_type}")
    if sql_info.tables:
        parts.append(f"表: {', '.join(sql_info.tables)}")
    if sql_info.columns:
        parts.append(f"列: {', '.join(sql_info.columns)}")
    if sql_info.where_conditions:
        parts.append(f"WHERE: {' AND '.join(sql_info.where_conditions)}")
    if sql_info.order_by:
        parts.append(f"ORDER BY: {', '.join(sql_info.order_by)}")

    if explain_result:
        parts.append("\nEXPLAIN 结果:")
        for row in explain_result.rows:
            parts.append(
                f"  - 表={row.table} type={row.type} key={row.key} "
                f"rows={row.rows} extra={row.extra}"
            )
        if explain_result.problems:
            parts.append("已识别问题: " + "; ".join(explain_result.problems))
    else:
        parts.append("\n(无 EXPLAIN 结果，请基于 SQL 结构推理)")

    return "\n".join(parts)


def _parse_ai_response(content: str, fallback_sql: str) -> AnalysisResult:
    """Parse AI response JSON. Fall back to basic result on error."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        # Try to extract JSON from text
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return AnalysisResult(
                    problems=[], optimized_sql=fallback_sql,
                    index_ddls=[], explanation="AI 返回格式异常，使用原始 SQL"
                )
        else:
            return AnalysisResult(
                problems=[], optimized_sql=fallback_sql,
                index_ddls=[], explanation="AI 返回格式异常，使用原始 SQL"
            )

    problems = []
    for p in data.get("problems", []):
        problems.append(Problem(
            severity=p.get("severity", "info"),
            table=p.get("table", ""),
            description=p.get("description", ""),
            suggestion=p.get("suggestion", ""),
        ))

    return AnalysisResult(
        problems=problems,
        optimized_sql=data.get("optimized_sql", fallback_sql),
        index_ddls=data.get("index_ddls", []),
        explanation=data.get("explanation", ""),
    )


class DeepSeekEngine(AIEngine):
    """DeepSeek AI engine."""

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com",
                 model: str = "deepseek-chat", max_retries: int = 3):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.max_retries = max_retries

    def name(self) -> str:
        return "deepseek"

    def analyze(
        self,
        sql_info: SQLInfo,
        explain_result: Optional[ExplainResult],
    ) -> AnalysisResult:
        user_message = _build_user_message(sql_info, explain_result)

        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content
                return _parse_ai_response(content, sql_info.raw_sql)
            except Exception as e:
                last_error = e
                logger.warning(f"DeepSeek API attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(1)

        return AnalysisResult(
            problems=[Problem(
                severity="critical", table="",
                description=f"AI 调用失败: {last_error}",
                suggestion="检查 API Key 和网络"
            )],
            optimized_sql=sql_info.raw_sql,
            index_ddls=[],
            explanation=f"AI 调用失败: {last_error}",
        )
