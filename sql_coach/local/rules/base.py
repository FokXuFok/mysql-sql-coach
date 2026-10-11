"""本地优化规则的抽象基类与上下文。"""
from abc import ABC
from dataclasses import dataclass
from typing import Optional

from ...models import SQLInfo, Problem
from ..schema import Schema


@dataclass
class RuleContext:
    sql_info: SQLInfo
    schema: Schema


class Rule(ABC):
    """一条本地优化规则。risk: safe（仅建议）/ rewrite（会改写 SQL）。"""

    name: str = ""
    risk: str = "safe"

    def check(self, ctx: RuleContext) -> list[Problem]:
        return []

    def rewrite(self, ctx: RuleContext) -> Optional[str]:
        return None

    def ddls(self, ctx: RuleContext) -> list[str]:
        return []
