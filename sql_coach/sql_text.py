"""SQL 文本清洗工具：剥离注释与字符串字面量，供解析产物（SQLInfo）与规则使用。

- ``strip_comments``：去掉 ``--``/``/* */`` 注释（跳过引号内文本），
  但保留 MySQL 可执行注释 ``/*! ... */`` 与优化器提示 ``/*+ ... */``。
- ``strip_literals``：清空字符串字面量内容、保留引号本身。
- ``clean``：先去注释再清字面量，供「关键字类」规则匹配前使用。

需要匹配字面量内容的规则（如 leading_wildcard 的 LIKE '%x'、
function_on_column 的 DATE(col)='2026-01-01'）不要使用 ``clean``，
应使用只去注释的 ``strip_comments``。
"""

_QUOTES = ("'", '"')


def _skip_quoted(sql: str, i: int, quote: str) -> tuple[int, bool]:
    """从 sql[i] == quote 开始，返回 ``(结束下标, 是否闭合)``（含转义与双写引号）。

    结束下标指向闭合引号之后；未闭合时指向字符串末尾。
    """
    n = len(sql)
    i += 1
    while i < n:
        ch = sql[i]
        if ch == "\\" and i + 1 < n:
            i += 2  # 反斜杠转义，跳过下一个字符
            continue
        if ch == quote:
            if i + 1 < n and sql[i + 1] == quote:
                i += 2  # 双写引号表示一个字面量引号，仍在字符串内
                continue
            return i + 1, True
        i += 1
    return n, False


def strip_comments(sql: str) -> str:
    """去掉 ``-- 到行尾`` 与 ``/* ... */`` 注释，用空格替换（保留换行）。"""
    if not sql:
        return sql
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in _QUOTES:
            end, closed = _skip_quoted(sql, i, ch)
            out.append(sql[i:end])
            i = end
            continue
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            while i < n and sql[i] != "\n":
                i += 1
            continue  # 行尾换行保留（若存在）
        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            # MySQL 可执行注释 /*! ... */ 与优化器提示 /*+ ... */ 都是真 SQL，
            # 会影响语义/执行计划，必须原样保留；仅剥离普通 /* ... */ 注释。
            if i + 2 < n and sql[i + 2] in "!+":
                end = i + 2
                while end + 1 < n and not (sql[end] == "*" and sql[end + 1] == "/"):
                    end += 1
                end = min(end + 2, n)
                out.append(sql[i:end])
                i = end
                continue
            i += 2
            while i + 1 < n and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i = min(i + 2, n)
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def strip_literals(sql: str) -> str:
    """清空 ``'...'`` 与 ``"..."`` 的内容，保留引号本身（如 ``'a!=b'`` -> ``''``）。"""
    if not sql:
        return sql
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in _QUOTES:
            end, closed = _skip_quoted(sql, i, ch)
            out.append(ch + ch if closed else ch)  # 闭合则清空内容、保留引号
            i = end
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def clean(sql: str) -> str:
    """先剥离注释，再清空字面量内容，供关键字类规则在正则匹配前调用。"""
    return strip_literals(strip_comments(sql or ""))
