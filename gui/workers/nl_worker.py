# gui/workers/nl_worker.py
"""自然语言转 SQL 后台线程, 防止 GUI 卡死。

每次生成创建新的 SQLCoach 实例, 生成完 close()。
不在主窗口持有长期连接, 避免多线程冲突。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QThread, Signal

from sql_coach.coach import SQLCoach
from sql_coach.models import Config


class NlWorker(QThread):
    """NL→SQL 后台线程。

    Signals:
        nl_done(object): 生成完成, 携带 NLQueryResult
        error(str): 异常, 携带错误信息

    注意: 自定义完成信号**不能**叫 ``finished`` —— 那会覆盖 ``QThread`` 内置的
    ``finished`` 信号, 导致线程结束时的兜底逻辑收不到通知。
    这里命名为 ``nl_done``（参照 ``analyze_worker.py`` 的 ``analysis_done``）。
    """

    nl_done = Signal(object)
    error = Signal(str)

    def __init__(
        self,
        text: str,
        config: Config,
        parent: Optional["QThread"] = None,
    ) -> None:
        super().__init__(parent)
        self.text = text
        self.config = config

    def run(self) -> None:
        """线程入口: 创建 SQLCoach, 调 generate_sql, close。"""
        coach = None
        try:
            coach = SQLCoach(self.config, use_cache=False)
            coach.connect()
            result = coach.generate_sql(self.text, execute=True, verify=True)
            self.nl_done.emit(result)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if coach is not None:
                coach.close()
