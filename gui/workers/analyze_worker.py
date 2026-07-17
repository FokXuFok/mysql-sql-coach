# gui/workers/analyze_worker.py
"""后台分析线程, 防止 GUI 卡死。

每次分析创建新的 SQLCoach 实例, 分析完 close()。
不在主窗口持有长期连接, 避免多线程冲突。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QThread, Signal

from sql_coach.coach import SQLCoach, Report
from sql_coach.models import Config

# 阶段 -> 中文标签
STAGE_LABELS = {
    "parse": "正在解析 SQL",
    "explain": "正在执行 EXPLAIN",
    "ai": "AI 分析中",
    "benchmark": "性能对比中",
}


def stage_label(stage: str) -> str:
    """返回阶段的中文描述。"""
    return STAGE_LABELS.get(stage, stage)


class AnalyzeWorker(QThread):
    """后台分析线程。

    Signals:
        finished(Report): 分析完成, 携带 Report
        error(str): 异常, 携带错误信息
        stage_changed(str): 阶段变化, "parse"/"explain"/"ai"/"benchmark"
    """

    finished = Signal(Report)
    error = Signal(str)
    stage_changed = Signal(str)

    def __init__(
        self,
        sql: str,
        config: Config,
        use_cache: bool = True,
        parent: Optional["QThread"] = None,
    ) -> None:
        super().__init__(parent)
        self.sql = sql
        self.config = config
        self.use_cache = use_cache

    def run(self) -> None:
        """线程入口: 创建 SQLCoach, 调 analyze, close。"""
        try:
            coach = SQLCoach(self.config, use_cache=self.use_cache)
            coach.connect()

            def on_stage(stage: str, step: int, total: int, status: str) -> None:
                # 仅在阶段开始时发射信号, 避免重复
                if status == "start":
                    self.stage_changed.emit(stage)

            report = coach.analyze(self.sql, on_stage=on_stage)
            coach.close()
            self.finished.emit(report)
        except Exception as e:
            self.error.emit(str(e))
