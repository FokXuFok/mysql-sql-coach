"""SQLCoach.generate_sql 端到端测试（mock 模式 / 连库 mock / 校验与错误处理）。"""
from unittest.mock import MagicMock, patch

import pytest

from sql_coach.coach import SQLCoach
from sql_coach.local.schema import Schema, TableSchema
from sql_coach.models import (
    Config, DBConfig, AnalysisResult, Problem, NLQueryResult,
)


def make_schema() -> Schema:
    """构造含 customers / orders / users 三张表的测试 schema。"""
    return Schema(tables={
        "customers": TableSchema(name="customers", columns={
            "id": "bigint", "name": "varchar", "city": "varchar",
            "amount": "decimal", "created_at": "datetime"}),
        "orders": TableSchema(name="orders", columns={
            "id": "bigint", "customer_id": "bigint", "status": "varchar",
            "amount": "decimal", "created_at": "datetime"}),
        "users": TableSchema(name="users", columns={
            "id": "bigint", "name": "varchar", "city": "varchar", "age": "int",
            "email": "varchar", "status": "varchar", "created_at": "datetime"}),
    })


def _config(mock: bool) -> Config:
    db = DBConfig(host="localhost", port=3306, user="root",
                  password="x", database="test")
    return Config(db=db, model="deepseek", deepseek_api_key="sk-test",
                  openai_api_key="", ollama_url="http://localhost:11434",
                  benchmark_runs=3, mock=mock)


@pytest.fixture
def mock_config() -> Config:
    return _config(mock=False)


@pytest.fixture
def mock_config_mock_mode() -> Config:
    return _config(mock=True)


def test_generate_sql_mock_mode(mock_config_mock_mode):
    """mock 模式下生成 SQL，且不执行查询。"""
    coach = SQLCoach(mock_config_mock_mode, use_cache=False)
    result = coach.generate_sql("查询10条订单", execute=False)

    assert isinstance(result, NLQueryResult)
    assert "SELECT" in result.generated_sql.upper()
    assert "LIMIT 10" in result.generated_sql.upper()
    assert result.executed is False
    assert result.rows == []
    assert result.columns == []


def test_generate_sql_mock_mode_does_not_execute_even_if_requested(mock_config_mock_mode):
    coach = SQLCoach(mock_config_mock_mode, use_cache=False)
    result = coach.generate_sql("查询10条订单", execute=True)
    assert result.executed is False


def test_generate_sql_warns_when_table_unknown(mock_config_mock_mode):
    """schema 为空 → 未识别表名，应产生 unknown_table 警告。"""
    coach = SQLCoach(mock_config_mock_mode, use_cache=False)
    result = coach.generate_sql("查询10条订单", execute=False)
    assert any("unknown_table" in w or "未能识别表名" in w for w in result.warnings)
    assert "unknown_table" in result.generated_sql


def test_generate_sql_returns_nl_query(mock_config_mock_mode):
    coach = SQLCoach(mock_config_mock_mode, use_cache=False)
    result = coach.generate_sql("查询10条订单", execute=False)
    assert result.nl_query.limit == 10
    assert result.nl_query.raw_text == "查询10条订单"


def test_generate_sql_executes_when_connected(mock_config):
    """连库模式下执行生成的 SQL，回填 columns / rows。"""
    with patch("sql_coach.coach.DBConnector") as db_cls:
        mock_db = MagicMock()
        mock_db.is_connected.return_value = True
        mock_db.query_with_columns.return_value = (["city", "cnt"], [("北京", 3)])
        db_cls.return_value = mock_db

        coach = SQLCoach(mock_config, use_cache=False)
        coach.schema_provider.load_all = lambda: make_schema()
        result = coach.generate_sql("统计每个城市的用户数量")

    assert result.executed is True
    assert result.columns == ["city", "cnt"]
    assert result.rows == [("北京", 3)]
    assert "GROUP BY city" in result.generated_sql


def test_generate_sql_not_connected_does_not_execute(mock_config):
    with patch("sql_coach.coach.DBConnector") as db_cls:
        mock_db = MagicMock()
        mock_db.is_connected.return_value = False
        db_cls.return_value = mock_db

        coach = SQLCoach(mock_config, use_cache=False)
        result = coach.generate_sql("查询10条订单", execute=True)

    assert result.executed is False
    assert not mock_db.query_with_columns.called


def test_generate_sql_records_error_on_failure(mock_config):
    """执行失败时写入 error，不抛异常。"""
    with patch("sql_coach.coach.DBConnector") as db_cls:
        mock_db = MagicMock()
        mock_db.is_connected.return_value = True
        mock_db.query_with_columns.side_effect = RuntimeError("boom")
        db_cls.return_value = mock_db

        coach = SQLCoach(mock_config, use_cache=False)
        coach.schema_provider.load_all = lambda: make_schema()
        result = coach.generate_sql("查询最近10条订单")

    assert result.executed is False
    assert result.error == "boom"
    assert result.generated_sql  # 仍展示生成的 SQL


def test_generate_sql_verify_uses_problems_not_optimized_sql(mock_config):
    """校验只取 problems 描述作 warnings，不采用 optimized_sql。"""
    fake = AnalysisResult(
        problems=[Problem(severity="warning", table="orders",
                          description="检测到全表扫描", suggestion="加索引")],
        optimized_sql="SELECT 1 /* 不应出现 */",
        index_ddls=[], explanation="",
    )
    with patch("sql_coach.coach.DBConnector") as db_cls, \
         patch("sql_coach.coach.LocalOptimizer") as lo_cls:
        mock_db = MagicMock()
        mock_db.is_connected.return_value = True
        mock_db.query_with_columns.return_value = ([], [])
        db_cls.return_value = mock_db
        lo_cls.return_value.optimize.return_value = fake

        coach = SQLCoach(mock_config, use_cache=False)
        coach.schema_provider.load_all = lambda: make_schema()
        result = coach.generate_sql("查询最近10条订单")

    assert "检测到全表扫描" in result.warnings
    assert "不应出现" not in result.generated_sql
    assert result.generated_sql == "SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;"


def test_generate_sql_verify_false_skips_optimizer(mock_config):
    with patch("sql_coach.coach.DBConnector") as db_cls, \
         patch("sql_coach.coach.LocalOptimizer") as lo_cls:
        mock_db = MagicMock()
        mock_db.is_connected.return_value = True
        mock_db.query_with_columns.return_value = ([], [])
        db_cls.return_value = mock_db

        coach = SQLCoach(mock_config, use_cache=False)
        coach.schema_provider.load_all = lambda: make_schema()
        result = coach.generate_sql("查询最近10条订单", verify=False)

    lo_cls.assert_not_called()
    assert result.generated_sql == "SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;"


def test_generate_sql_empty_schema_skips_verify(mock_config_mock_mode):
    """空 schema 时跳过校验（避免对未校验 schema 下结论）。"""
    with patch("sql_coach.coach.LocalOptimizer") as lo_cls:
        coach = SQLCoach(mock_config_mock_mode, use_cache=False)
        coach.generate_sql("查询10条订单", execute=False)
    lo_cls.assert_not_called()
