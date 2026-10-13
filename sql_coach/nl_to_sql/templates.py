"""SQL 模板库：定义 select / aggregate / count 三类查询的骨架。

模板用 `str.format` 占位符填充；各子句（where / group_by / order / limit）
在无内容时渲染为空字符串，因此模板本身始终是语法完整的 SQL。
"""
from collections import defaultdict

# SELECT 模板：显式列查询（无条件子句时对应占位符为空串）
SELECT_TEMPLATE = "SELECT {columns} FROM {table}{where}{order}{limit};"

# 聚合模板：聚合函数 + 可选分组
AGGREGATE_TEMPLATE = "SELECT {columns} FROM {table}{where}{group_by}{order}{limit};"

# COUNT 模板：固定输出别名 cnt
COUNT_TEMPLATE = "SELECT COUNT(*) AS cnt FROM {table}{where};"

# 未识别到表名时的占位表名，保证生成的 SQL 语法完整
UNKNOWN_TABLE = "unknown_table"

# 无显式列时的占位符
ALL_COLUMNS = "*"


def render(template: str, **parts: str) -> str:
    """按模板填充各子句；未提供的占位符按空串处理，避免 KeyError。"""
    return template.format_map(defaultdict(str, parts))
