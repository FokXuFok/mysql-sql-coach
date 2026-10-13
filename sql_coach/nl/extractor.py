"""从分词结果中提取结构化实体：表名、列名、条件、聚合、排序、分组、LIMIT。"""
import re

from ..models import NLEntity, NLQuery
from .dictionary import SchemaDictionary


class EntityExtractor:
    """从分词结果提取表名、列名、条件、聚合、排序、LIMIT。"""

    ORDER_KEYWORDS = {
        "最高": "DESC", "最大": "DESC", "最近": "DESC", "最新": "DESC", "倒序": "DESC",
        "最低": "ASC", "最小": "ASC", "最早": "ASC", "正序": "ASC",
    }
    AGGREGATE_MAP = {
        "销售额": "SUM", "总计": "SUM", "总和": "SUM", "总额": "SUM",
        "平均": "AVG", "均值": "AVG",
        "数量": "COUNT", "总数": "COUNT", "计数": "COUNT",
        "最高": "MAX", "最低": "MIN",
    }
    GROUP_KEYWORDS = ("每个", "每种", "各类")
    LIMIT_PAT = re.compile(r"(\d+)\s*(条|个|行|记录|篇|名|位)")
    EQ_OPERATORS = ("为", "是", "等于", "=")
    CMP_OPERATORS = {
        "大于等于": ">=", "不小于": ">=", "小于等于": "<=", "不大于": "<=",
        "大于": ">", "超过": ">", "多于": ">", "高于": ">",
        "小于": "<", "低于": "<", "少于": "<",
    }
    TIME_SYNONYMS = ("时间", "日期")
    _NUMBER_PAT = re.compile(r"-?\d+(\.\d+)?")

    def __init__(self, dictionary: SchemaDictionary):
        self._dict = dictionary

    def extract(self, tokens: list[str], intent: str) -> NLQuery:
        """提取所有实体，返回 NLQuery。"""
        text = "".join(tokens)
        tables, columns = self._collect_tables_columns(tokens, text)
        aggregates = self._extract_aggregates(tokens, text)
        return NLQuery(
            intent=intent,
            tables=tables,
            columns=columns,
            conditions=self._extract_conditions(tokens),
            aggregates=aggregates,
            order_by=self._extract_order(text, columns, aggregates),
            group_by=list(columns) if any(k in text for k in self.GROUP_KEYWORDS) else [],
            limit=self._extract_limit(text),
            raw_text=text,
        )

    # ------------------------------------------------------------------ 表 / 列

    def _collect_tables_columns(self, tokens, text):
        tables: list[str] = []
        columns: list[str] = []
        seen_tables: set[str] = set()
        seen_columns: set[str] = set()

        def add(name: str) -> None:
            if self._dict.is_table(name):
                if name.lower() not in seen_tables:
                    seen_tables.add(name.lower())
                    tables.append(name)
            elif self._dict.is_column(name):
                if name.lower() not in seen_columns:
                    seen_columns.add(name.lower())
                    columns.append(name)

        # 1) 英文标识符按 token 精确匹配
        for token in tokens:
            resolved = self._dict.resolve(token)
            if resolved:
                add(resolved)
        # 2) 中文别名做子串匹配（jieba 可能把"用户数量"合成一个词）
        for alias in self._dict.jieba_words():
            if alias in text:
                resolved = self._dict.resolve(alias)
                if resolved:
                    add(resolved)
        return tables, columns

    # ------------------------------------------------------------------ 聚合

    def _extract_aggregates(self, tokens, text) -> list[NLEntity]:
        aggregates: list[NLEntity] = []
        seen: set[str] = set()
        for keyword, func in self.AGGREGATE_MAP.items():
            if keyword not in text:
                continue
            if keyword in self.ORDER_KEYWORDS:
                continue  # "最高/最低" 作为排序修饰，交由 ORDER BY 处理
            mapped = f"{func}({self._find_nearest_column(tokens, keyword)})"
            if mapped in seen:
                continue
            seen.add(mapped)
            aggregates.append(NLEntity(type="aggregate", raw=keyword,
                                       mapped=mapped, alias=keyword))
        return aggregates

    def _find_nearest_column(self, tokens, keyword) -> str:
        """聚合作用的列：优先关键词自身映射，其次就近的列 token，兜底 '*'。"""
        own = self._dict.resolve(keyword)
        if own and self._dict.is_column(own):
            return own
        try:
            idx = tokens.index(keyword)
        except ValueError:
            return "*"
        for token in tokens[idx + 1:]:
            resolved = self._dict.resolve(token)
            if resolved and self._dict.is_column(resolved):
                return resolved
        for token in reversed(tokens[:idx]):
            resolved = self._dict.resolve(token)
            if resolved and self._dict.is_column(resolved):
                return resolved
        return "*"

    # ------------------------------------------------------------------ 排序

    def _extract_order(self, text, columns, aggregates) -> list[NLEntity]:
        for keyword, direction in self.ORDER_KEYWORDS.items():
            if keyword not in text:
                continue
            sort_col = self._find_sort_column(keyword, columns, aggregates)
            if not sort_col:
                continue
            return [NLEntity(type="order", raw=keyword,
                             mapped=f"{sort_col} {direction}", alias=keyword)]
        return []

    def _find_sort_column(self, keyword, columns, aggregates) -> str:
        if aggregates:
            return aggregates[0].mapped
        if columns:
            return columns[0]
        if keyword in ("最近", "最新", "最早"):
            for synonym in self.TIME_SYNONYMS:
                resolved = self._dict.resolve(synonym)
                if resolved and self._dict.is_column(resolved):
                    return resolved
        return ""

    # ------------------------------------------------------------------ LIMIT

    def _extract_limit(self, text):
        match = self.LIMIT_PAT.search(text)
        return int(match.group(1)) if match else None

    # ------------------------------------------------------------------ 条件

    def _extract_conditions(self, tokens) -> list[NLEntity]:
        conditions: list[NLEntity] = []
        for i, token in enumerate(tokens):
            if token in self.EQ_OPERATORS:
                op = "="
            elif token in self.CMP_OPERATORS:
                op = self.CMP_OPERATORS[token]
            else:
                continue
            if i - 1 < 0 or i + 1 >= len(tokens):
                continue
            column = self._dict.resolve(tokens[i - 1])
            if not column or not self._dict.is_column(column):
                continue
            value = tokens[i + 1]
            conditions.append(NLEntity(
                type="condition",
                raw=f"{tokens[i - 1]}{token}{value}",
                mapped=f"{column} {op} {self._format_value(value)}",
            ))
        return conditions

    def _format_value(self, value: str) -> str:
        if self._NUMBER_PAT.fullmatch(value):
            return value
        return f"'{value}'"
