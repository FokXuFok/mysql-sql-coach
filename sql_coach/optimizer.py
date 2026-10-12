"""优化器分流：本地规则引擎 vs AI 引擎，产出同一种 AnalysisResult。"""
from typing import Callable, Optional

from .models import Config, SQLInfo, ExplainResult, AnalysisResult, Complexity
from .local.engine import LocalOptimizer
from .local.schema import Schema


class AIOptimizerAdapter:
    """把现有 AIEngine 适配成统一 Optimizer 接口。"""

    def __init__(self, engine):
        self.engine = engine

    def name(self) -> str:
        return self.engine.name()

    def optimize(self, sql_info: SQLInfo, explain_result: Optional[ExplainResult],
                 schema: Schema, on_chunk: Optional[Callable[[str], None]] = None) -> AnalysisResult:
        return self.engine.analyze(sql_info, explain_result, on_chunk=on_chunk)


class LocalOptimizerAdapter:
    """把 LocalOptimizer 适配成统一 Optimizer 接口。"""

    def __init__(self, engine: Optional[LocalOptimizer] = None):
        self.engine = engine or LocalOptimizer()

    def name(self) -> str:
        return "local"

    def optimize(self, sql_info: SQLInfo, explain_result: Optional[ExplainResult],
                 schema: Schema, on_chunk: Optional[Callable[[str], None]] = None) -> AnalysisResult:
        return self.engine.optimize(sql_info, schema)


def select_optimizer(config: Config, complexity: Optional[Complexity],
                     ai_factory: Callable[[], object]):
    """返回 (optimizer, engine_name)。

    ai_factory 是零参可调用对象，只在真正需要 AI 时才被调用，
    这样纯本地模式下不会创建 AI 客户端（也就不需要 API Key）。
    """
    mode = (getattr(config, "optimizer_mode", "auto") or "auto").lower()
    if mode == "local":
        return LocalOptimizerAdapter(), "local"
    if mode == "ai":
        engine = ai_factory()
        return AIOptimizerAdapter(engine), engine.name()
    # auto
    if complexity is not None and complexity.level in ("simple", "medium"):
        return LocalOptimizerAdapter(), "local"
    engine = ai_factory()
    return AIOptimizerAdapter(engine), engine.name()
