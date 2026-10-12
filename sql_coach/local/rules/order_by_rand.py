"""随机排序规则：ORDER BY RAND() 会对全表做随机排序，数据量大时性能极差。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

# 兼容大小写与 RAND() 前后空格
_PAT = re.compile(r"\bORDER\s+BY\s+RAND\s*\(\s*\)", re.IGNORECASE)


class OrderByRandRule(Rule):
    name = "order_by_rand"
    risk = "safe"  # 随机取数需在应用层或改用主键区间，本期仅建议

    def check(self, ctx: RuleContext) -> list[Problem]:
        sql = ctx.sql_info.clean_sql
        if not _PAT.search(sql):
            return []
        table = ctx.sql_info.tables[0] if ctx.sql_info.tables else ""
        return [Problem(severity="warning", table=table,
                        description="ORDER BY RAND() 会对全表做随机排序，数据量大时性能极差",
                        suggestion="改为先按主键/范围取出候选集，再在应用层随机，"
                                   "或使用随机主键区间")]
