# tests/test_analyze_worker.py
"""AnalyzeWorker 单元测试, 使用 pytest-qt。"""
from unittest.mock import patch, MagicMock

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from sql_coach.coach import Report
from sql_coach.models import (
    SQLInfo, AnalysisResult, Config, DBConfig,
)

from gui.workers.analyze_worker import AnalyzeWorker


def make_config(mock=True):
    """构造 mock 模式 Config。"""
    return Config(
        db=DBConfig(host="localhost", port=3306, user="root", password="", database="test"),
        model="deepseek",
        deepseek_api_key="",
        openai_api_key="",
        ollama_url="http://localhost:11434",
        benchmark_runs=3,
        mock=mock,
    )


def make_report():
    """构造一个最小 Report。"""
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
            explanation="ok",
        ),
        benchmark=None,
    )


@pytest.fixture(autouse=True)
def qapp(qapp):
    """pytest-qt 自动提供 QApplication。"""
    return qapp


def test_finished_signal_emits_report(qtbot):
    """正常完成: 发射 finished 信号, 携带 Report。"""
    config = make_config(mock=True)
    fake_report = make_report()
    fake_coach = MagicMock()
    fake_coach.analyze.return_value = fake_report
    fake_coach.connect.return_value = True

    with patch("gui.workers.analyze_worker.SQLCoach", return_value=fake_coach):
        worker = AnalyzeWorker(sql="SELECT 1", config=config, use_cache=False)

        captured = []
        worker.finished.connect(lambda r: captured.append(r))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert len(captured) == 1
        assert captured[0] is fake_report
        fake_coach.analyze.assert_called_once()
        fake_coach.close.assert_called_once()


def test_error_signal_on_exception(qtbot):
    """analyze 抛异常: 发射 error 信号, 携带错误信息。"""
    config = make_config(mock=True)
    fake_coach = MagicMock()
    fake_coach.connect.return_value = True
    fake_coach.analyze.side_effect = RuntimeError("boom")

    with patch("gui.workers.analyze_worker.SQLCoach", return_value=fake_coach):
        worker = AnalyzeWorker(sql="SELECT 1", config=config, use_cache=False)

        errors = []
        worker.error.connect(lambda msg: errors.append(msg))

        with qtbot.waitSignal(worker.error, timeout=5000):
            worker.start()

        assert len(errors) == 1
        assert "boom" in errors[0]


def test_stage_changed_signal_emitted(qtbot):
    """on_stage 回调 -> 发射 stage_changed 信号。"""
    config = make_config(mock=True)

    # 用真实回调验证 stage_changed 被触发
    def fake_analyze(sql, on_stage=None, on_chunk=None):
        if on_stage:
            on_stage("parse", 1, 4, "start")
            on_stage("parse", 1, 4, "done")
            on_stage("ai", 3, 4, "start")
            on_stage("ai", 3, 4, "done")
        return make_report()

    fake_coach = MagicMock()
    fake_coach.connect.return_value = True
    fake_coach.analyze.side_effect = fake_analyze

    with patch("gui.workers.analyze_worker.SQLCoach", return_value=fake_coach):
        worker = AnalyzeWorker(sql="SELECT 1", config=config, use_cache=False)

        stages = []
        worker.stage_changed.connect(lambda s: stages.append(s))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        # 至少触发 parse 和 ai 两个阶段
        assert "parse" in stages
        assert "ai" in stages
