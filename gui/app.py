# gui/app.py
"""GUI 模式启动入口。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from sql_coach.config import load_config

from gui.main_window import MainWindow
from gui.paths import get_env_path


def _install_error_log() -> None:
    """把未捕获异常（含 Qt 槽函数里的异常）追加写入 ~/.sql-coach/error.log。

    打包成窗口程序后没有 stderr：槽函数抛异常时界面上不会有任何提示，
    报告会停在半渲染状态，排查只能靠这份日志。
    """
    import traceback
    from datetime import datetime
    from pathlib import Path

    log_path = Path.home() / ".sql-coach" / "error.log"

    def hook(exc_type, exc, tb):
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n=== {datetime.now().isoformat(timespec='seconds')} ===\n")
                traceback.print_exception(exc_type, exc, tb, file=f)
        except Exception:
            pass
        try:
            sys.__excepthook__(exc_type, exc, tb)
        except Exception:
            pass

    sys.excepthook = hook


def _install_qt_message_log() -> None:
    """把 Qt 自己的日志（含 qFatal 致命信息）写入 ~/.sql-coach/qt.log。

    Qt 的 qFatal 会直接 fail-fast 终止进程（Windows 上异常码 0xC0000409），
    而窗口程序没有 stderr，崩溃时完全看不到提示。装上这个处理器后，
    致命信息会先落到文件里，便于事后定位。
    """
    from datetime import datetime
    from pathlib import Path

    from PySide6.QtCore import qInstallMessageHandler

    log_path = Path.home() / ".sql-coach" / "qt.log"

    def handler(mode, context, message):  # noqa: ANN001 - Qt 回调用签名
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat(timespec='seconds')} "
                        f"[{mode}] {message}\n")
        except Exception:
            pass

    qInstallMessageHandler(handler)


def run() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('SQL Coach')
    _install_error_log()
    _install_qt_message_log()

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

    from sql_coach.diagnostics.checks import run_all
    from gui.widgets.diagnostics_dialog import DiagnosticsDialog, SKIP_MARKER

    if not SKIP_MARKER.exists():
        results = run_all(config, env_path)
        if any(r.status != "ok" for r in results):
            dialog = DiagnosticsDialog(results, env_path=env_path, config=config)
            app._diagnostics_dialog = dialog  # 保持引用，防止被 GC
            dialog.show()                     # 非模态，不阻塞启动

    window = MainWindow(config=config, env_path=env_path)
    window.show()

    sys.exit(app.exec())
