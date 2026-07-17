"""SQLite persistent cache for AI analysis results."""
import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .models import AnalysisResult, Problem

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path.home() / ".sql-coach"
DEFAULT_CACHE_PATH = DEFAULT_CACHE_DIR / "cache.db"
CACHE_TTL_SECONDS = 300  # 5 分钟


def _hash_sql(sql: str) -> str:
    """对 SQL 做 SHA-256 哈希，作为缓存 key。"""
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _serialize(result: AnalysisResult) -> str:
    """将 AnalysisResult 序列化为 JSON 字符串。"""
    return json.dumps({
        "problems": [asdict(p) for p in result.problems],
        "optimized_sql": result.optimized_sql,
        "index_ddls": result.index_ddls,
        "explanation": result.explanation,
    }, ensure_ascii=False)


def _deserialize(data: str) -> AnalysisResult:
    """从 JSON 字符串反序列化为 AnalysisResult。"""
    d = json.loads(data)
    return AnalysisResult(
        problems=[Problem(**p) for p in d["problems"]],
        optimized_sql=d["optimized_sql"],
        index_ddls=d["index_ddls"],
        explanation=d["explanation"],
    )


class AnalysisCache:
    """基于 SQLite 的 AI 分析结果持久缓存。"""

    def __init__(self, path=None, ttl=CACHE_TTL_SECONDS):
        self.path = Path(path) if path else DEFAULT_CACHE_PATH
        self.ttl = ttl
        self._init_db()

    def _init_db(self):
        """初始化数据库表。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analysis_cache (
                    sql_hash TEXT PRIMARY KEY,
                    sql_text TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.commit()

    def get(self, sql: str) -> Optional[AnalysisResult]:
        """从缓存获取分析结果，过期返回 None。"""
        sql_hash = _hash_sql(sql)
        with sqlite3.connect(str(self.path)) as conn:
            row = conn.execute(
                "SELECT result_json, created_at FROM analysis_cache WHERE sql_hash = ?",
                (sql_hash,),
            ).fetchone()
        if row is None:
            return None
        result_json, created_at = row
        if time.time() - created_at > self.ttl:
            self.delete(sql)
            return None
        try:
            return _deserialize(result_json)
        except Exception as e:
            logger.warning("缓存反序列化失败: %s", e)
            self.delete(sql)
            return None

    def put(self, sql: str, result: AnalysisResult) -> None:
        """存入缓存。"""
        sql_hash = _hash_sql(sql)
        result_json = _serialize(result)
        with sqlite3.connect(str(self.path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO analysis_cache "
                "(sql_hash, sql_text, result_json, created_at) VALUES (?, ?, ?, ?)",
                (sql_hash, sql, result_json, time.time()),
            )
            conn.commit()

    def delete(self, sql: str) -> None:
        """删除单条缓存。"""
        sql_hash = _hash_sql(sql)
        with sqlite3.connect(str(self.path)) as conn:
            conn.execute("DELETE FROM analysis_cache WHERE sql_hash = ?", (sql_hash,))
            conn.commit()

    def clear(self) -> int:
        """清空所有缓存，返回删除条数。"""
        with sqlite3.connect(str(self.path)) as conn:
            cur = conn.execute("DELETE FROM analysis_cache")
            conn.commit()
            return cur.rowcount

    def count(self) -> int:
        """返回缓存条目数。"""
        with sqlite3.connect(str(self.path)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM analysis_cache").fetchone()
            return row[0] if row else 0
