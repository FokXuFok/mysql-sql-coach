"""OpenAI API adapter."""
import logging
import time
from typing import Callable, Optional

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
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> AnalysisResult:
        user_message = _build_user_message(sql_info, explain_result)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
        last_error = None

        for attempt in range(self.max_retries):
            try:
                if on_chunk is not None:
                    stream = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=0.1,
                        response_format={"type": "json_object"},
                        stream=True,
                    )
                    content_parts = []
                    for chunk in stream:
                        if chunk.choices and chunk.choices[0].delta.content:
                            delta = chunk.choices[0].delta.content
                            content_parts.append(delta)
                            on_chunk(delta)
                    content = "".join(content_parts)
                else:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
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
