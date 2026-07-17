"""SQL Coach CLI 交互模式。

从原 main.py 提取，保持行为不变。在 PyCharm 或终端运行 `python main.py` 时调用。
"""
import sys

from rich.console import Console

from sql_coach.config import load_config
from sql_coach.coach import SQLCoach
from sql_coach.report.formatter import format_report

console = Console()


def analyze_one(coach: SQLCoach, sql: str) -> None:
    """分析单条 SQL 并打印报告。"""
    sql = sql.strip()
    if not sql:
        console.print("[yellow]SQL 为空, 已跳过[/yellow]")
        return
    if not sql.endswith(";"):
        sql += ";"

    console.print(f"\n[bold cyan]分析中: {sql}[/bold cyan]")
    console.print("\U0001f916 AI 分析中 ...")

    def on_chunk(chunk):
        console.print(chunk, end="", style="dim", highlight=False)

    try:
        report = coach.analyze(sql, on_chunk=on_chunk)
    except Exception as e:
        console.print(f"[red]分析失败: {e}[/red]")
        return

    console.print()  # 流式输出后换行

    # 打印完整报告
    console.print(format_report(
        report.sql_info, report.explain,
        report.analysis, report.benchmark
    ))

    # 摘要
    console.print("\n[bold]摘要[/bold]")
    console.print(f"  优化后 SQL: [green]{report.analysis.optimized_sql}[/green]")
    if report.analysis.index_ddls:
        for ddl in report.analysis.index_ddls:
            console.print(f"  索引建议: [cyan]{ddl}[/cyan]")
    if report.benchmark:
        speedup = report.benchmark.speedup
        if speedup == float("inf"):
            console.print("  提速: [bold green]无限大[/bold green]")
        else:
            console.print(f"  提速: [bold green]{speedup:.1f}x[/bold green]")


def run_cli() -> None:
    """交互式 CLI 入口: 循环读取 SQL 并分析, 输入 q 退出。"""
    console.print("[bold blue]╔════════════════════════════════════════════╗[/bold blue]")
    console.print("[bold blue]║   SQL Coach - AI 慢查询优化教练          ║[/bold blue]")
    console.print("[bold blue]╚════════════════════════════════════════════╝[/bold blue]")
    console.print("输入 SQL 进行分析, 输入 [magenta]q[/magenta] 退出\n")

    # 加载配置
    try:
        config = load_config()
    except Exception as e:
        console.print(f"[red]配置加载失败: {e}[/red]")
        console.print("提示: 先运行 [cyan]sql-coach config init[/cyan] 生成 .env 文件")
        sys.exit(1)

    # 连接数据库
    coach = SQLCoach(config)
    if not coach.connect():
        console.print("[yellow]数据库连接失败, 切换到模拟模式[/yellow]")
        config.mock = True
        coach = SQLCoach(config)
        coach.connect()

    try:
        # 主循环: 持续接收 SQL, 输入 q 退出
        while True:
            try:
                sql = console.input("\n[bold]> 输入 SQL (或 q 退出): [/bold]")
            except (EOFError, KeyboardInterrupt):
                console.print()
                break

            # 退出判断: q / quit / exit (大小写不敏感)
            if sql.strip().lower() in ("q", "quit", "exit"):
                break

            # 分析并输出
            analyze_one(coach, sql)
    finally:
        coach.close()
        console.print("\n[bold blue]已退出 SQL Coach, 再见[/bold blue]")
