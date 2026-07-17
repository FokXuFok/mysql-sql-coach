# gui/main_window.py
"""主窗口, 左右分栏组装所有组件。"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QMainWindow, QMessageBox, QSplitter,
    QStatusBar, QToolBar, QWidget,
)

from sql_coach.coach import Report
from sql_coach.config import load_config
from sql_coach.models import Config

from gui.storage.history_store import HistoryStore
from gui.storage.exporter import Exporter
from gui.widgets.history_dialog import HistoryDialog
from gui.widgets.report_view import ReportView
from gui.widgets.settings_dialog import SettingsDialog
from gui.widgets.sql_input import SqlInputWidget
from gui.workers.analyze_worker import AnalyzeWorker, stage_label


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
        self.last_report: Optional[Report] = None
        self._analyze_start_time: float = 0.0

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
        """左右分栏 40% / 60%。"""
        splitter = QSplitter(Qt.Horizontal)

        self.sql_input = SqlInputWidget()
        self.report_view = ReportView()

        splitter.addWidget(self.sql_input)
        splitter.addWidget(self.report_view)
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
        """工具栏: 5 个按钮。"""
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        analyze_btn = toolbar.addAction("🔍 分析")
        analyze_btn.triggered.connect(self._on_analyze)
        self._analyze_action = analyze_btn

        clear_btn = toolbar.addAction("🗑 清空")
        clear_btn.triggered.connect(self._on_clear)

        export_btn = toolbar.addAction("💾 导出报告")
        export_btn.triggered.connect(self._on_export)

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
                QMessageBox.warning(self, "数据库连接失败", "已切换到模拟模式")
                self.status_bar.showMessage("DB: 模拟模式")
        except Exception as e:
            self.config.mock = True
            QMessageBox.warning(self, "数据库连接失败", f"已切换到模拟模式\n错误: {e}")
            self.status_bar.showMessage("DB: 模拟模式")

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
        self.worker.finished.connect(self._on_analyze_finished)
        self.worker.error.connect(self._on_analyze_error)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.error.connect(self.worker.deleteLater)
        self.worker.start()

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

        self.sql_input.set_readonly(False)
        self._analyze_action.setEnabled(True)
        self.worker = None
        self.status_bar.showMessage(
            f"完成 | AI: {elapsed/1000:.1f}s | 模型: {self.config.model}"
        )

    def _on_analyze_error(self, msg: str) -> None:
        """分析出错: 弹错误框 + 恢复 UI。"""
        self.sql_input.set_readonly(False)
        self._analyze_action.setEnabled(True)
        self.worker = None
        QMessageBox.critical(self, "分析失败", msg)
        self.status_bar.showMessage("分析失败")

    # ---- 其他功能 ----
    def _on_clear(self) -> None:
        """清空输入框和报告区。"""
        self.sql_input.clear()
        self.report_view.clear()
        self.last_report = None
        self.status_bar.showMessage("已清空")

    def _on_export(self) -> None:
        """导出报告: 弹文件对话框。"""
        if self.last_report is None:
            QMessageBox.information(self, "提示", "请先执行一次分析")
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
            QMessageBox.critical(self, "导出失败", str(e))

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
