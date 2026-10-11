"""深分页规则：LIMIT offset,n 中 offset 过大。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_PAT = re.compile(r"\bLIMIT\s+(\d+)\s*,\s*(\d+)", re.IGNORECASE)
_OFFSET_THRESHOLD = 1000


class DeepPaginationRule(Rule):
    name = "deep_pagination"
    risk = "safe"  # 自动改写需主键信息，本期仅建议

    def check(self, ctx: RuleContext) -> list[Problem]:
        m = _PAT.search(ctx.sql_info.raw_sql or "")
        if not m or int(m.group(1)) < _OFFSET_THRESHOLD:
            return []
        table = ctx.sql_info.tables[0] if ctx.sql_info.tables else ""
        return [Problem(severity="warning", table=table,
                        description=f"深分页 LIMIT {m.group(1)}, {m.group(2)}，offset 越大越慢",
                        suggestion="改用基于主键/游标的续页，或延迟关联（先用覆盖索引取主键再 JOIN）")]
