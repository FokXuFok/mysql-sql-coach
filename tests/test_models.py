# tests/test_models.py
from sql_coach.models import (
    SQLInfo, ExplainRow, ExplainResult, Problem,
    AnalysisResult, BenchmarkResult, DBConfig, Config
)


def test_sql_info_creation():
    info = SQLInfo(
        raw_sql="SELECT * FROM t",
        sql_type="SELECT",
        tables=["t"],
        columns=["*"],
        where_conditions=[],
        join_tables=[],
        order_by=[],
    )
    assert info.sql_type == "SELECT"
    assert info.tables == ["t"]


def test_explain_row_creation():
    row = ExplainRow(
        id=1, select_type="SIMPLE", table="orders",
        type="ALL", key=None, rows=420000, extra="Using where"
    )
    assert row.type == "ALL"
    assert row.key is None


def test_explain_result_flags():
    result = ExplainResult(
        rows=[],
        is_full_scan=True,
        missing_indexes=["orders"],
        problems=["orders 全表扫描"],
    )
    assert result.is_full_scan is True


def test_problem_severity():
    p = Problem(severity="critical", table="orders",
                description="full scan", suggestion="add index")
    assert p.severity == "critical"


def test_analysis_result():
    a = AnalysisResult(
        problems=[], optimized_sql="SELECT 1",
        index_ddls=["CREATE INDEX..."], explanation="ok"
    )
    assert a.optimized_sql == "SELECT 1"


def test_benchmark_result():
    b = BenchmarkResult(
        original_time=2.31, optimized_time=0.04,
        speedup=57.75, original_rows=420000, optimized_rows=200
    )
    assert b.speedup > 50


def test_db_config():
    c = DBConfig(host="localhost", port=3306, user="root",
                 password="x", database="test")
    assert c.port == 3306


def test_config_creation():
    db = DBConfig(host="localhost", port=3306, user="root",
                  password="x", database="test")
    c = Config(db=db, model="deepseek",
               deepseek_api_key="sk-x", openai_api_key="",
               ollama_url="http://localhost:11434",
               benchmark_runs=3, mock=False)
    assert c.model == "deepseek"


def test_complexity_dataclass_defaults():
    from sql_coach.models import Complexity
    c = Complexity(level="simple", score=0)
    assert c.reasons == []


def test_config_optimizer_fields_direct_construction():
    """直接构造 Config 时默认走 AI，保持既有行为不变。"""
    from sql_coach.models import Config, DBConfig
    config = Config(db=DBConfig(host="h", port=3306, user="u", password="p", database="d"),
                    model="deepseek", deepseek_api_key="k", openai_api_key="",
                    ollama_url="http://localhost:11434", benchmark_runs=3, mock=False)
    assert config.optimizer_mode == "ai"
    assert config.complexity_threshold == 8


def test_config_from_env_optimizer_defaults(monkeypatch):
    from sql_coach.models import Config
    monkeypatch.delenv("OPTIMIZER_MODE", raising=False)
    monkeypatch.delenv("COMPLEXITY_THRESHOLD", raising=False)
    config = Config.from_env()
    assert config.optimizer_mode == "auto"
    assert config.complexity_threshold == 8


def test_config_from_env_optimizer_override(monkeypatch):
    from sql_coach.models import Config
    monkeypatch.setenv("OPTIMIZER_MODE", "local")
    monkeypatch.setenv("COMPLEXITY_THRESHOLD", "5")
    config = Config.from_env()
    assert config.optimizer_mode == "local"
    assert config.complexity_threshold == 5