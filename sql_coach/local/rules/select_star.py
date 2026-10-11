"""SELECT * 规则：有 schema 时展开为显式列，否则仅建议。"""
import re

from ...models import Problem
from .base import Rule, RuleContext


class SelectStarRule(Rule):
    name = "select_star"
    risk = "rewrite"

    def check(self, ctx: RuleContext) -> list[Problem]:
        info = ctx.sql_info
        if info.sql_type == "SELECT" and info.columns == ["*"] and info.tables:
            return [Problem(severity="warning", table=info.tables[0],
                            description="使用了 SELECT *，会读取全部列",
                            suggestion="只查询需要的列，减少数据传输与回表成本")]
        return []

    def rewrite(self, ctx: RuleContext) -> str | None:
        info = ctx.sql_info
        if info.columns != ["*"] or not info.tables or not ctx.schema:
            return None
        table = info.tables[0]
        ts = ctx.schema.tables.get(table.lower())
        if ts is None or not ts.columns:
            return None
        cols = ", ".join(ts.columns.keys())
        return re.sub(r"(?i)\bSELECT\s+\*", f"SELECT {cols}", info.raw_sql, count=1)
