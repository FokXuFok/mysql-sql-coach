# tests/test_nl_worker.py
"""NlWorker 单元测试, 使用 pytest-qt。"""
from unittest.mock import patch, MagicMock

from PySide6.QtCore import QThread

from sql_coach.models import Config, DBConfig, NLQuery, NLQueryResult

from gui.workers.nl_worker import NlWorker


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


def make_result():
    """构造一个最小 NLQueryResult。"""
    nl_query = NLQuery(
        intent="select", tables=["orders"], columns=["id"],
        conditions=[], aggregates=[], order_by=[], group_by=[],
        limit=10, raw_text="查询10条订单",
    )
    return NLQueryResult(
        nl_query=nl_query,
        generated_sql="SELECT id FROM orders LIMIT 10;",
        columns=["id"],
        rows=[(1,), (2,)],
        warnings=[],
        executed=True,
        error="",
    )


def test_nl_done_signal_emits_result(qtbot):
    """正常完成: 发射 nl_done 信号, 携带 NLQueryResult。"""
    config = make_config(mock=True)
    fake_result = make_result()
    fake_coach = MagicMock()
    fake_coach.connect.return_value = True
    fake_coach.generate_sql.return_value = fake_result

    with patch("gui.workers.nl_worker.SQLCoach", return_value=fake_coach):
        worker = NlWorker(text="查询10条订单", config=config)

        captured = []
        worker.nl_done.connect(lambda r: captured.append(r))

        with qtbot.waitSignal(worker.nl_done, timeout=5000):
            worker.start()

        assert len(captured) == 1
        assert captured[0] is fake_result
        fake_coach.connect.assert_called_once()
        fake_coach.generate_sql.assert_called_once_with(
            "查询10条订单", execute=True, verify=True)
        fake_coach.close.assert_called_once()


def test_error_signal_on_exception(qtbot):
    """generate_sql 抛异常: 发射 error 信号, 携带错误信息。"""
    config = make_config(mock=True)
    fake_coach = MagicMock()
    fake_coach.connect.return_value = True
    fake_coach.generate_sql.side_effect = RuntimeError("boom")

    with patch("gui.workers.nl_worker.SQLCoach", return_value=fake_coach):
        worker = NlWorker(text="查询10条订单", config=config)

        errors = []
        worker.error.connect(lambda msg: errors.append(msg))

        with qtbot.waitSignal(worker.error, timeout=5000):
            worker.start()

        assert len(errors) == 1
        assert "boom" in errors[0]


def test_close_called_even_when_generate_raises(qtbot):
    """Minor 7：generate_sql 抛异常时仍须 close()，避免连接泄漏。"""
    config = make_config(mock=True)
    fake_coach = MagicMock()
    fake_coach.connect.return_value = True
    fake_coach.generate_sql.side_effect = RuntimeError("boom")

    with patch("gui.workers.nl_worker.SQLCoach", return_value=fake_coach):
        worker = NlWorker(text="查询10条订单", config=config)
        with qtbot.waitSignal(worker.error, timeout=5000):
            worker.start()

        fake_coach.close.assert_called_once()


def test_does_not_override_qthread_finished():
    """自定义信号不得叫 finished, 否则会覆盖 QThread 内置信号。"""
    assert "finished" not in NlWorker.__dict__
    assert "nl_done" in NlWorker.__dict__


def test_builtin_finished_still_emits(qtbot):
    """QThread 内置 finished 未被覆盖, 线程结束时仍会发射（UI 兜底恢复依赖它）。"""
    config = make_config(mock=True)
    fake_coach = MagicMock()
    fake_coach.connect.return_value = True
    fake_coach.generate_sql.return_value = make_result()

    with patch("gui.workers.nl_worker.SQLCoach", return_value=fake_coach):
        worker = NlWorker(text="查询10条订单", config=config)
        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()
