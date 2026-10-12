# tests/test_formatter.py
from sql_coach.report.formatter import format_report, format_problems
from sql_coach.models import (
    SQLInfo, ExplainResult, ExplainRow, AnalysisResult,
    Problem, BenchmarkResult
)


def test_format_problems_empty():
    result = format_problems([])
    assert result == "未发现问题"


def test_format_problems_with_items():
    problems = [
        Problem(severity="critical", table="orders",
                description="full scan", suggestion="add index"),
        Problem(severity="warning", table="orders",
                description="SELECT *", suggestion="specify columns"),
    ]
    result = format_problems(problems)
    assert "orders" in result
    assert "full scan" in result


def test_format_report_basic():
    sql_info = SQLInfo(
        raw_sql="SELECT * FROM orders WHERE status='pending'",
        sql_type="SELECT", tables=["orders"], columns=["*"],
        where_conditions=["status='pending'"], join_tables=[], order_by=[],
    )
    explain = ExplainResult(
        rows=[ExplainRow(id=1, select_type="SIMPLE", table="orders",
                         type="ALL", key=None, rows=420000, extra="Using where")],
        is_full_scan=True, missing_indexes=["orders"],
        problems=["orders 全表扫描"],
    )
    analysis = AnalysisResult(
        problems=[Problem(severity="critical", table="orders",
                          description="full scan", suggestion="add index")],
        optimized_sql="SELECT id FROM orders FORCE INDEX(idx) WHERE status='pending'",
        index_ddls=["CREATE INDEX idx ON orders(status);"],
        explanation="添加索引",
    )

    output = format_report(sql_info, explain, analysis, None)
    assert "SELECT * FROM orders" in output
    assert "ALL" in output
    assert "SELECT id FROM orders FORCE INDEX" in output
    assert "CREATE INDEX" in output


def test_format_report_with_benchmark():
    sql_info = SQLInfo(
        raw_sql="SELECT * FROM t", sql_type="SELECT",
        tables=["t"], columns=["*"], where_conditions=[],
        join_tables=[], order_by=[],
    )
    explain = ExplainResult(
        rows=[], is_full_scan=False, missing_indexes=[], problems=[]
    )
    analysis = AnalysisResult(
        problems=[], optimized_sql="SELECT id FROM t",
        index_ddls=[], explanation="ok",
    )
    benchmark = BenchmarkResult(
        original_time=2.31, optimized_time=0.04,
        speedup=57.75, original_rows=420000, optimized_rows=200,
    )

    output = format_report(sql_info, explain, analysis, benchmark)
    assert "2.31" in output
    assert "0.04" in output
    assert "57" in output


def _minimal_report_parts():
    sql_info = SQLInfo(
        raw_sql="SELECT * FROM t", sql_type="SELECT",
        tables=["t"], columns=["*"], where_conditions=[],
        join_tables=[], order_by=[],
    )
    explain = ExplainResult(
        rows=[], is_full_scan=False, missing_indexes=[], problems=[]
    )
    analysis = AnalysisResult(
        problems=[], optimized_sql="SELECT id FROM t",
        index_ddls=[], explanation="说明文字",
    )
    return sql_info, explain, analysis


def test_format_report_local_engine_uses_local_title():
    """M9: 本地引擎时标题应为「本地规则说明」而非「AI 解释」。"""
    sql_info, explain, analysis = _minimal_report_parts()
    output = format_report(sql_info, explain, analysis, None, engine_used="local")
    assert "本地规则说明" in output
    assert "AI 解释" not in output


def test_format_report_default_engine_keeps_ai_title():
    """既有 4 参数调用行为不变，默认仍显示「AI 解释」。"""
    sql_info, explain, analysis = _minimal_report_parts()
    output = format_report(sql_info, explain, analysis, None)
    assert "AI 解释" in output


def test_format_report_explicit_ai_engine_uses_ai_title():
    sql_info, explain, analysis = _minimal_report_parts()
    output = format_report(sql_info, explain, analysis, None, engine_used="ai")
    assert "AI 解释" in output


def test_format_report_with_inf_speedup():
    """Test report handles infinite speedup."""
    sql_info = SQLInfo(
        raw_sql="SELECT * FROM t", sql_type="SELECT",
        tables=["t"], columns=["*"], where_conditions=[],
        join_tables=[], order_by=[],
    )
    explain = ExplainResult(
        rows=[], is_full_scan=False, missing_indexes=[], problems=[]
    )
    analysis = AnalysisResult(
        problems=[], optimized_sql="SELECT id FROM t",
        index_ddls=[], explanation="ok",
    )
    benchmark = BenchmarkResult(
        original_time=2.0, optimized_time=0.0,
        speedup=float("inf"), original_rows=1000, optimized_rows=10,
    )

    output = format_report(sql_info, explain, analysis, benchmark)
    assert "无限大" in output or "inf" in output.lower()


def test_format_report_with_index_impact():
    """提供 index_impact 时应渲染「索引实测」一节。"""
    from sql_coach.models import IndexImpact

    sql_info, explain, analysis = _minimal_report_parts()
    impact = IndexImpact(
        before_time=0.244, after_time=0.245, speedup=1.0,
        applied_ddls=["CREATE INDEX idx ON t(c);"], skipped_ddls=[],
        rolled_back=True,
    )
    output = format_report(sql_info, explain, analysis, None,
                           index_impact=impact)
    assert "索引实测" in output
    assert "0.244" in output
    assert "0.245" in output
    assert "1.0x" in output


def test_format_report_index_impact_error_shown():
    from sql_coach.models import IndexImpact

    sql_info, explain, analysis = _minimal_report_parts()
    impact = IndexImpact(
        before_time=0.1, after_time=0.1, speedup=1.0,
        applied_ddls=["CREATE INDEX idx ON t(c);"], skipped_ddls=[],
        rolled_back=False, error="回滚失败: boom",
    )
    output = format_report(sql_info, explain, analysis, None,
                           index_impact=impact)
    assert "回滚失败" in output


def test_format_report_default_no_index_impact_section():
    """未传 index_impact 时不出现「索引实测」一节（保持既有行为）。"""
    sql_info, explain, analysis = _minimal_report_parts()
    output = format_report(sql_info, explain, analysis, None)
    assert "索引实测" not in output


def test_format_report_index_impact_shows_verdict_and_selectivity():
    """有 verdict/selectivity 时输出包含「结论」与「命中率」。"""
    from sql_coach.models import IndexImpact

    sql_info, explain, analysis = _minimal_report_parts()
    impact = IndexImpact(
        before_time=0.244, after_time=0.005, speedup=48.8,
        applied_ddls=["CREATE INDEX idx ON t(c);"], skipped_ddls=[],
        rolled_back=True, matched_rows=1010, total_rows=100000,
        selectivity=0.0101, recommended=True,
        verdict="索引有效（实测提速 48.8x），建议采纳",
    )
    output = format_report(sql_info, explain, analysis, None,
                           index_impact=impact)
    assert "结论" in output
    assert "命中率" in output
    assert "建议采纳" in output


def test_format_report_index_impact_no_selectivity_hides_rate():
    """selectivity == -1 时不出现「命中率」行。"""
    from sql_coach.models import IndexImpact

    sql_info, explain, analysis = _minimal_report_parts()
    impact = IndexImpact(
        before_time=0.244, after_time=0.245, speedup=1.0,
        applied_ddls=[], skipped_ddls=[], rolled_back=True,
        verdict="索引收益有限（实测提速 1.00x），不建议创建",
    )
    output = format_report(sql_info, explain, analysis, None,
                           index_impact=impact)
    assert "结论" in output
    assert "命中率" not in output
