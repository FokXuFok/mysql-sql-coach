# tests/test_ai_engine.py
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from sql_coach.ai.base import AIEngine
from sql_coach.ai.deepseek import DeepSeekEngine
from sql_coach.ai.factory import create_ai_engine
from sql_coach.models import SQLInfo, ExplainResult, AnalysisResult


@pytest.fixture
def sample_sql_info():
    return SQLInfo(
        raw_sql="SELECT * FROM orders WHERE status='pending'",
        sql_type="SELECT",
        tables=["orders"],
        columns=["*"],
        where_conditions=["status='pending'"],
        join_tables=[],
        order_by=[],
    )


@pytest.fixture
def sample_explain_result():
    from sql_coach.models import ExplainRow
    return ExplainResult(
        rows=[ExplainRow(
            id=1, select_type="SIMPLE", table="orders",
            type="ALL", key=None, rows=420000, extra="Using where"
        )],
        is_full_scan=True,
        missing_indexes=["orders"],
        problems=["orders 全表扫描"],
    )


def test_deepseek_engine_name():
    engine = DeepSeekEngine(api_key="sk-test")
    assert engine.name() == "deepseek"


def test_factory_creates_deepseek():
    from sql_coach.models import Config, DBConfig
    db = DBConfig(host="localhost", port=3306, user="root",
                  password="x", database="test")
    config = Config(db=db, model="deepseek",
                    deepseek_api_key="sk-x", openai_api_key="",
                    ollama_url="http://localhost:11434",
                    benchmark_runs=3, mock=False)
    engine = create_ai_engine("deepseek", config)
    assert isinstance(engine, DeepSeekEngine)


def test_factory_unknown_model_raises():
    from sql_coach.models import Config, DBConfig
    db = DBConfig(host="localhost", port=3306, user="root",
                  password="x", database="test")
    config = Config(db=db, model="unknown",
                    deepseek_api_key="", openai_api_key="",
                    ollama_url="http://localhost:11434",
                    benchmark_runs=3, mock=False)
    with pytest.raises(ValueError):
        create_ai_engine("unknown", config)


def test_deepseek_analyze_with_mock_response(sample_sql_info, sample_explain_result):
    """Test analyze with mocked OpenAI client."""
    engine = DeepSeekEngine(api_key="sk-test")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "problems": [
            {"severity": "critical", "table": "orders",
             "description": "full scan", "suggestion": "add index"}
        ],
        "optimized_sql": "SELECT id FROM orders FORCE INDEX(idx_status) WHERE status='pending'",
        "index_ddls": ["CREATE INDEX idx_status ON orders(status);"],
        "explanation": "加了索引就好",
    })

    with patch.object(engine, "client") as mock_client:
        mock_client.chat.completions.create.return_value = mock_response
        result = engine.analyze(sample_sql_info, sample_explain_result)

    assert isinstance(result, AnalysisResult)
    assert len(result.problems) == 1
    assert result.problems[0].severity == "critical"
    assert "FORCE INDEX" in result.optimized_sql
    assert len(result.index_ddls) == 1


def test_deepseek_analyze_handles_invalid_json(sample_sql_info, sample_explain_result):
    """Test handling of invalid JSON response."""
    engine = DeepSeekEngine(api_key="sk-test")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "not json at all"

    with patch.object(engine, "client") as mock_client:
        mock_client.chat.completions.create.return_value = mock_response
        result = engine.analyze(sample_sql_info, sample_explain_result)

    # Should fall back to a basic result
    assert isinstance(result, AnalysisResult)
    assert result.optimized_sql == sample_sql_info.raw_sql


def test_deepseek_analyze_without_explain(sample_sql_info):
    """Test analyze in mock mode (no EXPLAIN result)."""
    engine = DeepSeekEngine(api_key="sk-test")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "problems": [],
        "optimized_sql": sample_sql_info.raw_sql,
        "index_ddls": [],
        "explanation": "看起来不错",
    })

    with patch.object(engine, "client") as mock_client:
        mock_client.chat.completions.create.return_value = mock_response
        result = engine.analyze(sample_sql_info, None)

    assert isinstance(result, AnalysisResult)


from sql_coach.ai.openai_adapter import OpenAIEngine
from sql_coach.ai.ollama import OllamaEngine


def test_openai_engine_name():
    engine = OpenAIEngine(api_key="sk-test")
    assert engine.name() == "openai"


def test_ollama_engine_name():
    engine = OllamaEngine(url="http://localhost:11434")
    assert engine.name() == "ollama"


def test_factory_creates_openai():
    from sql_coach.models import Config, DBConfig
    db = DBConfig(host="localhost", port=3306, user="root",
                  password="x", database="test")
    config = Config(db=db, model="openai",
                    deepseek_api_key="", openai_api_key="sk-x",
                    ollama_url="http://localhost:11434",
                    benchmark_runs=3, mock=False)
    engine = create_ai_engine("openai", config)
    assert isinstance(engine, OpenAIEngine)


def test_factory_creates_ollama():
    from sql_coach.models import Config, DBConfig
    db = DBConfig(host="localhost", port=3306, user="root",
                  password="x", database="test")
    config = Config(db=db, model="ollama",
                    deepseek_api_key="", openai_api_key="",
                    ollama_url="http://localhost:11434",
                    benchmark_runs=3, mock=False)
    engine = create_ai_engine("ollama", config)
    assert isinstance(engine, OllamaEngine)


def test_openai_analyze_with_mock_response(sample_sql_info, sample_explain_result):
    """Test OpenAIEngine analyze with mocked client."""
    engine = OpenAIEngine(api_key="sk-test")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "problems": [
            {"severity": "warning", "table": "orders",
             "description": "SELECT *", "suggestion": "specify columns"}
        ],
        "optimized_sql": "SELECT id FROM orders WHERE status='pending'",
        "index_ddls": [],
        "explanation": "指定列名",
    })

    with patch.object(engine, "client") as mock_client:
        mock_client.chat.completions.create.return_value = mock_response
        result = engine.analyze(sample_sql_info, sample_explain_result)

    assert isinstance(result, AnalysisResult)
    assert len(result.problems) == 1
    assert result.problems[0].severity == "warning"
    assert result.optimized_sql == "SELECT id FROM orders WHERE status='pending'"


def test_openai_analyze_handles_invalid_json(sample_sql_info, sample_explain_result):
    """Test OpenAIEngine handles invalid JSON response."""
    engine = OpenAIEngine(api_key="sk-test")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "not json"

    with patch.object(engine, "client") as mock_client:
        mock_client.chat.completions.create.return_value = mock_response
        result = engine.analyze(sample_sql_info, sample_explain_result)

    assert isinstance(result, AnalysisResult)
    assert result.optimized_sql == sample_sql_info.raw_sql


def test_ollama_analyze_with_mock_response(sample_sql_info, sample_explain_result):
    """Test OllamaEngine analyze with mocked httpx client."""
    engine = OllamaEngine(url="http://localhost:11434")

    mock_http_response = MagicMock()
    mock_http_response.json.return_value = {
        "message": {"content": json.dumps({
            "problems": [],
            "optimized_sql": "SELECT id FROM orders WHERE status='pending'",
            "index_ddls": ["CREATE INDEX idx_status ON orders(status);"],
            "explanation": "加索引",
        })}
    }
    mock_http_response.raise_for_status = MagicMock()

    with patch("sql_coach.ai.ollama.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_http_response
        mock_client_cls.return_value = mock_client

        result = engine.analyze(sample_sql_info, sample_explain_result)

    assert isinstance(result, AnalysisResult)
    assert result.optimized_sql == "SELECT id FROM orders WHERE status='pending'"
    assert len(result.index_ddls) == 1


def test_ollama_analyze_handles_api_failure(sample_sql_info, sample_explain_result):
    """Test OllamaEngine returns fallback when API always fails."""
    engine = OllamaEngine(url="http://localhost:11434", max_retries=2)

    with patch("sql_coach.ai.ollama.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.side_effect = httpx.ConnectError("connection refused")
        mock_client_cls.return_value = mock_client

        result = engine.analyze(sample_sql_info, sample_explain_result)

    assert isinstance(result, AnalysisResult)
    assert result.optimized_sql == sample_sql_info.raw_sql
    assert len(result.problems) == 1
    assert result.problems[0].severity == "critical"



# MockAIEngine tests
def test_mock_engine_name():
    from sql_coach.ai.mock import MockAIEngine
    engine = MockAIEngine()
    assert engine.name() == "mock"


def test_mock_engine_analyze_returns_result(sample_sql_info):
    from sql_coach.ai.mock import MockAIEngine
    engine = MockAIEngine()
    result = engine.analyze(sample_sql_info, None)
    assert isinstance(result, AnalysisResult)
    # SELECT * with WHERE -> should suggest optimization
    assert len(result.problems) >= 1
    assert result.optimized_sql  # non-empty


def test_factory_returns_mock_in_mock_mode():
    """Factory should return MockAIEngine when config.mock is True."""
    from sql_coach.models import Config, DBConfig
    from sql_coach.ai.factory import create_ai_engine
    from sql_coach.ai.mock import MockAIEngine
    db = DBConfig(host="localhost", port=3306, user="root",
                  password="x", database="test")
    config = Config(db=db, model="deepseek",
                    deepseek_api_key="", openai_api_key="",
                    ollama_url="http://localhost:11434",
                    benchmark_runs=3, mock=True)
    engine = create_ai_engine("deepseek", config)
    assert isinstance(engine, MockAIEngine)
