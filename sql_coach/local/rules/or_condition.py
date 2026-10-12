"""OR 条件规则：WHERE 含 OR 可能无法有效使用索引。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_PAT = re.compile(r"\bOR\b", re.IGNORECASE)


class OrConditionRule(Rule):
    name = "or_condition"
    risk = "safe"  # OR->UNION 存在语义风险，本期仅建议

    def check(self, ctx: RuleContext) -> list[Problem]:
        sql = ctx.sql_info.raw_sql or ""
        if not _PAT.search(sql) or len(ctx.sql_info.where_conditions) < 2:
            return []
        table = ctx.sql_info.tables[0] if ctx.sql_info.tables else ""
        return [Problem(severity="warning", table=table,
                        description="WHERE 中使用 OR，可能无法有效使用索引",
                        suggestion="若两侧列都有索引，可改写为 UNION ALL")]
