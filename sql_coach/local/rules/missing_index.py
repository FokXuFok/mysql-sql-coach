"""缺索引规则：WHERE 条件列缺索引时建议建索引。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_OP_SPLIT = re.compile(
    r"\s*(?:=|>=|<=|<>|!=|>|<|\bLIKE\b|\bIN\b|\bBETWEEN\b)", re.IGNORECASE)
_IDENT = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)?$")


class MissingIndexRule(Rule):
    name = "missing_index"
    risk = "safe"

    def check(self, ctx: RuleContext) -> list[Problem]:
        table = self._table(ctx)
        if not table:
            return []
        verified = ctx.schema.has_table(table)
        out = []
        for col in self._columns(ctx):
            desc = (f"WHERE 条件列 {col} 缺少索引" if verified
                    else f"WHERE 条件列 {col} 疑似缺少索引（未连接数据库校验）")
            out.append(Problem(severity="critical", table=table, description=desc,
                               suggestion=f"在 {table}({col}) 上创建索引"))
        return out

    def ddls(self, ctx: RuleContext) -> list[str]:
        table = self._table(ctx)
        if not table:
            return []
        return [f"CREATE INDEX idx_{table}_{col} ON {table}({col});"
                for col in self._columns(ctx)]

    def _table(self, ctx: RuleContext):
        # 多表 JOIN 时无法判断条件列归属哪张表，保守跳过（避免 DDL 指错表）
        if len(ctx.sql_info.tables) != 1:
            return ""
        return ctx.sql_info.tables[0]

    def _columns(self, ctx: RuleContext) -> list[str]:
        table = self._table(ctx)
        out, seen = [], set()
        for cond in ctx.sql_info.where_conditions:
            col = self._column(cond)
            if not col or col in seen:
                continue
            if ctx.schema and ctx.schema.has_index_on(table, col):
                continue
            seen.add(col)
            out.append(col)
        return out

    @staticmethod
    def _column(cond: str) -> "str | None":
        left = _OP_SPLIT.split(cond, maxsplit=1)[0].strip().strip("` ")
        if not _IDENT.match(left):
            return None
        return left.split(".")[-1]
