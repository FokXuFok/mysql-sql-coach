"""SQL 复杂度评分：纯结构分析，不调用 AI。"""
import re

from ..models import SQLInfo, Complexity

DEFAULT_THRESHOLD = 8
SIMPLE_MAX = 3

_RESERVED = {
    "where", "group", "order", "limit", "having", "on", "join", "inner",
    "left", "right", "union", "set", "values", "as", "and", "or", "by",
}


class ComplexityScorer:
    """按 SQL 结构特征打分并划分等级。"""

    def __init__(self, threshold: int = DEFAULT_THRESHOLD):
        self.threshold = threshold

    def score(self, sql_info: SQLInfo) -> Complexity:
        sql = sql_info.raw_sql or ""
        upper = sql.upper()
        s = 0
        reasons: list[str] = []

        n = len(sql_info.tables)
        if n == 2:
            s += 2
            reasons.append("2 张表")
        elif n >= 3:
            s += 4
            reasons.append(f"{n} 张表")

        subqueries = max(0, len(re.findall(r"\bSELECT\b", upper)) - 1)
        if subqueries:
            s += 3 * subqueries
            reasons.append(f"{subqueries} 个子查询/派生表")

        correlated = self._count_correlated(sql_info, sql)
        if correlated:
            s += 5 * correlated
            reasons.append(f"{correlated} 个相关子查询")

        if re.search(r"\bWITH\b", upper):
            s += 3
            reasons.append("CTE")
        if re.search(r"\bUNION\b", upper):
            s += 2
            reasons.append("UNION")
        if re.search(r"\b(GROUP\s+BY|HAVING)\b", upper):
            s += 2
            reasons.append("聚合/分组")
        elif re.search(r"\b(COUNT|SUM|AVG|MAX|MIN)\s*\(", upper):
            s += 2
            reasons.append("聚合函数")
        if re.search(r"\bOVER\s*\(", upper):
            s += 5
            reasons.append("窗口函数")
        if re.search(r"\bCASE\b", upper):
            s += 2
            reasons.append("CASE 表达式")
        if len(re.findall(r"\bOR\b", upper)) >= 2:
            s += 1
            reasons.append("多 OR 条件")
        if sql_info.sql_type == "SELECT" and not sql_info.where_conditions:
            s += 2
            reasons.append("无 WHERE 全表查询")
        if len(sql_info.order_by) >= 2:
            s += 1
            reasons.append("多列排序")

        if s <= SIMPLE_MAX and s <= self.threshold:
            level = "simple"
        elif s <= self.threshold:
            level = "medium"
        else:
            level = "complex"
        return Complexity(level=level, score=s, reasons=reasons)

    @staticmethod
    def _count_correlated(sql_info: SQLInfo, sql: str) -> int:
        aliases = {t.lower() for t in sql_info.tables}
        for m in re.finditer(
            r"\b(?:FROM|JOIN)\s+([A-Za-z_]\w*)(?:\s+(?:AS\s+)?([A-Za-z_]\w*))?",
            sql, re.IGNORECASE,
        ):
            alias = m.group(2)
            if alias and alias.lower() not in _RESERVED:
                aliases.add(alias.lower())
        count = 0
        for m in re.finditer(r"\(\s*SELECT\b([^()]*)\)", sql, re.IGNORECASE | re.DOTALL):
            inner = m.group(1)
            if any(re.search(rf"\b{re.escape(a)}\s*\.", inner, re.IGNORECASE) for a in aliases):
                count += 1
        return count
