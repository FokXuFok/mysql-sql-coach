"""SQL Coach - 智能入口。

- PyInstaller 打包环境 (sys.frozen) 或显式 --gui 参数 -> 启动 GUI
- PyCharm / 终端 (python main.py) -> CLI 交互模式
"""
import sys


def main() -> None:
    """根据运行环境分发到 GUI 或 CLI。"""
    if getattr(sys, "frozen", False) or "--gui" in sys.argv:
        # PyInstaller 打包环境 或 显式指定 --gui
        from gui.app import run
        run()
    else:
        # PyCharm / 终端 -> CLI 交互模式
        from sql_coach.interactive import run_cli
        run_cli()


if __name__ == "__main__":
    main()
