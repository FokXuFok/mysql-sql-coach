"""否定条件规则：WHERE 含 !=/<>/NOT IN/NOT LIKE/NOT EXISTS，通常无法有效使用索引。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

# 显式枚举否定运算符，而非裸匹配 \bNOT\b：这样 IS NOT NULL 不会被误判为否定条件。
# != / <> 均为两字符运算符，不会成为其它运算符（如 <=>、>=）的子串，天然具备词法边界。
_NEG_PAT = re.compile(r"!=|<>|\bNOT\s+(?:IN|LIKE|EXISTS)\b", re.IGNORECASE)


class NegationRule(Rule):
    name = "negation"
    risk = "safe"  # 正向改写可能改变语义（尤其 NULL 语义），本期仅建议

    def check(self, ctx: RuleContext) -> list[Problem]:
        if not _NEG_PAT.search(ctx.sql_info.raw_sql or ""):
            return []
        table = ctx.sql_info.tables[0] if ctx.sql_info.tables else ""
        return [Problem(severity="warning", table=table,
                        description="WHERE 条件包含否定条件（!=/<>/NOT IN/NOT LIKE/NOT EXISTS），"
                                    "通常无法有效使用索引，可能导致全表扫描",
                        suggestion="若语义允许，改写为正向等值/范围条件，"
                                   "或用 EXISTS/IN 的等价形式")]
