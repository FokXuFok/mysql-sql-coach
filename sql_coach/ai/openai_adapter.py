# sql_coach/ai/openai_adapter.py
"""OpenAI API adapter."""
import logging
import time
from typing import Optional

from openai import OpenAI

from ..models import SQLInfo, ExplainResult, AnalysisResult, Problem
from .base import AIEngine
from .deepseek import _build_user_message, _parse_ai_response, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class OpenAIEngine(AIEngine):
    """OpenAI GPT-4o engine."""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1",
                 model: str = "gpt-4o", max_retries: int = 3):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.max_retries = max_retries

    def name(self) -> str:
        return "openai"

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
                logger.warning(f"OpenAI API attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(1)

        return AnalysisResult(
            problems=[Problem(
                severity="critical", table="",
                description=f"OpenAI API 失败: {last_error}",
                suggestion="检查 API Key"
            )],
            optimized_sql=sql_info.raw_sql,
            index_ddls=[],
            explanation=f"AI 调用失败: {last_error}",
        )
