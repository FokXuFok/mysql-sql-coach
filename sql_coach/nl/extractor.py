"""从分词结果中提取结构化实体：表名、列名、条件、聚合、排序、分组、LIMIT。"""
import re
from typing import Optional

from ..local.schema import Schema
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
    # 时间类排序关键词：应优先按时间列排序，而不是首列
    TIME_ORDER_KEYWORDS = ("最近", "最新", "最早")
    # 时间列的识别标记：列名包含其一即视为时间列
    TIME_COLUMN_MARKERS = ("created_at", "_at", "time", "date")
    # 数值单位换算
    UNIT_MULTIPLIERS = {"万": 10000, "千": 1000, "百": 100}
    _NUMBER_PAT = re.compile(r"-?\d+(\.\d+)?")
    _NUMBER_UNIT_PAT = re.compile(r"(-?\d+(?:\.\d+)?)(万|千|百)")
    # 带引号的字面量：贪婪匹配到最后一个同种引号，保留内部引号
    _QUOTED_LITERAL_PAT = re.compile(r"""^(['"])(.*)\1""", re.DOTALL)
    # 聚合片段（如 "SUM(amount)"）中的目标列
    _AGG_TARGET_PAT = re.compile(r"^\s*\w+\s*\(\s*([^)]*?)\s*\)\s*$")
    # 代表列候选：恰好 name / 以 _name 结尾 / 恰好 title
    _REPRESENTATIVE_SUFFIX = "_name"

    def __init__(self, dictionary: SchemaDictionary, schema: Optional[Schema] = None):
        self._dict = dictionary
        self._schema = schema

    def extract(self, tokens: list[str], intent: str) -> NLQuery:
        """提取所有实体，返回 NLQuery。"""
        text = "".join(tokens)
        tables, columns = self._collect_tables_columns(tokens, text)
        aggregates, skipped = self._extract_aggregates(tokens, text)
        conditions = self._extract_conditions(tokens, text)
        # 聚合目标列与 WHERE 条件列只参与对应子句，不作为 SELECT 列
        columns = self._drop_non_selected(columns, aggregates, conditions)
        group_by = list(columns) if any(k in text for k in self.GROUP_KEYWORDS) else []
        order_by = self._extract_order(text, columns, aggregates, tables)
        # 仅当聚合结果被排序时（"销售额最高的10个客户"这类 Top-N）才用表代表列分组；
        # 纯全局聚合（"用户的平均年龄"）不该带 GROUP BY，否则会答非所问。
        if aggregates and not columns and not group_by and order_by:
            representative = self._representative_column(tables)
            if representative:
                columns = [representative]
        nl_query = NLQuery(
            intent=intent,
            tables=tables,
            columns=columns,
            conditions=conditions,
            aggregates=aggregates,
            order_by=order_by,
            group_by=group_by,
            limit=self._extract_limit(text),
            raw_text=text,
            # 留痕：记录因缺少目标列而被跳过的非法聚合（如 SUM），供上层提示/排查
            skipped_aggregates=skipped,
        )
        return nl_query

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

    # ------------------------------------------------------------- 列过滤 / 代表列

    def _drop_non_selected(self, columns, aggregates, conditions) -> list[str]:
        """剔除只服务于聚合或 WHERE 的列，它们不应出现在 SELECT/GROUP BY。"""
        excluded = self._aggregate_targets(aggregates) | self._condition_columns(conditions)
        if not excluded:
            return columns
        return [c for c in columns if c.lower() not in excluded]

    @classmethod
    def _aggregate_targets(cls, aggregates) -> set[str]:
        """聚合函数参数中的列名（`SUM(amount)` → `amount`；`COUNT(*)` 忽略）。"""
        targets: set[str] = set()
        for agg in aggregates:
            match = cls._AGG_TARGET_PAT.match(agg.mapped or "")
            if not match:
                continue
            col = match.group(1).strip()
            if col and col != "*":
                targets.add(col.lower())
        return targets

    @staticmethod
    def _condition_columns(conditions) -> set[str]:
        """WHERE 条件片段左侧的列名（`status = 'pending'` → `status`）。"""
        columns: set[str] = set()
        for cond in conditions:
            head = (cond.mapped or "").split(None, 1)[0]
            if head:
                columns.add(head.lower())
        return columns

    def _representative_column(self, tables) -> Optional[str]:
        """选表代表列作分组依据：name → *_name → title；无合适列返回 None。"""
        if self._schema is None or not tables:
            return None
        table = self._schema.tables.get(tables[0].lower())
        if table is None:
            return None
        names = list(table.columns.keys())
        if "name" in names:
            return "name"
        for name in names:
            if name.endswith(self._REPRESENTATIVE_SUFFIX):
                return name
        if "title" in names:
            return "title"
        return None

    # ------------------------------------------------------------------ 聚合

    def _extract_aggregates(self, tokens, text) -> tuple[list[NLEntity], list[str]]:
        """提取聚合实体；非 COUNT 聚合缺少目标列时跳过，避免生成 `SUM(*)` 等非法 SQL。

        Returns:
            (aggregates, skipped)：skipped 为被跳过的聚合关键词，供上层留痕。
        """
        aggregates: list[NLEntity] = []
        skipped: list[str] = []
        seen: set[str] = set()
        for keyword, func in self.AGGREGATE_MAP.items():
            if keyword not in text:
                continue
            if keyword in self.ORDER_KEYWORDS:
                continue  # "最高/最低" 作为排序修饰，交由 ORDER BY 处理
            column = self._find_nearest_column(tokens, keyword)
            if func != "COUNT" and column == "*":
                # MySQL 里只有 COUNT(*) 合法，其余聚合缺目标列时宁可丢弃
                skipped.append(keyword)
                continue
            mapped = f"{func}({column})"
            if mapped in seen:
                continue
            seen.add(mapped)
            aggregates.append(NLEntity(type="aggregate", raw=keyword,
                                       mapped=mapped, alias=keyword))
        return aggregates, skipped

    def _find_nearest_column(self, tokens, keyword) -> str:
        """聚合作用的列：优先关键词自身映射，其次就近的列 token，兜底 '*'。"""
        own = self._dict.resolve(keyword)
        if own and self._dict.is_column(own):
            return own
        try:
            idx = tokens.index(keyword)
        except ValueError:
            # 关键词可能被 jieba 合成进某个词（如"平均年龄"含"平均"）：
            # 只在该合成词内部寻找目标列，避免误取远处无关的列。
            for token in tokens:
                if keyword in token:
                    return self._column_in_token(token) or "*"
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

    def _column_in_token(self, token: str) -> Optional[str]:
        """在合成词内部找列名（"平均年龄" → age）；找不到返回 None。"""
        for alias in self._dict.jieba_words():
            if alias in token:
                resolved = self._dict.resolve(alias)
                if resolved and self._dict.is_column(resolved):
                    return resolved
        return None

    # ------------------------------------------------------------------ 排序

    def _extract_order(self, text, columns, aggregates, tables) -> list[NLEntity]:
        for keyword, direction in self.ORDER_KEYWORDS.items():
            if keyword not in text:
                continue
            sort_col = self._find_sort_column(keyword, columns, aggregates, tables)
            if not sort_col:
                continue
            return [NLEntity(type="order", raw=keyword,
                             mapped=f"{sort_col} {direction}", alias=keyword)]
        return []

    def _find_sort_column(self, keyword, columns, aggregates, tables) -> str:
        if aggregates:
            return aggregates[0].mapped
        # 时间类排序（最近/最新/最早）优先取 schema 中的时间列
        if keyword in self.TIME_ORDER_KEYWORDS:
            time_col = self._find_time_column(tables)
            if time_col:
                return time_col
        if columns:
            return columns[0]
        if keyword in self.TIME_ORDER_KEYWORDS:
            for synonym in self.TIME_SYNONYMS:
                resolved = self._dict.resolve(synonym)
                if resolved and self._dict.is_column(resolved):
                    return resolved
        return ""

    def _find_time_column(self, tables) -> Optional[str]:
        """在 schema 中找时间列（列名含 created_at / _at / time / date）。"""
        if self._schema is None:
            return None
        names: list[str] = []
        for table_name in tables:
            table = self._schema.tables.get(table_name.lower())
            if table is not None:
                names.extend(table.columns.keys())
        if not names:
            # 未识别到表时退化为扫描整库，尽量找到时间列
            for table in self._schema.tables.values():
                names.extend(table.columns.keys())
        for marker in self.TIME_COLUMN_MARKERS:
            for name in names:
                if marker in name.lower():
                    return name
        return None

    # ------------------------------------------------------------------ LIMIT

    def _extract_limit(self, text):
        match = self.LIMIT_PAT.search(text)
        return int(match.group(1)) if match else None

    # ------------------------------------------------------------------ 条件

    def _extract_conditions(self, tokens, text) -> list[NLEntity]:
        conditions: list[NLEntity] = []
        offsets = self._token_offsets(tokens)
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
            # 等值条件且操作符后是带引号的字面量：取引号内完整内容
            quoted = None
            if op == "=":
                rest = text[offsets[i] + len(token):]
                quoted = self._match_quoted_literal(rest)
            if quoted is not None:
                conditions.append(NLEntity(
                    type="condition",
                    raw=f"{tokens[i - 1]}{token}{quoted}",
                    mapped=f"{column} {op} '{quoted}'",
                ))
                continue
            value = tokens[i + 1]
            unit_token = tokens[i + 2] if i + 2 < len(tokens) else ""
            conditions.append(NLEntity(
                type="condition",
                raw=f"{tokens[i - 1]}{token}{value}",
                mapped=f"{column} {op} {self._format_value(value, unit_token)}",
            ))
        return conditions

    @staticmethod
    def _token_offsets(tokens) -> list[int]:
        """每个 token 在 `"".join(tokens)` 中的起始下标。"""
        offsets: list[int] = []
        pos = 0
        for token in tokens:
            offsets.append(pos)
            pos += len(token)
        return offsets

    def _match_quoted_literal(self, rest: str) -> Optional[str]:
        """`为/是` 后是带引号字面量时，取引号内完整内容（贪婪匹配到最后一个引号）。"""
        if not rest:
            return None
        match = self._QUOTED_LITERAL_PAT.match(rest)
        return match.group(2) if match else None

    def _format_value(self, value: str, unit_token: str = "") -> str:
        number = self._to_number(value, unit_token)
        if number is not None:
            return number
        return f"'{value}'"

    def _to_number(self, value: str, unit_token: str = "") -> Optional[str]:
        """把数值（含万/千/百单位）规整成字符串；非数值返回 None。"""
        unit = ""
        if self._NUMBER_PAT.fullmatch(value):
            num = value
        else:
            match = self._NUMBER_UNIT_PAT.fullmatch(value)
            if not match:
                return None
            num, unit = match.group(1), match.group(2)
        if not unit and unit_token in self.UNIT_MULTIPLIERS:
            unit = unit_token
        if unit:
            scaled = float(num) * self.UNIT_MULTIPLIERS[unit]
            return str(int(scaled)) if scaled == int(scaled) else str(scaled)
        return value
