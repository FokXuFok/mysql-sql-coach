"""Abstract AI engine interface."""
from abc import ABC, abstractmethod
from typing import Callable, Optional

from ..models import SQLInfo, ExplainResult, AnalysisResult


class AIEngine(ABC):
    """Abstract base class for AI engines."""

    @abstractmethod
    def analyze(
        self,
        sql_info: SQLInfo,
        explain_result: Optional[ExplainResult],
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> AnalysisResult:
        """Analyze SQL and return optimization suggestions.

        If on_chunk is provided, the engine should stream output chunks
        via the callback as they arrive from the AI model.
        """
        ...

    @abstractmethod
    def name(self) -> str:
        """Return the engine name."""
        ...
