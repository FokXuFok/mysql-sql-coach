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
