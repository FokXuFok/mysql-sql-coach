"""SQLBuilder：把 `NLQuery` 组装成完整的 SQL 字符串。

按文档 §4.7 的三类意图分流：
- count     → `SELECT COUNT(*) AS cnt ...`
- aggregate → 聚合列 + 普通列，无 group_by 时用普通列分组
- select    → 显式列查询

生成的 SQL 始终以 `;` 结尾，且可被 `sqlparse.parse()` 解析。
"""
from ..models import NLQuery
from . import templates
from .mapper import EntityMapper


class SQLBuilder:
    """根据 NLQuery 构建 SQL 字符串。"""

    def __init__(self, mapper: EntityMapper = None):
        self._mapper = mapper or EntityMapper()

    def build(self, nl_query: NLQuery) -> str:
        """按意图选择模板生成 SQL。"""
        intent = nl_query.intent
        if intent == "count":
            return self._build_count(nl_query)
        if intent == "aggregate":
            return self._build_aggregate(nl_query)
        return self._build_select(nl_query)

    # ------------------------------------------------------------------ 三类意图

    def _build_select(self, q: NLQuery) -> str:
        columns = ", ".join(q.columns) if q.columns else templates.ALL_COLUMNS
        return templates.render(
            templates.SELECT_TEMPLATE,
            columns=columns,
            table=self._table(q),
            where=self._build_where(q),
            order=self._build_order(q),
            limit=self._build_limit(q),
        )

    def _build_aggregate(self, q: NLQuery) -> str:
        agg_cols = [self._mapper.aggregate(a) for a in q.aggregates]
        plain_cols = list(q.columns)
        select_parts = plain_cols + agg_cols if plain_cols else agg_cols
        columns = ", ".join(select_parts) if select_parts else templates.ALL_COLUMNS
        # aggregates 为空时按普通 select 处理，不加 GROUP BY
        group_by = self._build_group(q, plain_cols) if q.aggregates else ""
        return templates.render(
            templates.AGGREGATE_TEMPLATE,
            columns=columns,
            table=self._table(q),
            where=self._build_where(q),
            group_by=group_by,
            order=self._build_order(q),
            limit=self._build_limit(q),
        )

    def _build_count(self, q: NLQuery) -> str:
        return templates.render(
            templates.COUNT_TEMPLATE,
            table=self._table(q),
            where=self._build_where(q),
        )

    # ------------------------------------------------------------------ 子句

    def _table(self, q: NLQuery) -> str:
        """取第一个识别到的表名；未识别时用 unknown_table 占位。"""
        return q.tables[0] if q.tables else templates.UNKNOWN_TABLE

    def _build_where(self, q: NLQuery) -> str:
        if not q.conditions:
            return ""
        parts = [self._mapper.condition(c) for c in q.conditions]
        return " WHERE " + " AND ".join(parts)

    def _build_group(self, q: NLQuery, plain_cols: list[str]) -> str:
        """聚合分组：优先显式 group_by，否则用普通列（文档 §4.7 行为）。"""
        group = list(q.group_by)
        if not group and plain_cols:
            group = plain_cols
        if not group:
            return ""
        return " GROUP BY " + ", ".join(group)

    def _build_order(self, q: NLQuery) -> str:
        if not q.order_by:
            return ""
        return " ORDER BY " + ", ".join(self._mapper.order(o) for o in q.order_by)

    def _build_limit(self, q: NLQuery) -> str:
        if q.limit is None:
            return ""
        return f" LIMIT {int(q.limit)}"
