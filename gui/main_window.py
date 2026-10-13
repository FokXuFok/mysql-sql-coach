# gui/main_window.py
"""主窗口, 左右分栏组装所有组件。"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QMainWindow, QMessageBox, QSplitter,
    QStackedWidget, QStatusBar, QToolBar, QVBoxLayout, QWidget,
)

from sql_coach.coach import Report
from sql_coach.config import load_config
from sql_coach.models import Config

from gui.storage.history_store import HistoryStore
from gui.storage.exporter import Exporter
from gui.widgets.history_dialog import HistoryDialog
from gui.widgets.nl_input_widget import NlInputWidget
from gui.widgets.query_result_widget import QueryResultWidget
from gui.widgets.report_view import ReportView
from gui.widgets.settings_dialog import SettingsDialog
from gui.widgets.sql_display_widget import SqlDisplayWidget
from gui.widgets.sql_input import SqlInputWidget
from gui.workers.analyze_worker import AnalyzeWorker, stage_label
from gui.workers.nl_worker import NlWorker

# 模式下拉的顺序即 QStackedWidget 的索引
MODE_OPTIMIZE = 0
MODE_NL = 1


class MainWindow(QMainWindow):
    """主窗口: 左右分栏 SqlInputWidget + ReportView。"""

    def __init__(
        self,
        config: Optional[Config] = None,
        env_path: str = ".env",
    ) -> None:
        super().__init__()
        self.config = config or load_config(env_path=env_path)
        self.env_path = env_path
        self.history = HistoryStore()
        self.exporter = Exporter()
        self.worker: Optional[AnalyzeWorker] = None
        self.nl_worker: Optional[NlWorker] = None
        self.last_report: Optional[Report] = None
        self._analyze_start_time: float = 0.0
        # 非模态提示框保活列表：同时弹出多个时，避免前一个被 GC
        self._message_boxes: list[QMessageBox] = []

        self.setWindowTitle("SQL Coach")
        self.resize(1200, 800)
        self.setMinimumSize(800, 600)

        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._build_statusbar()
        self._connect_signals()
        self._check_db_connection()

    # ---- UI 构建 ----
    def _build_ui(self) -> None:
        """左右分栏 40% / 60%; 每侧用 QStackedWidget 承载两种模式。"""
        splitter = QSplitter(Qt.Horizontal)

        # 左侧: 优化模式(SQL 输入) / NL 模式(自然语言输入)
        self.sql_input = SqlInputWidget()
        self.nl_input = NlInputWidget()
        self.left_stack = QStackedWidget()
        self.left_stack.addWidget(self.sql_input)  # 索引 0
        self.left_stack.addWidget(self.nl_input)   # 索引 1

        # 右侧: 优化模式(报告) / NL 模式(SQL 展示 + 结果表格)
        self.report_view = ReportView()
        self.sql_display = SqlDisplayWidget()
        self.query_result = QueryResultWidget()
        self.nl_container = QWidget()
        nl_layout = QVBoxLayout(self.nl_container)
        nl_layout.setContentsMargins(0, 0, 0, 0)
        nl_layout.setSpacing(0)
        nl_splitter = QSplitter(Qt.Vertical)
        nl_splitter.addWidget(self.sql_display)
        nl_splitter.addWidget(self.query_result)
        nl_splitter.setStretchFactor(0, 4)
        nl_splitter.setStretchFactor(1, 6)
        nl_splitter.setSizes([320, 480])
        nl_layout.addWidget(nl_splitter)

        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(self.report_view)   # 索引 0
        self.right_stack.addWidget(self.nl_container)  # 索引 1

        splitter.addWidget(self.left_stack)
        splitter.addWidget(self.right_stack)
        splitter.setStretchFactor(0, 4)  # 40%
        splitter.setStretchFactor(1, 6)  # 60%
        splitter.setSizes([480, 720])

        self.setCentralWidget(splitter)

    def _build_menu(self) -> None:
        """菜单栏: 文件 / 设置 / 帮助。"""
        menubar = self.menuBar()

        # 文件
        file_menu = menubar.addMenu("文件")
        export_action = QAction("导出报告 ...", self)
        export_action.setShortcut("Ctrl+S")
        export_action.triggered.connect(self._on_export)
        file_menu.addAction(export_action)

        file_menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # 设置
        settings_menu = menubar.addMenu("设置")
        settings_action = QAction("打开设置 ...", self)
        settings_action.triggered.connect(self._on_open_settings)
        settings_menu.addAction(settings_action)

        # 帮助
        help_menu = menubar.addMenu("帮助")
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _build_toolbar(self) -> None:
        """工具栏: 模式下拉 + 5 个按钮。"""
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # 模式切换放在最左侧
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["优化模式", "自然语言模式"])
        toolbar.addWidget(self.mode_combo)
        toolbar.addSeparator()

        analyze_btn = toolbar.addAction("🔍 分析")
        analyze_btn.triggered.connect(self._on_analyze)
        self._analyze_action = analyze_btn

        clear_btn = toolbar.addAction("🗑 清空")
        clear_btn.triggered.connect(self._on_clear)

        export_btn = toolbar.addAction("💾 导出报告")
        export_btn.triggered.connect(self._on_export)
        self._export_action = export_btn

        history_btn = toolbar.addAction("🕘 历史")
        history_btn.triggered.connect(self._on_history)

        settings_btn = toolbar.addAction("⚙ 设置")
        settings_btn.triggered.connect(self._on_open_settings)

    def _build_statusbar(self) -> None:
        """状态栏: 左状态文字, 右元信息。"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    def _connect_signals(self) -> None:
        """连接信号槽 + 快捷键。"""
        self.sql_input.analyze_requested.connect(self._start_analyze)
        self.nl_input.generate_requested.connect(self._start_nl_generate)
        self.sql_display.optimize_requested.connect(self._on_optimize_requested)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        # Ctrl+L 清空
        clear_sc = QShortcut(QKeySequence("Ctrl+L"), self)
        clear_sc.activated.connect(self._on_clear)

    # ---- 业务逻辑 ----
    def _check_db_connection(self) -> None:
        """启动时测试 DB 连通性, 失败则切 mock 模式。"""
        if self.config.mock:
            self.status_bar.showMessage("DB: 模拟模式")
            return
        from sql_coach.coach import SQLCoach
        try:
            coach = SQLCoach(self.config)
            ok = coach.connect()
            coach.close()
            if ok:
                self.status_bar.showMessage("DB: 已连接")
            else:
                self.config.mock = True
                self._show_db_fallback("已切换到模拟模式")
                self.status_bar.showMessage("DB: 模拟模式")
        except Exception as e:
            self.config.mock = True
            self._show_db_fallback(f"已切换到模拟模式\n错误: {e}")
            self.status_bar.showMessage("DB: 模拟模式")

    def _show_db_fallback(self, message: str) -> None:
        """非模态提示连库失败。"""
        self._show_message("数据库连接失败", message, QMessageBox.Warning)

    def _show_message(self, title: str, text: str, icon) -> None:
        """非模态提示框。

        必须同时做两件事，缺一不可：
        1. 用 ``show()`` 而不是模态静态方法（``warning``/``critical``）——后者进入嵌套事件循环；
        2. 显式 ``setWindowModality(Qt.NonModal)`` —— ``QMessageBox`` **默认是应用级模态**，
           只调 ``show()`` 虽然不阻塞代码，但仍会拦住主窗口的输入，用户没注意到弹窗时
           就会觉得"点哪都没反应"。
        """
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(icon)
        box.setWindowModality(Qt.NonModal)
        box.setModal(False)
        # 保存到列表（保留最近 5 个），防止同时弹出多个时前面的被 GC
        self._message_boxes.append(box)
        self._message_boxes = self._message_boxes[-5:]
        box.show()

    def _on_analyze(self) -> None:
        """工具栏分析按钮回调。"""
        sql = self.sql_input.get_sql()
        if sql.strip():
            self._start_analyze(sql)

    def _start_analyze(self, sql: str) -> None:
        """启动后台分析线程。"""
        if self.worker is not None:
            return  # 正在分析, 忽略
        self.sql_input.set_readonly(True)
        self._analyze_action.setEnabled(False)
        self.status_bar.showMessage("分析中 ...")
        self._analyze_start_time = time.perf_counter()

        self.worker = AnalyzeWorker(
            sql=sql, config=self.config, use_cache=not self.config.mock,
        )
        self.worker.stage_changed.connect(self._on_stage_changed)
        self.worker.analysis_done.connect(self._on_analyze_finished)
        self.worker.error.connect(self._on_analyze_error)
        # QThread 内置 finished 总会发射 -> 作为兜底, 保证 UI 一定回到可交互状态
        self.worker.finished.connect(self._reset_analysis_ui)
        self.worker.analysis_done.connect(self.worker.deleteLater)
        self.worker.error.connect(self.worker.deleteLater)
        self.worker.start()

    def _reset_analysis_ui(self) -> None:
        """恢复 UI 到可交互状态。幂等, 可被多个信号调用。"""
        self.sql_input.set_readonly(False)
        self._analyze_action.setEnabled(True)
        self.worker = None

    def _on_stage_changed(self, stage: str) -> None:
        """更新状态栏文字。"""
        self.status_bar.showMessage(stage_label(stage) + " ...")

    def _on_analyze_finished(self, report: Report) -> None:
        """分析完成: 渲染报告 + 存历史 + 恢复 UI。"""
        elapsed = (time.perf_counter() - self._analyze_start_time) * 1000
        self.last_report = report
        self.report_view.set_report(report)

        # 存入历史
        try:
            self.history.add(
                sql=report.sql_info.raw_sql,
                report=report,
                ai_time_ms=elapsed,
            )
        except Exception:
            pass  # 历史记录失败不影响主流程

        self._reset_analysis_ui()
        engine = "本地规则" if report.engine_used == "local" else report.engine_used
        self.status_bar.showMessage(
            f"完成 | {engine} | 耗时 {elapsed/1000:.1f}s"
        )

    def _on_analyze_error(self, msg: str) -> None:
        """分析出错: 提示 + 恢复 UI。

        用**非模态**提示而非 ``QMessageBox.critical``: 后者会进入嵌套事件循环,
        在用户没注意到弹窗时会让整个主窗口"点哪都没反应"(输入框也无法输入)。
        """
        self._reset_analysis_ui()
        self._show_message("分析失败", msg, QMessageBox.Critical)
        self.status_bar.showMessage("分析失败")

    # ---- 模式切换 (优化 / 自然语言) ----
    def _on_mode_changed(self, index: int) -> None:
        """切换左右 stack 并更新工具栏按钮可用状态。"""
        self.left_stack.setCurrentIndex(index)
        self.right_stack.setCurrentIndex(index)
        is_optimize = index == MODE_OPTIMIZE
        # NL 模式下优化相关按钮不可用; 优化模式下 "✨ 生成 SQL" 由组件自身管理
        self._analyze_action.setEnabled(is_optimize)
        self._export_action.setEnabled(is_optimize)
        mode_name = "优化模式" if is_optimize else "自然语言模式"
        self.status_bar.showMessage(f"已切换到{mode_name}")

    def _start_nl_generate(self, text: str) -> None:
        """启动 NL→SQL 后台线程。"""
        if self.nl_worker is not None:
            return  # 正在生成, 忽略
        self.nl_input.set_readonly(True)
        self.status_bar.showMessage("生成 SQL 中 ...")

        self.nl_worker = NlWorker(text=text, config=self.config)
        self.nl_worker.nl_done.connect(self._on_nl_finished)
        self.nl_worker.error.connect(self._on_nl_error)
        # QThread 内置 finished 总会发射 -> 兜底, 保证 UI 一定回到可交互状态
        self.nl_worker.finished.connect(self._reset_nl_ui)
        self.nl_worker.nl_done.connect(self.nl_worker.deleteLater)
        self.nl_worker.error.connect(self.nl_worker.deleteLater)
        self.nl_worker.start()

    def _reset_nl_ui(self) -> None:
        """恢复 NL 输入 UI。幂等, 可被多个信号调用。"""
        self.nl_input.set_readonly(False)
        self.nl_worker = None

    def _on_nl_finished(self, result) -> None:
        """生成完成: 渲染 SQL 与结果, 提示 warnings / error。"""
        self.sql_display.set_sql(result.generated_sql)
        self.query_result.set_result(result.columns, result.rows)
        self._reset_nl_ui()

        if result.error:
            self._show_message("查询执行失败", result.error, QMessageBox.Critical)
        if result.warnings:
            self._show_message(
                "生成提示", "\n".join(result.warnings), QMessageBox.Warning)

        if result.error:
            self.status_bar.showMessage("生成完成, 但执行失败")
        elif result.warnings:
            # 有提示时状态栏要显眼，否则用户只看"完成"会以为生成的 SQL 就是他要的
            self.status_bar.showMessage(
                f"⚠ 有 {len(result.warnings)} 条提示 | 结果 {len(result.rows)} 行（请查看提示确认是否符合预期）")
        else:
            self.status_bar.showMessage(f"完成 | 结果 {len(result.rows)} 行")

    def _on_nl_error(self, msg: str) -> None:
        """生成出错: 非模态提示 + 恢复 UI。"""
        self._reset_nl_ui()
        self._show_message("生成失败", msg, QMessageBox.Critical)
        self.status_bar.showMessage("生成失败")

    def _on_optimize_requested(self, sql: str) -> None:
        """送入优化模式: SQL 填入输入框并切回优化模式。"""
        self.sql_input.editor.setPlainText(sql)
        self.mode_combo.setCurrentIndex(MODE_OPTIMIZE)
        self.status_bar.showMessage("已送入优化模式")

    # ---- 其他功能 ----
    def _on_clear(self) -> None:
        """清空输入框和报告区 (两种模式一起清)。"""
        self.sql_input.clear()
        self.report_view.clear()
        self.nl_input.clear()
        self.sql_display.clear()
        self.query_result.clear()
        self.last_report = None
        self.status_bar.showMessage("已清空")

    def _on_export(self) -> None:
        """导出报告: 弹文件对话框。"""
        if self.last_report is None:
            self._show_message("提示", "请先执行一次分析", QMessageBox.Information)
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "导出报告", "report",
            "Markdown (*.md);;HTML (*.html)",
        )
        if not path:
            return
        # 根据扩展名或过滤器决定格式
        if path.lower().endswith(".html") or "HTML" in selected_filter:
            fmt = "html"
        else:
            fmt = "markdown"
        try:
            self.exporter.save(self.last_report, path, fmt)
            self.status_bar.showMessage(f"已导出到: {path}")
        except Exception as e:
            self._show_message("导出失败", str(e), QMessageBox.Critical)

    def _on_history(self) -> None:
        """打开历史记录对话框。"""
        dialog = HistoryDialog(store=self.history, parent=self)
        dialog.sql_selected.connect(self._on_history_sql_selected)
        dialog.exec()

    def _on_history_sql_selected(self, sql: str) -> None:
        """历史对话框双击: 把 SQL 填入输入框。"""
        self.sql_input.editor.setPlainText(sql)
        self.status_bar.showMessage("已从历史填入 SQL")

    def _on_open_settings(self) -> None:
        """打开设置对话框。"""
        dialog = SettingsDialog(env_path=self.env_path, parent=self)
        if dialog.exec():
            # 重新加载配置
            self.config = load_config(env_path=self.env_path, mock=self.config.mock)
            self.status_bar.showMessage("配置已更新")
            self._check_db_connection()

    def _on_about(self) -> None:
        """关于对话框。"""
        QMessageBox.about(
            self, "关于 SQL Coach",
            "<h3>SQL Coach</h3>"
            "<p>AI 慢查询优化教练</p>"
            "<p>PySide6 GUI 桌面版</p>",
        )
