# gui/app.py
"""GUI 模式启动入口。

由 main.py 在 sys.frozen 或 --gui 时调用。
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from sql_coach.config import load_config

from gui.main_window import MainWindow


def run() -> None:
    """启动 GUI: 创建 QApplication + MainWindow + exec。"""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("SQL Coach")

    # 加载配置 (失败时降级 mock 模式)
    try:
        config = load_config()
    except Exception:
        from sql_coach.models import Config, DBConfig
        config = Config(
            db=DBConfig(host="localhost", port=3306, user="root",
                        password="", database="test"),
            model="deepseek",
            deepseek_api_key="",
            openai_api_key="",
            ollama_url="http://localhost:11434",
            benchmark_runs=3,
            mock=True,
        )

    window = MainWindow(config=config)
    window.show()
    sys.exit(app.exec())
