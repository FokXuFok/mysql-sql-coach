"""实体映射器：把 `NLEntity` 规整成安全的 SQL 片段。

条件实体的 `mapped` 已由 extractor 生成（形如 `col op value`），
这里做两件事：
1. 规整首尾空白；
2. 对字符串字面量转义单引号（`'` → `''`），避免 SQL 注入或语法错误。
"""
from ..models import NLEntity

_QUOTE = "'"


class EntityMapper:
    """`NLEntity` → SQL 片段的映射与转义。"""

    def condition(self, entity: NLEntity) -> str:
        """映射 WHERE 条件片段，并转义其中的字符串字面量。"""
        return self.escape_literal((entity.mapped or "").strip())

    def aggregate(self, entity: NLEntity) -> str:
        """映射聚合片段（如 `SUM(amount)`）。"""
        return (entity.mapped or "").strip()

    def order(self, entity: NLEntity) -> str:
        """映射排序片段（如 `amount DESC`）。"""
        return (entity.mapped or "").strip()

    @staticmethod
    def escape_string(value: str) -> str:
        """转义字符串值中的单引号：`'` → `''`。"""
        return (value or "").replace("'", "''")

    def escape_literal(self, fragment: str) -> str:
        """把片段中最外层单引号内的内容转义。

        例如 `status = 'O'Brien'` → `status = 'O''Brien'`；
        没有成对引号时原样返回。
        """
        first = fragment.find(_QUOTE)
        last = fragment.rfind(_QUOTE)
        if first == -1 or last <= first:
            return fragment
        inner = fragment[first + 1:last]
        return fragment[:first + 1] + self.escape_string(inner) + fragment[last:]
