"""函数包裹索引列规则：DATE(col)='...' 会使索引失效，可安全改写为范围条件。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_CHECK_PAT = re.compile(
    r"\b(DATE|YEAR|MONTH|DAY|UPPER|LOWER|SUBSTRING|SUBSTR|CAST)\s*\(\s*"
    r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\)",
    re.IGNORECASE)
_DATE_EQ_PAT = re.compile(
    r"\bDATE\s*\(\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\)\s*=\s*'(\d{4}-\d{2}-\d{2})'",
    re.IGNORECASE)


class FunctionOnColumnRule(Rule):
    name = "function_on_column"
    risk = "rewrite"

    def check(self, ctx: RuleContext) -> list[Problem]:
        out = []
        for cond in ctx.sql_info.where_conditions:
            m = _CHECK_PAT.search(cond)
            if m:
                table = ctx.sql_info.tables[0] if ctx.sql_info.tables else ""
                out.append(Problem(
                    severity="warning", table=table,
                    description=f"条件对列使用了函数 {m.group(1)}({m.group(2)})，索引会失效",
                    suggestion=f"改写为对 {m.group(2)} 的范围条件，使其可用索引"))
        return out

    def rewrite(self, ctx: RuleContext) -> str | None:
        sql = ctx.sql_info.raw_sql or ""
        if not sql:
            return None

        def repl(m):
            col, day = m.group(1), m.group(2)
            return (f"({col} >= '{day} 00:00:00' "
                    f"AND {col} < DATE_ADD('{day}', INTERVAL 1 DAY))")

        new_sql, n = _DATE_EQ_PAT.subn(repl, sql)
        return new_sql if n else None
