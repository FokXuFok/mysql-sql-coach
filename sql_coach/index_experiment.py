# sql_coach/index_experiment.py
"""索引实测模式：临时建索引 → 复测 → 回滚，给出真实的索引收益。

现有 benchmark 比较的是「原始 SQL vs 改写后 SQL」，对建索引类建议恒为 ~1.0x。
本模块通过临时创建建议索引、复测同一 SQL、再回滚索引，量化索引真实收益。
"""
import logging
import re
from typing import Optional

from .models import IndexImpact

logger = logging.getLogger(__name__)

# 收益守卫阈值：实测提速低于该值判为「不建议创建」。
# 依据真实 MySQL 选择性扫描：约 1%~5% 命中率处索引失效（5.25x → 1.15x），
# 1.3 落在 1.15x 与 5.25x 之间。
INDEX_SPEEDUP_THRESHOLD = 1.3

# 匹配 CREATE INDEX [IF NOT EXISTS] <idx> ON <tbl>，兼容反引号与大小写。
_CREATE_INDEX_RE = re.compile(
    r"^\s*CREATE\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<index>`[^`]+`|[A-Za-z_][\w$]*)"
    r"\s+ON\s+"
    r"(?P<table>`[^`]+`|[A-Za-z_][\w$]*)",
    re.IGNORECASE,
)


def parse_create_index(ddl: str) -> Optional[tuple[str, str]]:
    """从 CREATE INDEX 语句解析出 (索引名, 表名)。

    兼容可选的 IF NOT EXISTS、反引号与大小写。无法解析时返回 None。
    """
    if not ddl:
        return None
    m = _CREATE_INDEX_RE.match(ddl)
    if not m:
        return None
    index_name = m.group("index").strip("`")
    table = m.group("table").strip("`")
    return index_name, table


def build_drop_index(ddl: str) -> Optional[str]:
    """生成与 CREATE INDEX 对应的 DROP INDEX 语句；无法解析时返回 None。"""
    parsed = parse_create_index(ddl)
    if parsed is None:
        return None
    index_name, table = parsed
    return f"DROP INDEX `{index_name}` ON `{table}`;"


def _index_exists(conn, table: str, index_name: str) -> bool:
    """查询 information_schema.STATISTICS 判断索引是否已存在。

    查询异常时按「不存在」处理（后续会尝试创建，失败会被记录）。
    """
    try:
        rows = conn.query(
            "SELECT 1 FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
            "AND INDEX_NAME = %s LIMIT 1",
            (table, index_name),
        )
    except Exception as e:
        logger.debug("检查索引是否存在失败，按不存在处理: %s", e)
        return False
    return bool(rows)


def _first_table(ddls: list[str]) -> Optional[str]:
    """从 DDL 列表中取第一个可解析的表名；无法解析时返回 None。"""
    for ddl in ddls:
        parsed = parse_create_index(ddl)
        if parsed is not None:
            return parsed[1]
    return None


def _estimate_selectivity(conn, sql: str, table: Optional[str],
                          ) -> tuple[int, int, float]:
    """best-effort 估算命中率，任何失败都置为未知（不影响主流程）。

    Returns:
        (matched_rows, total_rows, selectivity)，未知项分别为 0/0/-1.0。
    """
    total_rows = 0
    if table:
        try:
            rows = conn.query(
                "SELECT TABLE_ROWS FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                (table,),
            )
            if rows:
                total_rows = int(rows[0][0] or 0)
        except Exception as e:  # best-effort：失败置为未知
            logger.debug("查询表总行数失败（忽略）: %s", e)

    matched_rows = 0
    matched_known = False
    if sql and sql.strip().upper().startswith("SELECT"):
        try:
            rows = conn.query(f"SELECT COUNT(*) FROM ({sql}) AS _probe", ())
            if rows:
                matched_rows = int(rows[0][0] or 0)
                matched_known = True
        except Exception as e:  # best-effort：失败置为未知
            logger.debug("探测命中行数失败（忽略）: %s", e)

    selectivity = -1.0
    if matched_known and total_rows > 0:
        selectivity = matched_rows / total_rows
    return matched_rows, total_rows, selectivity


def measure_index_impact(conn, sql: str, ddls: list[str],
                         runs: int = 3) -> Optional[IndexImpact]:
    """实测索引收益：建索引前基准 → 临时建索引 → 复测 → 回滚。

    Args:
        conn: DBConnector 实例（需支持 is_connected/query/execute/benchmark）。
        sql: 待测 SQL。
        ddls: 索引建议 DDL 列表。
        runs: 基准测试次数。

    Returns:
        IndexImpact；未连接或 ddls 为空时返回 None。

    安全保证：任何异常都不会向上抛出；已成功创建的索引一定会在 finally 中回滚，
    回滚失败的信息会记入 error 并置 rolled_back=False（并 logger.error）。
    """
    if not conn.is_connected() or not ddls:
        return None

    skipped_ddls: list[str] = []
    to_create: list[tuple[str, str, str]] = []
    for ddl in ddls:
        parsed = parse_create_index(ddl)
        if parsed is None:
            skipped_ddls.append(ddl)
            continue
        index_name, table = parsed
        if _index_exists(conn, table, index_name):
            skipped_ddls.append(ddl)
            continue
        to_create.append((index_name, table, ddl))

    before_time = 0.0
    after_time = 0.0
    applied: list[tuple[str, str, str]] = []   # (索引名, 表名, 原 DDL)
    analyzed_tables: set[str] = set()
    error = ""
    rolled_back = True

    try:
        before_time = conn.benchmark(sql, runs=runs)
        for index_name, table, ddl in to_create:
            conn.execute(ddl)
            applied.append((index_name, table, ddl))
            if table not in analyzed_tables:
                try:
                    conn.execute(f"ANALYZE TABLE `{table}`")
                except Exception as e:  # best-effort：失败忽略
                    logger.debug("ANALYZE TABLE %s 失败（忽略）: %s", table, e)
                analyzed_tables.add(table)
        after_time = conn.benchmark(sql, runs=runs)
    except Exception as e:
        error = f"索引实测执行失败: {e}"
        logger.error(error)
    finally:
        for index_name, _table, ddl in applied:
            drop_ddl = build_drop_index(ddl)
            if drop_ddl is None:
                continue
            try:
                conn.execute(drop_ddl)
            except Exception as e:
                rolled_back = False
                msg = f"回滚索引 {index_name} 失败: {e}"
                error = f"{error}; {msg}" if error else msg
                logger.error(msg)

    if after_time > 0:
        speedup = before_time / after_time
    else:
        speedup = float("inf") if before_time > 0 else 1.0

    # best-effort 估算选择性（回滚后进行，反映原始查询的命中率）。
    matched_rows, total_rows, selectivity = _estimate_selectivity(
        conn, sql, _first_table(ddls))

    recommended = speedup >= INDEX_SPEEDUP_THRESHOLD
    if recommended:
        if speedup == float("inf"):
            verdict = "索引有效（实测提速 无限大），建议采纳"
        else:
            verdict = f"索引有效（实测提速 {speedup:.1f}x），建议采纳"
    else:
        if selectivity >= 0:
            verdict = (f"索引收益有限（实测提速 {speedup:.2f}x，"
                       f"命中率约 {selectivity * 100:.1f}%），不建议创建")
        else:
            verdict = f"索引收益有限（实测提速 {speedup:.2f}x），不建议创建"

    return IndexImpact(
        before_time=before_time,
        after_time=after_time,
        speedup=speedup,
        applied_ddls=[ddl for _idx, _tbl, ddl in applied],
        skipped_ddls=skipped_ddls,
        rolled_back=rolled_back,
        error=error,
        matched_rows=matched_rows,
        total_rows=total_rows,
        selectivity=selectivity,
        recommended=recommended,
        verdict=verdict,
    )
