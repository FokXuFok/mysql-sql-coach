# tests/test_coach.py
import json
from unittest.mock import MagicMock, patch

import pytest

from sql_coach.coach import SQLCoach, Report
from sql_coach.models import (
    Config, DBConfig, SQLInfo, ExplainResult, ExplainRow,
    AnalysisResult, Problem, BenchmarkResult
)


@pytest.fixture
def mock_config():
    db = DBConfig(host="localhost", port=3306, user="root",
                  password="x", database="test")
    return Config(db=db, model="deepseek",
                  deepseek_api_key="sk-test", openai_api_key="",
                  ollama_url="http://localhost:11434",
                  benchmark_runs=3, mock=False)


@pytest.fixture
def mock_config_mock_mode():
    db = DBConfig(host="localhost", port=3306, user="root",
                  password="x", database="test")
    return Config(db=db, model="deepseek",
                  deepseek_api_key="sk-test", openai_api_key="",
                  ollama_url="http://localhost:11434",
                  benchmark_runs=3, mock=True)


def test_coach_init_real_mode(mock_config):
    with patch("sql_coach.coach.DBConnector") as mock_db_cls, \
         patch("sql_coach.coach.create_ai_engine") as mock_ai:
        mock_db_cls.return_value = MagicMock()
        mock_ai.return_value = MagicMock()

        coach = SQLCoach(mock_config)
        assert coach.config == mock_config


def test_coach_init_mock_mode(mock_config_mock_mode):
    with patch("sql_coach.coach.MockConnector") as mock_db_cls, \
         patch("sql_coach.coach.create_ai_engine") as mock_ai:
        mock_db_cls.return_value = MagicMock()
        mock_ai.return_value = MagicMock()

        coach = SQLCoach(mock_config_mock_mode)
        assert coach.config.mock is True


def test_coach_analyze_full_flow(mock_config):
    """Test the full analyze flow with mocked dependencies."""
    with patch("sql_coach.coach.DBConnector") as mock_db_cls, \
         patch("sql_coach.coach.create_ai_engine") as mock_ai_factory:

        mock_db = MagicMock()
        mock_db.is_connected.return_value = True
        mock_db.explain.return_value = ExplainResult(
            rows=[ExplainRow(id=1, select_type="SIMPLE", table="orders",
                             type="ALL", key=None, rows=420000, extra="Using where")],
            is_full_scan=True, missing_indexes=["orders"],
            problems=["orders 全表扫描"],
        )
        mock_db.benchmark.side_effect = [2.31, 0.04]
        mock_db_cls.return_value = mock_db

        mock_ai = MagicMock()
        mock_ai.analyze.return_value = AnalysisResult(
            problems=[Problem(severity="critical", table="orders",
                              description="full scan", suggestion="add index")],
            optimized_sql="SELECT id FROM orders FORCE INDEX(idx) WHERE status='pending'",
            index_ddls=["CREATE INDEX idx ON orders(status);"],
            explanation="加索引",
        )
        mock_ai_factory.return_value = mock_ai

        coach = SQLCoach(mock_config)
        report = coach.analyze("SELECT * FROM orders WHERE status='pending'")

        assert isinstance(report, Report)
        assert report.sql_info.sql_type == "SELECT"
        assert report.explain is not None
        assert report.analysis.optimized_sql != ""
        assert report.benchmark is not None
        assert report.benchmark.original_time == 2.31


def test_coach_analyze_mock_mode_skips_benchmark(mock_config_mock_mode):
    """In mock mode, benchmark should be None."""
    with patch("sql_coach.coach.MockConnector") as mock_db_cls, \
         patch("sql_coach.coach.create_ai_engine") as mock_ai_factory:

        mock_db = MagicMock()
        mock_db.is_connected.return_value = True
        mock_db_cls.return_value = mock_db

        mock_ai = MagicMock()
        mock_ai.analyze.return_value = AnalysisResult(
            problems=[], optimized_sql="SELECT 1",
            index_ddls=[], explanation="ok",
        )
        mock_ai_factory.return_value = mock_ai

        coach = SQLCoach(mock_config_mock_mode)
        report = coach.analyze("SELECT * FROM t")

        assert report.benchmark is None


def test_coach_close(mock_config):
    with patch("sql_coach.coach.DBConnector") as mock_db_cls, \
         patch("sql_coach.coach.create_ai_engine"):
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db

        coach = SQLCoach(mock_config)
        coach.close()
        assert mock_db.close.called



def test_end_to_end_mock_mode():
    """End-to-end test in mock mode (no real DB/AI required).

    Mock mode uses MockAIEngine, so no patching of OpenAI is needed.
    """
    from sql_coach.coach import SQLCoach
    from sql_coach.models import Config, DBConfig

    db = DBConfig(host="localhost", port=3306, user="root",
                  password="x", database="test")
    config = Config(db=db, model="deepseek",
                    deepseek_api_key="", openai_api_key="",
                    ollama_url="http://localhost:11434",
                    benchmark_runs=2, mock=True)

    coach = SQLCoach(config)
    report = coach.analyze("SELECT * FROM orders WHERE status='pending'")

    assert report.sql_info.sql_type == "SELECT"
    # MockAIEngine flags SELECT * and WHERE without index -> at least 1 problem
    assert len(report.analysis.problems) >= 1
    # Should suggest an index DDL for the WHERE column
    assert len(report.analysis.index_ddls) >= 1
    assert report.benchmark is None  # mock mode skips benchmark


def test_coach_routes_simple_sql_to_local():
    """auto 模式下简单 SQL 走本地引擎，不创建 AI 客户端。"""
    from sql_coach.models import Config, DBConfig
    from sql_coach.coach import SQLCoach
    from unittest.mock import patch

    db = DBConfig(host="h", port=3306, user="u", password="p", database="d")
    config = Config(db=db, model="deepseek", deepseek_api_key="", openai_api_key="",
                    ollama_url="http://x", benchmark_runs=3, mock=False, optimizer_mode="auto")
    with patch("sql_coach.coach.DBConnector") as db_cls, \
         patch("sql_coach.coach.create_ai_engine") as ai_factory:
        mock_db = db_cls.return_value
        mock_db.is_connected.return_value = False
        coach = SQLCoach(config, use_cache=False)
        report = coach.analyze("SELECT * FROM orders WHERE status='pending'")
        assert report.engine_used == "local"
        assert report.complexity is not None
        assert ai_factory.call_count == 0


def test_coach_routes_complex_sql_to_ai():
    from sql_coach.models import Config, DBConfig
    from sql_coach.coach import SQLCoach
    from sql_coach.models import AnalysisResult
    from unittest.mock import patch, MagicMock

    db = DBConfig(host="h", port=3306, user="u", password="p", database="d")
    config = Config(db=db, model="deepseek", deepseek_api_key="k", openai_api_key="",
                    ollama_url="http://x", benchmark_runs=3, mock=False, optimizer_mode="auto")
    with patch("sql_coach.coach.DBConnector") as db_cls, \
         patch("sql_coach.coach.create_ai_engine") as ai_factory:
        db_cls.return_value.is_connected.return_value = False
        mock_ai = MagicMock()
        mock_ai.name.return_value = "deepseek"
        mock_ai.analyze.return_value = AnalysisResult(
            problems=[], optimized_sql="SELECT 1", index_ddls=[], explanation="ok")
        ai_factory.return_value = mock_ai

        coach = SQLCoach(config, use_cache=False)
        sql = ("SELECT ROW_NUMBER() OVER (ORDER BY a.id) FROM a "
               "JOIN b ON a.id=b.id JOIN c ON b.id=c.id")
        report = coach.analyze(sql)
        assert report.engine_used == "deepseek"
        assert mock_ai.analyze.called


def test_coach_falls_back_to_ai_when_local_engine_fails():
    """本地规则引擎整体失败时应降级到 AI（spec §12），而不是把异常抛给上层。"""
    from sql_coach.models import Config, DBConfig
    from sql_coach.coach import SQLCoach
    from sql_coach.models import AnalysisResult
    from unittest.mock import patch, MagicMock

    db = DBConfig(host="h", port=3306, user="u", password="p", database="d")
    config = Config(db=db, model="deepseek", deepseek_api_key="k", openai_api_key="",
                    ollama_url="http://x", benchmark_runs=3, mock=False, optimizer_mode="auto")
    with patch("sql_coach.coach.DBConnector") as db_cls, \
         patch("sql_coach.coach.create_ai_engine") as ai_factory, \
         patch("sql_coach.optimizer.LocalOptimizerAdapter") as local_cls:
        db_cls.return_value.is_connected.return_value = False
        local_cls.return_value.name.return_value = "local"
        local_cls.return_value.optimize.side_effect = RuntimeError("local boom")

        mock_ai = MagicMock()
        mock_ai.name.return_value = "deepseek"
        mock_ai.analyze.return_value = AnalysisResult(
            problems=[], optimized_sql="SELECT 1", index_ddls=[], explanation="ok")
        ai_factory.return_value = mock_ai

        coach = SQLCoach(config, use_cache=False)
        report = coach.analyze("SELECT * FROM orders WHERE status='pending'")

        assert report.engine_used == "deepseek"
        assert mock_ai.analyze.called
