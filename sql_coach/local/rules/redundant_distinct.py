"""冗余 DISTINCT 规则：SELECT DISTINCT 与 GROUP BY 同时出现时 DISTINCT 通常冗余。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_DISTINCT_PAT = re.compile(r"\bSELECT\s+DISTINCT\b", re.IGNORECASE)
_GROUP_BY_PAT = re.compile(r"\bGROUP\s+BY\b", re.IGNORECASE)


class RedundantDistinctRule(Rule):
    name = "redundant_distinct"
    risk = "safe"

    def check(self, ctx: RuleContext) -> list[Problem]:
        sql = ctx.sql_info.raw_sql or ""
        if not (_DISTINCT_PAT.search(sql) and _GROUP_BY_PAT.search(sql)):
            return []
        table = ctx.sql_info.tables[0] if ctx.sql_info.tables else ""
        return [Problem(severity="info", table=table,
                        description="同时使用 SELECT DISTINCT 与 GROUP BY，DISTINCT 通常冗余",
                        suggestion="去掉 DISTINCT，GROUP BY 已保证分组去重")]
