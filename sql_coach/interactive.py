"""SQL Coach CLI 交互模式。

从原 main.py 提取，保持行为不变。在 PyCharm 或终端运行 `python main.py` 时调用。
"""
import sys

from rich.console import Console

from sql_coach.config import load_config
from sql_coach.coach import SQLCoach
from sql_coach.report.formatter import format_report

console = Console()

# 交互模式下以该前缀开头视为自然语言转 SQL 模式
NL_PREFIX = "/nl"


def analyze_one(coach: SQLCoach, sql: str) -> None:
    """分析单条 SQL 并打印报告。"""
    sql = sql.strip()
    if not sql:
        console.print("[yellow]SQL 为空, 已跳过[/yellow]")
        return
    if not sql.endswith(";"):
        sql += ";"

    console.print(f"\n[bold cyan]分析中: {sql}[/bold cyan]")
    console.print("\U0001f50e 正在分析 SQL ...")

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
        report.analysis, report.benchmark,
        engine_used=report.engine_used,
        index_impact=report.index_impact,
    ))

    level = report.complexity.level if report.complexity else "-"
    console.print(f"[dim]优化引擎: {report.engine_used} | 复杂度: {level}[/dim]")

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


def nl_one(coach: SQLCoach, text: str) -> None:
    """自然语言转 SQL 并打印生成的 SQL 与结果摘要。"""
    text = text.strip()
    if not text:
        console.print("[yellow]自然语言描述为空, 已跳过[/yellow]")
        return

    console.print(f"\n[bold cyan]自然语言: {text}[/bold cyan]")
    try:
        result = coach.generate_sql(text, execute=True, verify=True)
    except Exception as e:  # noqa: BLE001 - 生成失败不中断交互
        console.print(f"[red]生成失败: {e}[/red]")
        return

    nq = result.nl_query
    tables = ", ".join(nq.tables) or "(未识别)"
    console.print(f"[bold]意图[/bold]: {nq.intent} | [bold]识别表[/bold]: {tables}")
    console.print(f"生成的 SQL: [green]{result.generated_sql}[/green]")

    for warning in result.warnings:
        console.print(f"[yellow]\u26a0 {warning}[/yellow]")
    if result.error:
        console.print(f"[red]执行错误: {result.error}[/red]")
    if result.executed:
        console.print(f"[dim]返回 {len(result.rows)} 行, 列: {', '.join(result.columns)}[/dim]")


def run_cli() -> None:
    """交互式 CLI 入口: 循环读取 SQL 并分析, 输入 q 退出。"""
    console.print("[bold blue]╔════════════════════════════════════════════╗[/bold blue]")
    console.print("[bold blue]║   SQL Coach - 慢查询优化教练             ║[/bold blue]")
    console.print("[bold blue]╚════════════════════════════════════════════╝[/bold blue]")
    console.print("输入 SQL 进行分析, 输入 [magenta]q[/magenta] 退出")
    console.print("输入 [cyan]/nl 自然语言描述[/cyan] 可自然语言转 SQL\n")

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

            # 自然语言转 SQL 模式: 以 /nl 开头
            stripped = sql.strip()
            if stripped == NL_PREFIX or stripped.startswith(NL_PREFIX + " "):
                nl_one(coach, stripped[len(NL_PREFIX):])
                continue

            # 分析并输出
            analyze_one(coach, sql)
    finally:
        coach.close()
        console.print("\n[bold blue]已退出 SQL Coach, 再见[/bold blue]")
