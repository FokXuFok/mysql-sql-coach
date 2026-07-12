# sql_coach/engine/explain_runner.py
"""EXPLAIN execution and result parsing."""
import json
from typing import Optional

from ..models import ExplainResult, ExplainRow


def parse_explain_json(explain_json_str: str) -> ExplainResult:
    """Parse EXPLAIN FORMAT=JSON output into ExplainResult."""
    try:
        data = json.loads(explain_json_str)
    except (json.JSONDecodeError, TypeError):
        return ExplainResult(rows=[], is_full_scan=False,
                             missing_indexes=[], problems=["无法解析 EXPLAIN 输出"])

    rows = []
    problems = []
    missing_indexes = []

    def process_table(table_data: dict):
        nonlocal rows, problems, missing_indexes
        table_name = table_data.get("table_name", "unknown")
        access_type = table_data.get("access_type", "ALL")
        key = table_data.get("key")
        rows_examined = table_data.get("rows_examined_per_scan", 0)

        extras = []
        if table_data.get("using_filesort"):
            extras.append("Using filesort")
        if table_data.get("using_temporary_table"):
            extras.append("Using temporary")
        if table_data.get("attached_condition"):
            extras.append("Using where")

        extra_str = ", ".join(extras) if extras else ""

        rows.append(ExplainRow(
            id=len(rows) + 1,
            select_type="SIMPLE",
            table=table_name,
            type=access_type,
            key=key,
            rows=rows_examined,
            extra=extra_str,
        ))

        if access_type == "ALL":
            problems.append(f"{table_name} 全表扫描 (type=ALL)")
            missing_indexes.append(table_name)
        elif key is None and access_type not in ("const", "system"):
            problems.append(f"{table_name} 未使用索引")
            missing_indexes.append(table_name)

        if "Using filesort" in extra_str:
            problems.append(f"{table_name} 文件排序 (filesort)")
        if "Using temporary" in extra_str:
            problems.append(f"{table_name} 使用临时表")

    def walk(node):
        if isinstance(node, dict):
            if "table" in node:
                process_table(node["table"])
            if "ordering_operation" in node:
                op = node["ordering_operation"]
                if "table" in op:
                    table_data = dict(op["table"])
                    if op.get("using_filesort"):
                        table_data["using_filesort"] = True
                    if op.get("using_temporary_table"):
                        table_data["using_temporary_table"] = True
                    process_table(table_data)
            if "nested_loop" in node:
                for item in node["nested_loop"]:
                    walk(item)
            if "query_block" in node:
                walk(node["query_block"])
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)

    is_full_scan = any(r.type == "ALL" for r in rows)

    return ExplainResult(
        rows=rows,
        is_full_scan=is_full_scan,
        missing_indexes=missing_indexes,
        problems=problems,
    )


def run_explain(conn, sql: str) -> ExplainResult:
    """Execute EXPLAIN FORMAT=JSON on the connection and parse result."""
    explain_sql = f"EXPLAIN FORMAT=JSON {sql}"
    try:
        with conn.cursor() as cursor:
            cursor.execute(explain_sql)
            row = cursor.fetchone()
            if row and row[0]:
                return parse_explain_json(row[0])
    except Exception as e:
        return ExplainResult(
            rows=[], is_full_scan=False,
            missing_indexes=[], problems=[f"EXPLAIN 执行失败: {e}"]
        )

    return ExplainResult(rows=[], is_full_scan=False,
                         missing_indexes=[], problems=["EXPLAIN 无返回结果"])