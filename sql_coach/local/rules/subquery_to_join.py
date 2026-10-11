"""子查询规则：IN (SELECT ...) 建议改写为 JOIN / EXISTS。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_PAT = re.compile(r"\bIN\s*\(\s*SELECT\b", re.IGNORECASE)


class SubqueryToJoinRule(Rule):
    name = "subquery_to_join"
    risk = "safe"  # JOIN 改写可能产生重复行，本期仅建议

    def check(self, ctx: RuleContext) -> list[Problem]:
        if not _PAT.search(ctx.sql_info.raw_sql or ""):
            return []
        table = ctx.sql_info.tables[0] if ctx.sql_info.tables else ""
        return [Problem(severity="warning", table=table,
                        description="使用 IN (SELECT ...) 子查询，可能执行效率较低",
                        suggestion="改写为 JOIN 或 EXISTS（注意去重语义）")]
