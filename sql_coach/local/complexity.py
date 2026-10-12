"""SQL 复杂度评分：纯结构分析，不调用 AI。"""
import re

from ..models import SQLInfo, Complexity

DEFAULT_THRESHOLD = 8
SIMPLE_MAX = 3


class ComplexityScorer:
    """按 SQL 结构特征打分并划分等级。"""

    def __init__(self, threshold: int = DEFAULT_THRESHOLD):
        # 阈值下界钳制：0/负数会让一切判为 complex
        self.threshold = max(1, threshold)

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

        if s <= min(SIMPLE_MAX, self.threshold):
            level = "simple"
        elif s <= self.threshold:
            level = "medium"
        else:
            level = "complex"
        return Complexity(level=level, score=s, reasons=reasons)
