# gui/storage/history_store.py
"""历史记录 JSON 存储, 不依赖 Qt。

存储到 ~/.sql-coach/history.json, 最多保留 100 条。
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime
from typing import Optional

from sql_coach.coach import Report

logger = logging.getLogger(__name__)

DEFAULT_PATH = os.path.join(
    os.path.expanduser("~"), ".sql-coach", "history.json"
)
MAX_RECORDS = 100


class HistoryStore:
    """JSON 文件历史记录存储。"""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or DEFAULT_PATH
        self._max_records = MAX_RECORDS

    # ---- 内部读写 ----
    def _read(self) -> list[dict]:
        """读取全部记录, 文件损坏返回空列表。"""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return []
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("历史记录文件损坏, 返回空列表: %s", e)
            return []
        if not isinstance(data, list):
            return []
        return data

    def _write(self, records: list[dict]) -> None:
        """写入记录, 自动创建父目录。"""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.path)

    # ---- 公共 API ----
    def add(self, sql: str, report: Report, ai_time_ms: float) -> str:
        """添加一条记录, 返回 6 位 hex id。超出上限自动删最旧。"""
        rid = secrets.token_hex(3)  # 6 位 hex
        speedup = None
        if report.benchmark is not None:
            speedup = report.benchmark.speedup
        record = {
            "id": rid,
            "sql": sql,
            "timestamp": datetime.now().isoformat(),
            "optimized_sql": report.analysis.optimized_sql,
            "speedup": speedup,
            "ai_time_ms": ai_time_ms,
            "problem_count": len(report.analysis.problems),
        }
        records = self._read()
        records.append(record)
        # 超出上限: 删最旧 (列表头部)
        if len(records) > self._max_records:
            records = records[-self._max_records:]
        self._write(records)
        return rid

    def list(self) -> list[dict]:
        """返回全部记录, 按时间倒序 (最新在前)。"""
        records = self._read()
        # 按 timestamp 倒序
        return sorted(
            records,
            key=lambda r: r.get("timestamp", ""),
            reverse=True,
        )

    def delete(self, record_id: str) -> bool:
        """删除指定 id 的记录, 返回是否删除成功。"""
        records = self._read()
        before = len(records)
        records = [r for r in records if r.get("id") != record_id]
        if len(records) == before:
            return False
        self._write(records)
        return True

    def clear(self) -> int:
        """清空全部记录, 返回删除条数。"""
        records = self._read()
        count = len(records)
        self._write([])
        return count

    def get(self, record_id: str) -> Optional[dict]:
        """按 id 取单条记录, 不存在返回 None。"""
        for r in self._read():
            if r.get("id") == record_id:
                return r
        return None
