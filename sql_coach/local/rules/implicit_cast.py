"""隐式类型转换规则：字符串列与数字比较（需 schema 已知列类型）。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_PAT = re.compile(r"([A-Za-z_]\w*)\s*=\s*(\d+)")
_STR_TYPES = ("varchar", "char", "text", "tinytext", "mediumtext", "longtext")


class ImplicitCastRule(Rule):
    name = "implicit_cast"
    risk = "safe"

    def check(self, ctx: RuleContext) -> list[Problem]:
        if not ctx.sql_info.tables:
            return []
        table = ctx.sql_info.tables[0]
        if not ctx.schema.has_table(table):
            return []
        out = []
        for cond in ctx.sql_info.where_conditions:
            m = _PAT.search(cond)
            if not m:
                continue
            col = m.group(1)
            ctype = ctx.schema.column_type(table, col)
            if ctype and ctype in _STR_TYPES:
                out.append(Problem(severity="warning", table=table,
                                   description=f"字符串列 {col} 与数字比较，可能触发隐式类型转换",
                                   suggestion=f"为 {col} 的比较值加引号，避免索引失效"))
        return out
