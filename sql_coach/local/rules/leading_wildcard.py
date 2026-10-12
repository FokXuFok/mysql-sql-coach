"""前导通配规则：LIKE '%x' 无法使用索引。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_PAT = re.compile(r"\bLIKE\s+'%", re.IGNORECASE)


class LeadingWildcardRule(Rule):
    name = "leading_wildcard"
    risk = "safe"

    def check(self, ctx: RuleContext) -> list[Problem]:
        if not _PAT.search(ctx.sql_info.raw_sql or ""):
            return []
        table = ctx.sql_info.tables[0] if ctx.sql_info.tables else ""
        return [Problem(severity="warning", table=table,
                        description="LIKE 以 % 开头，无法使用索引",
                        suggestion="改为后缀匹配，或使用全文索引 / 反向列")]
