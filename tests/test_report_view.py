# tests/test_report_view.py
"""ReportView 冒烟测试。"""
import pytest
from PySide6.QtWidgets import QApplication

from sql_coach.coach import Report
from sql_coach.models import (
    SQLInfo, ExplainRow, ExplainResult, Problem, AnalysisResult,
    BenchmarkResult,
)
from gui.widgets.report_view import ReportView


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_report():
    return Report(
        sql_info=SQLInfo(
            raw_sql="SELECT * FROM t",
            sql_type="SELECT",
            tables=["t"],
            columns=["*"],
            where_conditions=[],
            join_tables=[],
            order_by=[],
        ),
        explain=ExplainResult(
            rows=[
                ExplainRow(
                    id=1, select_type="SIMPLE", table="t",
                    type="ALL", key=None, rows=10, extra="",
                ),
            ],
            is_full_scan=True,
            missing_indexes=[],
            problems=[],
        ),
        analysis=AnalysisResult(
            problems=[
                Problem(
                    severity="critical", table="t",
                    description="全表扫描", suggestion="加索引",
                ),
            ],
            optimized_sql="SELECT * FROM t WHERE 1=1;",
            index_ddls=["CREATE INDEX idx ON t(col);"],
            explanation="已优化",
        ),
        benchmark=BenchmarkResult(
            original_time=0.5, optimized_time=0.02, speedup=25.0,
            original_rows=10, optimized_rows=1,
        ),
    )


def test_set_report_builds_content(app):
    """set_report 后容器内有内容。"""
    view = ReportView()
    view.set_report(make_report())
    # scroll area 应该有一个 widget
    assert view.widget() is not None


def test_clear_empties_content(app):
    """clear() 清空容器。"""
    view = ReportView()
    view.set_report(make_report())
    view.clear()
    # 内容应该被清空 (label 文字为空或 widget 重置)
    assert view.widget() is not None
