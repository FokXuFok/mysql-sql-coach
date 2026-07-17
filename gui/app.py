# gui/app.py
"""GUI 模式启动入口。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from sql_coach.config import load_config

from gui.main_window import MainWindow
from gui.paths import get_env_path


def run() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('SQL Coach')

    env_path = get_env_path()

    try:
        config = load_config(env_path=env_path)
    except Exception:
        from sql_coach.models import Config, DBConfig
        config = Config(
            db=DBConfig(host='localhost', port=3306, user='root',
                        password='', database='test'),
            model='deepseek',
            deepseek_api_key='',
            openai_api_key='',
            ollama_url='http://localhost:11434',
            benchmark_runs=3,
            mock=True,
        )

    window = MainWindow(config=config, env_path=env_path)
    window.show()

    sys.exit(app.exec())
