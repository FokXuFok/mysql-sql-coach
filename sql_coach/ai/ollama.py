# sql_coach/ai/ollama.py
"""Ollama local AI engine adapter."""
import logging
import time
from typing import Optional

import httpx

from ..models import SQLInfo, ExplainResult, AnalysisResult, Problem
from .base import AIEngine
from .deepseek import _build_user_message, _parse_ai_response, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class OllamaEngine(AIEngine):
    """Ollama local engine."""

    def __init__(self, url: str = "http://localhost:11434",
                 model: str = "qwen2.5:14b", max_retries: int = 3):
        self.url = url.rstrip("/")
        self.model = model
        self.max_retries = max_retries

    def name(self) -> str:
        return "ollama"

    def analyze(
        self,
        sql_info: SQLInfo,
        explain_result: Optional[ExplainResult],
    ) -> AnalysisResult:
        user_message = _build_user_message(sql_info, explain_result)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }

        last_error = None
        with httpx.Client(timeout=60.0) as client:
            for attempt in range(self.max_retries):
                try:
                    response = client.post(
                        f"{self.url}/api/chat",
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                    content = data.get("message", {}).get("content", "")
                    return _parse_ai_response(content, sql_info.raw_sql)
                except Exception as e:
                    last_error = e
                    logger.warning(f"Ollama attempt {attempt + 1} failed: {e}")
                    if attempt < self.max_retries - 1:
                        time.sleep(1)

        return AnalysisResult(
            problems=[Problem(
                severity="critical", table="",
                description=f"Ollama 调用失败: {last_error}",
                suggestion="检查 Ollama 是否启动"
            )],
            optimized_sql=sql_info.raw_sql,
            index_ddls=[],
            explanation=f"AI 调用失败: {last_error}",
        )
