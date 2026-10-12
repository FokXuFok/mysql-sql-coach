"""本地规则引擎：汇总所有规则，产出与 AI 一致的 AnalysisResult。"""
import logging
from dataclasses import replace

from ..models import SQLInfo, AnalysisResult
from .schema import Schema
from .rules.base import Rule, RuleContext
from .rules.missing_index import MissingIndexRule
from .rules.select_star import SelectStarRule
from .rules.leading_wildcard import LeadingWildcardRule
from .rules.function_on_column import FunctionOnColumnRule
from .rules.implicit_cast import ImplicitCastRule
from .rules.no_limit import NoLimitRule
from .rules.deep_pagination import DeepPaginationRule
from .rules.or_condition import OrConditionRule
from .rules.subquery_to_join import SubqueryToJoinRule
from .rules.negation import NegationRule
from .rules.order_by_rand import OrderByRandRule
from .rules.union_dedup import UnionDedupRule
from .rules.redundant_distinct import RedundantDistinctRule

logger = logging.getLogger(__name__)

DEFAULT_RULES = [
    MissingIndexRule(), SelectStarRule(), LeadingWildcardRule(),
    FunctionOnColumnRule(), ImplicitCastRule(), NoLimitRule(),
    DeepPaginationRule(), OrConditionRule(), SubqueryToJoinRule(),
    NegationRule(), OrderByRandRule(), UnionDedupRule(), RedundantDistinctRule(),
]


class LocalOptimizer:
    """遍历规则，汇总 problems / index_ddls / optimized_sql。"""

    def __init__(self, rules: list[Rule] | None = None):
        self.rules = list(rules) if rules is not None else list(DEFAULT_RULES)

    def optimize(self, sql_info: SQLInfo, schema: Schema) -> AnalysisResult:
        ctx = RuleContext(sql_info=sql_info, schema=schema)
        problems, ddls, hit = [], [], []
        optimized = sql_info.raw_sql

        for rule in self.rules:
            found = self._safe(lambda: rule.check(ctx), rule.name, "check", [])
            if found:
                problems.extend(found)
                hit.append(rule.name)
            new_sql = self._safe(lambda: rule.rewrite(ctx), rule.name, "rewrite", None)
            if new_sql and new_sql != ctx.sql_info.raw_sql:
                optimized = new_sql
                # 用改写后的 SQL 重建上下文，让后续规则在同一份 SQL 上叠加，而不是互相覆盖
                ctx = RuleContext(
                    sql_info=replace(ctx.sql_info, raw_sql=new_sql), schema=schema)
                if rule.name not in hit:
                    hit.append(rule.name)
            ddls.extend(self._safe(lambda: rule.ddls(ctx), rule.name, "ddls", []))

        return AnalysisResult(
            problems=problems,
            optimized_sql=optimized,
            index_ddls=ddls,
            explanation=self._explain(hit, sql_info, schema),
        )

    @staticmethod
    def _safe(fn, rule_name, phase, default):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - 单条规则异常不影响整体
            logger.warning("规则 %s 的 %s 阶段异常: %s", rule_name, phase, e)
            return default

    @staticmethod
    def _explain(hit: list[str], sql_info: SQLInfo, schema: Schema) -> str:
        if not hit:
            return "本地规则引擎：未发现明显问题。"
        table = sql_info.tables[0] if sql_info.tables else ""
        verified = bool(table) and schema.has_table(table)
        has_index_rule = any("missing_index" in h for h in hit)
        note = ("（未连接数据库，索引相关结论未校验）"
                if has_index_rule and not verified else "")
        return "本地规则引擎命中规则: " + ", ".join(hit) + note
