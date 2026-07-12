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