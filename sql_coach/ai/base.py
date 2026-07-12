# sql_coach/ai/base.py
"""Abstract AI engine interface."""
from abc import ABC, abstractmethod
from typing import Optional

from ..models import SQLInfo, ExplainResult, AnalysisResult


class AIEngine(ABC):
    """Abstract base class for AI engines."""

    @abstractmethod
    def analyze(
        self,
        sql_info: SQLInfo,
        explain_result: Optional[ExplainResult],
    ) -> AnalysisResult:
        """Analyze SQL and return optimization suggestions."""
        ...

    @abstractmethod
    def name(self) -> str:
        """Return the engine name."""
        ...
