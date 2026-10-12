"""冗余 DISTINCT 规则：同层 SELECT DISTINCT 与 GROUP BY 同时出现时 DISTINCT 通常冗余。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_DISTINCT_PAT = re.compile(r"\bSELECT\s+DISTINCT\b", re.IGNORECASE)
_GROUP_BY_PAT = re.compile(r"\bGROUP\s+BY\b", re.IGNORECASE)
# 保守判断嵌套子查询：存在 (SELECT 时无法可靠确认 DISTINCT 与 GROUP BY 是否同层
_SUBQUERY_PAT = re.compile(r"\(\s*SELECT\b", re.IGNORECASE)


class RedundantDistinctRule(Rule):
    name = "redundant_distinct"
    risk = "safe"

    def check(self, ctx: RuleContext) -> list[Problem]:
        sql = ctx.sql_info.clean_sql
        # 含嵌套子查询时，DISTINCT 与 GROUP BY 可能分处内外层，宁可漏报也不误报
        if _SUBQUERY_PAT.search(sql):
            return []
        if not (_DISTINCT_PAT.search(sql) and _GROUP_BY_PAT.search(sql)):
            return []
        table = ctx.sql_info.tables[0] if ctx.sql_info.tables else ""
        return [Problem(severity="info", table=table,
                        description="同时使用 SELECT DISTINCT 与 GROUP BY，DISTINCT 通常冗余",
                        suggestion="去掉 DISTINCT，GROUP BY 已保证分组去重")]
