"""UNION 去重规则：UNION 会对结果去重并排序，开销较大。"""
import re

from ...models import Problem
from .base import Rule, RuleContext
from ._text import clean

# 匹配 UNION 但排除 UNION ALL（负向先行断言允许 ALL 前有空格）
_PAT = re.compile(r"\bUNION\b(?!\s+ALL\b)", re.IGNORECASE)


class UnionDedupRule(Rule):
    name = "union_dedup"
    risk = "safe"  # 去重语义可能影响结果，本期仅建议

    def check(self, ctx: RuleContext) -> list[Problem]:
        sql = clean(ctx.sql_info.raw_sql or "")
        if not _PAT.search(sql):
            return []
        table = ctx.sql_info.tables[0] if ctx.sql_info.tables else ""
        return [Problem(severity="warning", table=table,
                        description="UNION 会对结果去重并排序，开销较大",
                        suggestion="若业务不要求去重，改用 UNION ALL")]
