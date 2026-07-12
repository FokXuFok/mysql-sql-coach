# sql_coach/report/formatter.py
"""Report formatter using Rich."""
from io import StringIO
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from ..models import (
    SQLInfo, ExplainResult, AnalysisResult, BenchmarkResult, Problem
)

SEVERITY_ICONS = {
    "critical": "🔴",
    "warning": "🟡",
    "info": "🔵",
}


def format_problems(problems: list[Problem]) -> str:
    """Format problems list as a string."""
    if not problems:
        return "未发现问题"

    lines = []
    for p in problems:
        icon = SEVERITY_ICONS.get(p.severity, "•")
        lines.append(f"  {icon} ({p.severity}) {p.table}: {p.description}")
        if p.suggestion:
            lines.append(f"      → {p.suggestion}")
    return "\n".join(lines)


def _format_explain_table(explain: ExplainResult) -> Table:
    """Format EXPLAIN result as a Rich table."""
    table = Table(title="执行计划", show_lines=True)
    table.add_column("id", style="cyan")
    table.add_column("table", style="magenta")
    table.add_column("type", style="yellow")
    table.add_column("key", style="green")
    table.add_column("rows", style="red")
    table.add_column("Extra")

    for row in explain.rows:
        type_style = "red" if row.type == "ALL" else "green"
        table.add_row(
            str(row.id),
            row.table,
            Text(row.type, style=type_style),
            row.key or "NULL",
            f"{row.rows:,}",
            row.extra or "",
        )

    return table


def format_report(
    sql_info: SQLInfo,
    explain: Optional[ExplainResult],
    analysis: AnalysisResult,
    benchmark: Optional[BenchmarkResult],
) -> str:
    """Format full report and return as string."""
    buffer = StringIO()
    buf_console = Console(file=buffer, width=100)

    # Header
    buf_console.print(Panel("📋 SQL 优化分析报告", style="bold blue"))

    # Original SQL
    buf_console.print("\n[bold]📝 原始 SQL:[/bold]")
    buf_console.print(f"  [dim]{sql_info.raw_sql}[/dim]")

    # EXPLAIN table
    if explain and explain.rows:
        buf_console.print("\n[bold]📊 执行计划:[/bold]")
        buf_console.print(_format_explain_table(explain))

    # Problems
    if analysis.problems:
        buf_console.print(f"\n[bold]⚠️ 发现 {len(analysis.problems)} 个问题:[/bold]")
        buf_console.print(format_problems(analysis.problems))

    # Optimized SQL
    if analysis.optimized_sql and analysis.optimized_sql != sql_info.raw_sql:
        buf_console.print("\n[bold green]✅ 优化后 SQL:[/bold green]")
        buf_console.print(f"  [green]{analysis.optimized_sql}[/green]")

    # Index DDLs
    if analysis.index_ddls:
        buf_console.print("\n[bold]📌 索引建议:[/bold]")
        for ddl in analysis.index_ddls:
            buf_console.print(f"  [cyan]{ddl}[/cyan]")

    # AI explanation
    if analysis.explanation:
        buf_console.print("\n[bold]🤖 AI 解释:[/bold]")
        buf_console.print(f"  {analysis.explanation}")

    # Benchmark
    if benchmark:
        buf_console.print("\n[bold]📊 性能对比:[/bold]")
        buf_console.print(f"  原始 SQL:   {benchmark.original_time:.3f}s  "
                          f"(扫描 {benchmark.original_rows:,} 行)")
        buf_console.print(f"  优化 SQL:   {benchmark.optimized_time:.3f}s  "
                          f"(扫描 {benchmark.optimized_rows:,} 行)")
        if benchmark.speedup == float("inf"):
            buf_console.print("  [bold green]提速: 无限大 🚀[/bold green]")
        else:
            buf_console.print(f"  [bold green]提速: {benchmark.speedup:.1f}x 🚀[/bold green]")

    return buffer.getvalue()