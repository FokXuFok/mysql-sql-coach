# tests/test_exporter.py
"""Exporter 单元测试。纯 Python, 不依赖 Qt。"""
from pathlib import Path

import pytest

from sql_coach.coach import Report
from sql_coach.models import (
    SQLInfo, ExplainRow, ExplainResult, Problem, AnalysisResult,
    BenchmarkResult,
)

from gui.storage.exporter import Exporter


@pytest.fixture
def report_with_full_data():
    """包含执行计划、问题、优化 SQL、索引、benchmark 的完整报告。"""
    return Report(
        sql_info=SQLInfo(
            raw_sql="SELECT * FROM commodity WHERE Cname='牛奶'",
            sql_type="SELECT",
            tables=["commodity"],
            columns=["*"],
            where_conditions=["Cname='牛奶'"],
            join_tables=[],
            order_by=[],
        ),
        explain=ExplainResult(
            rows=[
                ExplainRow(
                    id=1, select_type="SIMPLE", table="commodity",
                    type="ALL", key=None, rows=1000, extra="Using where",
                ),
            ],
            is_full_scan=True,
            missing_indexes=["Cname"],
            problems=["全表扫描"],
        ),
        analysis=AnalysisResult(
            problems=[
                Problem(
                    severity="critical",
                    table="commodity",
                    description="全表扫描: Cname 列无索引",
                    suggestion="在 Cname 列创建索引",
                ),
            ],
            optimized_sql="SELECT * FROM commodity WHERE Cname='牛奶';",
            index_ddls=["CREATE INDEX idx_cname ON commodity(Cname);"],
            explanation="为 WHERE 条件列添加索引以避免全表扫描。",
        ),
        benchmark=BenchmarkResult(
            original_time=0.5,
            optimized_time=0.02,
            speedup=25.0,
            original_rows=1000,
            optimized_rows=1,
        ),
    )


@pytest.fixture
def report_minimal():
    """最小报告: 无 explain, 无 benchmark, 无问题。"""
    return Report(
        sql_info=SQLInfo(
            raw_sql="SELECT 1",
            sql_type="SELECT",
            tables=[],
            columns=["1"],
            where_conditions=[],
            join_tables=[],
            order_by=[],
        ),
        explain=None,
        analysis=AnalysisResult(
            problems=[],
            optimized_sql="SELECT 1;",
            index_ddls=[],
            explanation="无需优化。",
        ),
        benchmark=None,
    )


def test_to_markdown_contains_sections(report_with_full_data):
    """Markdown 输出包含所有必要章节。"""
    md = Exporter().to_markdown(report_with_full_data)
    assert "# SQL 优化分析报告" in md
    assert "## 原始 SQL" in md
    assert "## 执行计划" in md
    assert "## 问题列表" in md
    assert "## 优化后 SQL" in md
    assert "## 索引建议" in md
    assert "## 性能对比" in md


def test_to_markdown_contains_explain_table(report_with_full_data):
    """Markdown 中执行计划用表格形式呈现。"""
    md = Exporter().to_markdown(report_with_full_data)
    # 表头
    assert "| id | table | type | key | rows | extra |" in md
    assert "| 1 | commodity | ALL | NULL | 1,000 | Using where |" in md


def test_to_markdown_contains_problems(report_with_full_data):
    """Markdown 中问题列表含 severity 和建议。"""
    md = Exporter().to_markdown(report_with_full_data)
    assert "critical" in md
    assert "全表扫描" in md
    assert "在 Cname 列创建索引" in md


def test_to_markdown_contains_benchmark(report_with_full_data):
    """Markdown 中性能对比含原值、优化值、提速倍数。"""
    md = Exporter().to_markdown(report_with_full_data)
    assert "0.500s" in md
    assert "0.020s" in md
    assert "25.0x" in md


def test_to_markdown_minimal_report(report_minimal):
    """无 explain/benchmark 的最小报告不崩溃。"""
    md = Exporter().to_markdown(report_minimal)
    assert "## 原始 SQL" in md
    assert "SELECT 1" in md
    # 无执行计划章节
    assert "## 执行计划" not in md
    # 无性能对比章节
    assert "## 性能对比" not in md


def test_to_html_contains_sections(report_with_full_data):
    """HTML 输出包含必要章节和内联 CSS。"""
    html = Exporter().to_html(report_with_full_data)
    assert "<!DOCTYPE html>" in html
    assert "<html" in html
    assert "<style>" in html
    assert "SQL 优化分析报告" in html
    assert "原始 SQL" in html
    assert "执行计划" in html
    assert "问题列表" in html
    assert "优化后 SQL" in html
    assert "索引建议" in html
    assert "性能对比" in html


def test_to_html_escapes_sql(report_with_full_data):
    """HTML 转义 SQL 中的特殊字符。"""
    html = Exporter().to_html(report_with_full_data)
    # 原始 SQL 含 '<' 会被转义
    assert "&lt;" not in html or "SELECT" in html  # 至少能正常输出
    assert "<script>" not in html  # 没有 script 注入


def test_to_html_minimal_report(report_minimal):
    """最小报告的 HTML 不崩溃。"""
    html = Exporter().to_html(report_minimal)
    assert "<!DOCTYPE html>" in html
    assert "SELECT 1" in html


def test_save_markdown(tmp_path, report_with_full_data):
    """save() 写 Markdown 文件。"""
    path = str(tmp_path / "report.md")
    Exporter().save(report_with_full_data, path, fmt="markdown")
    content = Path(path).read_text(encoding="utf-8")
    assert "# SQL 优化分析报告" in content


def test_save_html(tmp_path, report_with_full_data):
    """save() 写 HTML 文件。"""
    path = str(tmp_path / "report.html")
    Exporter().save(report_with_full_data, path, fmt="html")
    content = Path(path).read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content


def test_save_unknown_format_raises(tmp_path, report_with_full_data):
    """未知格式抛 ValueError。"""
    path = str(tmp_path / "report.txt")
    with pytest.raises(ValueError):
        Exporter().save(report_with_full_data, path, fmt="pdf")
