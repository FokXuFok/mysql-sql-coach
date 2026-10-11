"""无 LIMIT 规则：无 WHERE 且无 LIMIT 的查询可能返回大量数据。"""
from ...models import Problem
from .base import Rule, RuleContext


class NoLimitRule(Rule):
    name = "no_limit"
    risk = "safe"

    def check(self, ctx: RuleContext) -> list[Problem]:
        info = ctx.sql_info
        if info.sql_type != "SELECT" or not info.tables or info.where_conditions:
            return []
        if "LIMIT" in (info.raw_sql or "").upper():
            return []
        return [Problem(severity="info", table=info.tables[0],
                        description="查询无 WHERE 且无 LIMIT，可能返回大量数据",
                        suggestion="确认是否需要全量返回；如只需部分数据请加 LIMIT")]
