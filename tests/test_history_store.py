# tests/test_history_store.py
"""HistoryStore 单元测试。纯 Python, 不依赖 Qt。"""
import json
import time
from pathlib import Path

import pytest

from sql_coach.coach import Report
from sql_coach.models import (
    SQLInfo, ExplainResult, AnalysisResult, BenchmarkResult,
)

from gui.storage.history_store import HistoryStore


@pytest.fixture
def store(tmp_path):
    """使用临时目录的 HistoryStore。"""
    return HistoryStore(path=str(tmp_path / "history.json"))


@pytest.fixture
def sample_report():
    """构造一个最小的 Report 对象。"""
    return Report(
        sql_info=SQLInfo(
            raw_sql="SELECT * FROM users WHERE id=1",
            sql_type="SELECT",
            tables=["users"],
            columns=["*"],
            where_conditions=["id=1"],
            join_tables=[],
            order_by=[],
        ),
        explain=None,
        analysis=AnalysisResult(
            problems=[],
            optimized_sql="SELECT * FROM users WHERE id=1;",
            index_ddls=["CREATE INDEX idx_users_id ON users(id);"],
            explanation="已优化",
        ),
        benchmark=BenchmarkResult(
            original_time=0.5,
            optimized_time=0.02,
            speedup=25.0,
            original_rows=1000,
            optimized_rows=1,
        ),
    )


def test_add_returns_id(store, sample_report):
    """add() 返回 6 位 hex id。"""
    rid = store.add(sample_report.sql_info.raw_sql, sample_report, ai_time_ms=1000.0)
    assert isinstance(rid, str)
    assert len(rid) == 6
    # hex 字符串
    int(rid, 16)


def test_list_returns_records(store, sample_report):
    """list() 返回记录列表, 按时间倒序。"""
    store.add("SQL1", sample_report, ai_time_ms=100.0)
    time.sleep(0.01)
    store.add("SQL2", sample_report, ai_time_ms=200.0)
    records = store.list()
    assert len(records) == 2
    # 最新的在前
    assert records[0]["sql"] == "SQL2"
    assert records[1]["sql"] == "SQL1"
    # 字段完整
    rec = records[0]
    assert "id" in rec
    assert "sql" in rec
    assert "timestamp" in rec
    assert "optimized_sql" in rec
    assert "speedup" in rec
    assert "ai_time_ms" in rec
    assert "problem_count" in rec


def test_get_by_id(store, sample_report):
    """get() 按 id 返回单条记录。"""
    rid = store.add("SELECT 1", sample_report, ai_time_ms=50.0)
    rec = store.get(rid)
    assert rec is not None
    assert rec["id"] == rid
    assert rec["sql"] == "SELECT 1"
    assert rec["ai_time_ms"] == 50.0


def test_get_missing_id_returns_none(store):
    """get() 对不存在的 id 返回 None。"""
    assert store.get("ffffff") is None


def test_delete_by_id(store, sample_report):
    """delete() 删除指定记录, 返回 True/False。"""
    rid = store.add("DELETE ME", sample_report, ai_time_ms=10.0)
    assert store.delete(rid) is True
    assert store.get(rid) is None
    assert store.delete(rid) is False  # 已删除
    assert store.delete("nonexist") is False


def test_clear_returns_count(store, sample_report):
    """clear() 返回删除的条数。"""
    store.add("SQL1", sample_report, ai_time_ms=1.0)
    store.add("SQL2", sample_report, ai_time_ms=2.0)
    count = store.clear()
    assert count == 2
    assert store.list() == []


def test_max_100_records(store, sample_report):
    """最多保留 100 条, 超出删最旧。"""
    for i in range(105):
        store.add(f"SQL{i}", sample_report, ai_time_ms=float(i))
    records = store.list()
    assert len(records) == 100
    # 最旧的 SQL0~SQL4 应被删除
    sqls = [r["sql"] for r in records]
    assert "SQL0" not in sqls
    assert "SQL4" not in sqls
    assert "SQL5" in sqls
    assert "SQL104" in sqls


def test_corrupted_file_returns_empty(tmp_path):
    """文件损坏时返回空列表, 不崩溃。"""
    bad_file = tmp_path / "history.json"
    bad_file.write_text("{invalid json!!!", encoding="utf-8")
    store = HistoryStore(path=str(bad_file))
    assert store.list() == []


def test_missing_file_returns_empty(tmp_path):
    """文件不存在时返回空列表。"""
    store = HistoryStore(path=str(tmp_path / "nonexist.json"))
    assert store.list() == []


def test_persistence_across_instances(tmp_path, sample_report):
    """跨实例持久化: 写入后新实例能读到。"""
    path = str(tmp_path / "history.json")
    s1 = HistoryStore(path=path)
    rid = s1.add("PERSIST", sample_report, ai_time_ms=1.0)
    s2 = HistoryStore(path=path)
    rec = s2.get(rid)
    assert rec is not None
    assert rec["sql"] == "PERSIST"
