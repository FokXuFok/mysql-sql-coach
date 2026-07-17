"""SQL Coach 入口: 打包后走 GUI, 开发模式走 CLI 交互."""
import sys


def main() -> None:
    # PyInstaller 打包后 sys.frozen=True, 直接启动 GUI
    if getattr(sys, 'frozen', False) or '--gui' in sys.argv:
        from gui.app import run
        run()
    else:
        # PyCharm / 终端 -> CLI 交互模式
        from sql_coach.interactive import run_cli
        run_cli()


if __name__ == '__main__':
    main()
