# tests/test_main_window.py
"""MainWindow 冒烟测试。"""
import pytest
from PySide6.QtWidgets import QApplication

from sql_coach.models import Config, DBConfig
from gui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_config():
    return Config(
        db=DBConfig(host="localhost", port=3306, user="root", password="", database="test"),
        model="deepseek",
        deepseek_api_key="",
        openai_api_key="",
        ollama_url="http://localhost:11434",
        benchmark_runs=3,
        mock=True,
    )


def test_main_window_constructs(app):
    """主窗口能正常构造。"""
    win = MainWindow(config=make_config())
    assert win.windowTitle() == "SQL Coach"
    assert win.sql_input is not None
    assert win.report_view is not None
    assert win.status_bar is not None


def test_clear_action_resets_ui(app):
    """Ctrl+L / 清空按钮重置 UI。"""
    win = MainWindow(config=make_config())
    win.sql_input.editor.setPlainText("SELECT 1")
    win._on_clear()
    assert win.sql_input.get_sql() == ""


def test_analyze_with_empty_sql_does_nothing(app):
    """空 SQL 不触发分析。"""
    win = MainWindow(config=make_config())
    win._on_analyze()  # 输入框为空
    assert win.worker is None


def _make_report(engine_used: str):
    from sql_coach.coach import Report
    from sql_coach.models import AnalysisResult, Complexity, SQLInfo

    return Report(
        sql_info=SQLInfo(raw_sql="SELECT 1", sql_type="SELECT", tables=[],
                         columns=[], where_conditions=[], join_tables=[], order_by=[]),
        explain=None,
        analysis=AnalysisResult(problems=[], optimized_sql="SELECT 1",
                                index_ddls=[], explanation="ok"),
        benchmark=None,
        engine_used=engine_used,
        complexity=Complexity(level="simple", score=0, reasons=[]),
    )


def test_status_bar_shows_local_engine(app):
    """本地引擎时状态栏显示「本地规则」而非 AI。"""
    win = MainWindow(config=make_config())
    win._on_analyze_finished(_make_report("local"))
    msg = win.status_bar.currentMessage()
    assert "本地规则" in msg
    assert "AI:" not in msg


def test_status_bar_shows_ai_engine(app):
    """AI 引擎时状态栏显示引擎名。"""
    win = MainWindow(config=make_config())
    win._on_analyze_finished(_make_report("deepseek"))
    msg = win.status_bar.currentMessage()
    assert "deepseek" in msg
    assert "耗时" in msg


def make_real_config():
    """非 mock 配置: 用于触发 _check_db_connection 的真实分支。"""
    cfg = make_config()
    cfg.mock = False
    return cfg


def test_db_failure_uses_non_modal_dialog(app, monkeypatch):
    """I2: 连库失败时不得弹模态框（模态会阻塞启动 / CI 挂起）。"""
    from PySide6.QtWidgets import QMessageBox
    from sql_coach import coach as coach_mod

    # 让数据库连接失败
    monkeypatch.setattr(coach_mod.SQLCoach, "connect", lambda self: False)
    # 避免测试在用户主目录创建缓存文件
    monkeypatch.setattr(coach_mod, "AnalysisCache", lambda *a, **k: None)

    # 任何模态路径被调用都应立即报错（证明没有进入嵌套事件循环）
    def _boom(*args, **kwargs):
        raise AssertionError("连库失败时走了模态弹窗路径")

    monkeypatch.setattr(QMessageBox, "exec", _boom)
    monkeypatch.setattr(QMessageBox, "warning", _boom)

    # 拦截真正的 show(): 非模态展示在无事件循环的测试进程里会留下原生窗口,
    # 导致解释器退出挂起。仅记录被调用, 以证明走的是非模态路径。
    shown = {}
    monkeypatch.setattr(QMessageBox, "show", lambda self: shown.__setitem__("called", True))

    win = MainWindow(config=make_real_config())
    assert shown.get("called") is True
    assert "模拟模式" in win.status_bar.currentMessage()


def test_analyze_error_does_not_block_ui(app, monkeypatch):
    """回归: 分析失败时不得用模态框卡死主窗口, 且 UI 必须恢复可交互。

    历史 bug: `_on_analyze_error` 调用模态 `QMessageBox.critical`，会进入嵌套
    事件循环 —— 用户没注意到弹窗时，输入框点不动、所有按钮无响应。
    注意：仅改成 `show()` 还不够，`QMessageBox` **默认是应用级模态**，
    必须显式 `setWindowModality(Qt.NonModal)`，否则仍会拦住主窗口输入。
    """
    import time
    from unittest.mock import patch
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    from sql_coach import coach as coach_mod

    def _boom(*args, **kwargs):
        raise AssertionError("分析失败时走了模态弹窗路径（会卡死主窗口）")

    monkeypatch.setattr(QMessageBox, "critical", _boom)
    monkeypatch.setattr(QMessageBox, "exec", _boom)

    win = MainWindow(config=make_config())
    with patch.object(coach_mod.SQLCoach, "analyze", side_effect=RuntimeError("模拟失败")):
        win._start_analyze("SELECT 1")
        for _ in range(100):
            QApplication.processEvents()
            if win.worker is None:
                break
            time.sleep(0.05)

    assert win.worker is None
    assert win.sql_input.editor.isReadOnly() is False
    assert win._analyze_action.isEnabled() is True

    box = win._message_boxes[-1]
    assert box is not None, "失败时应给出提示"
    assert box.windowModality() == Qt.NonModal, "提示框必须是非模态，否则会卡住主窗口"
    assert QApplication.activeModalWidget() is None
    box.close()


# ---------------- Task 15: 模式切换与 NL 流程 ----------------

def make_nl_result(warnings=None, error=""):
    """构造一个最小 NLQueryResult。"""
    from sql_coach.models import NLQuery, NLQueryResult
    return NLQueryResult(
        nl_query=NLQuery(
            intent="select", tables=["orders"], columns=["id"],
            conditions=[], aggregates=[], order_by=[], group_by=[],
            limit=10, raw_text="查询10条订单",
        ),
        generated_sql="SELECT id FROM orders LIMIT 10;",
        columns=["id"],
        rows=[(1,), (2,)],
        warnings=warnings or [],
        executed=True,
        error=error,
    )


def test_default_mode_is_optimize(app):
    """默认进入优化模式, 左侧显示 sql_input。"""
    win = MainWindow(config=make_config())
    assert win.mode_combo.currentText() == "优化模式"
    assert win.left_stack.currentWidget() is win.sql_input
    assert win.right_stack.currentWidget() is win.report_view
    assert win._analyze_action.isEnabled() is True


def test_switch_to_nl_mode_disables_optimize_actions(app):
    """切到 NL 模式: nl_input 可见, 分析/导出按钮禁用。"""
    win = MainWindow(config=make_config())
    win.mode_combo.setCurrentIndex(1)
    assert win.mode_combo.currentText() == "自然语言模式"
    assert win.left_stack.currentWidget() is win.nl_input
    assert win.right_stack.currentWidget() is win.nl_container
    assert win._analyze_action.isEnabled() is False
    assert win._export_action.isEnabled() is False


def test_switch_back_to_optimize_enables_actions(app):
    """切回优化模式恢复按钮。"""
    win = MainWindow(config=make_config())
    win.mode_combo.setCurrentIndex(1)
    win.mode_combo.setCurrentIndex(0)
    assert win.left_stack.currentWidget() is win.sql_input
    assert win.right_stack.currentWidget() is win.report_view
    assert win._analyze_action.isEnabled() is True
    assert win._export_action.isEnabled() is True


def test_optimize_requested_fills_sql_input_and_switches_mode(app):
    """送入优化模式: SQL 填入 sql_input 并切回优化模式。"""
    win = MainWindow(config=make_config())
    win.mode_combo.setCurrentIndex(1)
    win.sql_display.optimize_requested.emit("SELECT 42;")
    assert win.sql_input.editor.toPlainText() == "SELECT 42;"
    assert win.mode_combo.currentIndex() == 0
    assert win.left_stack.currentWidget() is win.sql_input


def test_nl_generate_renders_result(app, monkeypatch):
    """NL 模式端到端: 生成 SQL 后渲染 SQL 与结果表格。"""
    import time
    from unittest.mock import MagicMock
    from gui.workers import nl_worker as nw_mod

    fake_coach = MagicMock()
    fake_coach.connect.return_value = True
    fake_coach.generate_sql.return_value = make_nl_result()
    monkeypatch.setattr(nw_mod, "SQLCoach", lambda *a, **k: fake_coach)

    win = MainWindow(config=make_config())
    win.mode_combo.setCurrentIndex(1)
    win.nl_input.editor.setPlainText("查询10条订单")
    win.nl_input.generate_button.click()

    for _ in range(100):
        QApplication.processEvents()
        if win.nl_worker is None:
            break
        time.sleep(0.05)

    assert win.nl_worker is None
    assert win.nl_input.editor.isReadOnly() is False
    assert win.sql_display.get_sql() == "SELECT id FROM orders LIMIT 10;"
    assert win.query_result.table.rowCount() == 2


def test_nl_warnings_shown_non_modal(app, monkeypatch):
    """warnings 用非模态提示展示, 不得走模态路径。"""
    import time
    from unittest.mock import MagicMock
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    from gui.workers import nl_worker as nw_mod

    def _boom(*args, **kwargs):
        raise AssertionError("NL 提示走了模态路径")

    monkeypatch.setattr(QMessageBox, "critical", _boom)
    monkeypatch.setattr(QMessageBox, "exec", _boom)

    fake_coach = MagicMock()
    fake_coach.connect.return_value = True
    fake_coach.generate_sql.return_value = make_nl_result(warnings=["未识别表名"])
    monkeypatch.setattr(nw_mod, "SQLCoach", lambda *a, **k: fake_coach)

    win = MainWindow(config=make_config())
    win.mode_combo.setCurrentIndex(1)
    win.nl_input.editor.setPlainText("查询10条订单")
    win.nl_input.generate_button.click()

    for _ in range(100):
        QApplication.processEvents()
        if win.nl_worker is None:
            break
        time.sleep(0.05)

    box = win._message_boxes[-1]
    assert box is not None
    assert "未识别表名" in box.text()
    assert box.windowModality() == Qt.NonModal
    box.close()


def test_nl_error_restores_ui(app, monkeypatch):
    """NL 生成失败: 非模态提示 + UI 幂等恢复。"""
    import time
    from unittest.mock import MagicMock
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    from gui.workers import nl_worker as nw_mod

    def _boom(*args, **kwargs):
        raise AssertionError("NL 失败时走了模态路径")

    monkeypatch.setattr(QMessageBox, "critical", _boom)
    monkeypatch.setattr(QMessageBox, "exec", _boom)

    fake_coach = MagicMock()
    fake_coach.connect.return_value = True
    fake_coach.generate_sql.side_effect = RuntimeError("模拟失败")
    monkeypatch.setattr(nw_mod, "SQLCoach", lambda *a, **k: fake_coach)

    win = MainWindow(config=make_config())
    win.mode_combo.setCurrentIndex(1)
    win._start_nl_generate("查询10条订单")

    for _ in range(100):
        QApplication.processEvents()
        if win.nl_worker is None:
            break
        time.sleep(0.05)

    assert win.nl_worker is None
    assert win.nl_input.editor.isReadOnly() is False
    box = win._message_boxes[-1]
    assert box is not None
    assert box.windowModality() == Qt.NonModal
    box.close()


def test_message_boxes_retained_across_calls(app):
    """Minor 6：连续两次提示都须保活，避免前一个弹框被 GC。"""
    from PySide6.QtWidgets import QMessageBox

    win = MainWindow(config=make_config())
    win._show_message("提示一", "1", QMessageBox.Warning)
    win._show_message("提示二", "2", QMessageBox.Critical)

    assert len(win._message_boxes) >= 2
    texts = [b.text() for b in win._message_boxes[-2:]]
    assert texts == ["1", "2"]
    for b in win._message_boxes:
        b.close()


def test_nl_status_bar_flags_warnings(app, monkeypatch):
    """有 warnings 时状态栏必须显眼提示，避免用户误以为结果就是他要的。"""
    from sql_coach.models import NLQuery, NLQueryResult

    win = MainWindow(config=make_config())
    result = NLQueryResult(
        nl_query=NLQuery(intent="select", tables=["users"], columns=[],
                         conditions=[], aggregates=[], order_by=[], group_by=[]),
        generated_sql="SELECT * FROM users;",
        warnings=["未识别到可聚合的列（关键词：销售额）"],
    )
    shown = []
    monkeypatch.setattr(win, "_show_message", lambda *a, **k: shown.append(a))
    win._on_nl_finished(result)

    msg = win.status_bar.currentMessage()
    assert "⚠" in msg
    assert "1 条提示" in msg
    assert shown, "仍应弹出提示框"


class _FakeCoach:
    """替身：不真连库，按键结果返回。"""

    next_ok = True
    instances = 0

    def __init__(self, config):
        self.config = config
        self.db = self
        self.last_error = "" if _FakeCoach.next_ok else "Access denied for user 'root'"
        _FakeCoach.instances += 1

    def connect(self):
        return _FakeCoach.next_ok

    def close(self):
        pass


def test_saved_settings_reload_env_without_restart(app, monkeypatch, tmp_path):
    """回归测试：设置保存到 .env 后立即生效，不需要关掉程序重开。

    这是「第 4 幕勾选索引实测却没出现实测结果、只能重开程序」的根因：
    保存后既不重载新值，也不重试数据库连接（mock 状态被永久沿用）。
    """
    env = tmp_path / ".env"
    env.write_text("DB_NAME=test\nMEASURE_INDEX=false\n", encoding="utf-8")
    monkeypatch.delenv("MEASURE_INDEX", raising=False)
    _FakeCoach.next_ok = True
    _FakeCoach.instances = 0
    monkeypatch.setattr("sql_coach.coach.SQLCoach", _FakeCoach)

    win = MainWindow(config=make_config(), env_path=str(env))
    assert win.config.measure_index is False
    assert win.config.mock is True          # 初始配置是 mock

    # 模拟用户勾选「索引实测」并点「保存到 .env」
    env.write_text("DB_NAME=test\nMEASURE_INDEX=true\n", encoding="utf-8")

    win._reload_after_settings_saved()

    assert win.config.measure_index is True, "保存后新配置必须立即生效"
    assert win.config.mock is False, "保存后必须重试真实连接，不能沿用 mock"
    assert _FakeCoach.instances == 1
    assert "已连接" in win.status_bar.currentMessage()


def test_check_db_connection_retries_after_startup_failure(app, monkeypatch):
    """force_retry=True 时必须忽略 mock 状态重新尝试，并能从 mock 恢复。"""
    _FakeCoach.next_ok = True
    _FakeCoach.instances = 0
    monkeypatch.setattr("sql_coach.coach.SQLCoach", _FakeCoach)

    win = MainWindow(config=make_config())
    # 默认行为：已经是 mock 就直接返回，不再尝试连接
    win._check_db_connection()
    assert _FakeCoach.instances == 0

    win._check_db_connection(force_retry=True)
    assert _FakeCoach.instances == 1
    assert win.config.mock is False


def test_check_db_connection_shows_real_error(app, monkeypatch):
    """连库失败时要把真实原因显示出来，而不是只说"已切换到模拟模式"。"""
    _FakeCoach.next_ok = False
    monkeypatch.setattr("sql_coach.coach.SQLCoach", _FakeCoach)

    win = MainWindow(config=make_config())
    shown = []
    monkeypatch.setattr(win, "_show_db_fallback", lambda m: shown.append(m))

    win._check_db_connection(force_retry=True)

    assert win.config.mock is True
    assert win.status_bar.currentMessage() == "DB: 模拟模式"
    assert shown and "Access denied" in shown[0]


def _report_with_benchmark_and_impact():
    """构造一份同时带「性能对比」和「索引实测」的报告。"""
    from sql_coach.coach import Report
    from sql_coach.models import (
        AnalysisResult, BenchmarkResult, Complexity, IndexImpact, SQLInfo,
    )

    return Report(
        sql_info=SQLInfo(raw_sql="SELECT * FROM orders WHERE amount>999.5",
                         sql_type="SELECT", tables=["orders"],
                         columns=["amount"], where_conditions=["amount>999.5"],
                         join_tables=[], order_by=[]),
        explain=None,
        analysis=AnalysisResult(
            problems=[], optimized_sql="SELECT amount FROM orders",
            index_ddls=["CREATE INDEX idx_orders_amount ON orders(amount);"],
            explanation="本地规则引擎命中规则"),
        benchmark=BenchmarkResult(original_time=0.041, optimized_time=0.001,
                                  speedup=41.0, original_rows=100000,
                                  optimized_rows=50),
        engine_used="local",
        complexity=Complexity(level="simple", score=0),
        index_impact=IndexImpact(
            before_time=0.041, after_time=0.001, speedup=41.0,
            applied_ddls=["CREATE INDEX idx_orders_amount ON orders(amount);"],
            skipped_ddls=[], rolled_back=True, matched_rows=50,
            total_rows=100000, selectivity=0.0005, recommended=True,
            verdict="索引有效（实测提速 41.0x），建议采纳"),
    )


def test_report_renders_index_impact_even_if_chart_fails(app, monkeypatch):
    """回归测试：图表章节渲染失败时，「索引实测」必须仍然出现在报告里。

    打包环境下 matplotlib 相关渲染抛异常时，原先会让整份报告停在「性能对比」，
    导致「索引实测」永远不出现（表现为"设置里开了索引实测却没有对比"）。
    """
    win = MainWindow(config=make_config())

    def boom(*args, **kwargs):
        raise RuntimeError("simulated chart failure")

    monkeypatch.setattr("gui.widgets.benchmark_chart.BenchmarkChartWidget", boom)
    win.report_view.set_report(_report_with_benchmark_and_impact())

    from PySide6.QtWidgets import QLabel

    labels = [lbl.text() for lbl in win.report_view._container.findChildren(QLabel)]
    assert any("索引实测" in t for t in labels), "索引实测章节不应因图表失败而消失"
    assert any("本节渲染失败" in t for t in labels), "失败章节应给出占位提示"
    assert any("索引建议" in t for t in labels), "失败章节之前的章节也应保留"


def test_analyze_finished_resets_ui_when_render_fails(app, monkeypatch):
    """渲染抛异常时仍要复位 UI 并更新状态栏，不能一直停在"分析中"。"""
    import time

    win = MainWindow(config=make_config())

    class _History:
        def add(self, **kwargs):
            return "x"

    shown = []
    monkeypatch.setattr(win, "history", _History())
    monkeypatch.setattr(win, "_show_message", lambda *a, **k: shown.append(a))

    def boom(report):
        raise RuntimeError("render boom")

    monkeypatch.setattr(win.report_view, "set_report", boom)
    win._analyze_start_time = time.perf_counter()

    win._on_analyze_finished(_report_with_benchmark_and_impact())

    msg = win.status_bar.currentMessage()
    assert "渲染异常" in msg, msg
    assert win.sql_input.editor.isReadOnly() is False, "UI 必须回到可交互状态"
    assert shown, "必须弹出渲染失败提示，而不是静默失败"


def test_nl_finished_keeps_worker_until_thread_finishes(app):
    """回归测试：完成槽函数不得在 QThread 真正结束前丢弃 worker 引用。

    否则 QThread 对象会在 run() 尚未返回时被回收，Qt 会直接
    qFatal("QThread: Destroyed while thread is still running") 终止进程
    （Windows 异常码 0xC0000409，表现为点「生成 SQL」后程序直接消失）。
    """
    from sql_coach.models import NLQuery, NLQueryResult

    win = MainWindow(config=make_config())
    sentinel = object()
    win.nl_worker = sentinel                     # 模拟"线程仍在运行"

    result = NLQueryResult(
        nl_query=NLQuery(intent="select", tables=["users"], columns=[],
                         conditions=[], aggregates=[], order_by=[], group_by=[]),
        generated_sql="SELECT city, COUNT(*) FROM users GROUP BY city;",
        columns=["city", "cnt"], rows=[("北京", 2)],
    )
    win._on_nl_finished(result)

    assert win.nl_worker is sentinel, "线程结束前不得丢弃 worker 引用"
    assert win.nl_input.editor.isReadOnly() is False, "但输入框要立即恢复可用"

    # 线程真正结束后，才由 finished 的槽负责释放
    win._reset_nl_ui()
    assert win.nl_worker is None


def test_analyze_finished_keeps_worker_until_thread_finishes(app, monkeypatch):
    """同上的分析路径：完成槽不得提前丢弃 worker 引用。"""
    win = MainWindow(config=make_config())

    class _History:
        def add(self, **kwargs):
            return "x"

    monkeypatch.setattr(win, "history", _History())
    sentinel = object()
    win.worker = sentinel

    win._on_analyze_finished(_report_with_benchmark_and_impact())

    assert win.worker is sentinel, "线程结束前不得丢弃 worker 引用"
    assert win.sql_input.editor.isReadOnly() is False
