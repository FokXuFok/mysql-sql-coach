# sql_coach/cli.py
"""CLI entry point using Click."""
import os
import sys
from pathlib import Path

import click
import pyperclip
from rich.console import Console
from rich.panel import Panel

from . import __version__
from .config import load_config
from .coach import SQLCoach
from .report.formatter import format_report

console = Console()

ENV_TEMPLATE = """# MySQL 连接
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=test

# AI 模型: deepseek / openai / ollama
AI_MODEL=deepseek

# DeepSeek
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com

# OpenAI
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1

# Ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b

# 通用
BENCHMARK_RUNS=3
LOG_LEVEL=INFO
"""


@click.group()
@click.version_option(__version__)
def main():
    """SQL Coach — AI-powered MySQL slow query optimization coach."""
    pass


@main.command()
@click.argument("sql", required=False)
@click.option("--file", "-f", help="从文件读取 SQL")
@click.option("--model", "-m", default=None,
              type=click.Choice(["deepseek", "openai", "ollama"]),
              help="指定 AI 模型")
@click.option("--mock", is_flag=True, help="使用模拟模式（无需数据库）")
def analyze(sql, file, model, mock):
    """分析并优化 SQL 语句。"""
    # Get SQL from argument or file
    if file:
        with open(file, "r", encoding="utf-8") as f:
            sql = f.read().strip()
    if not sql:
        console.print("[red]错误: 请提供 SQL 语句或使用 -f 指定文件[/red]")
        sys.exit(1)

    # Load config
    config = load_config(mock=mock)
    if model:
        config.model = model

    # Connect
    console.print("🔍 正在连接 MySQL...", end=" ")
    coach = SQLCoach(config)
    if not coach.connect():
        console.print("[yellow]✗ 数据库连接失败，切换到模拟模式[/yellow]")
        config.mock = True
        coach = SQLCoach(config)
    else:
        console.print("[green]✓[/green]")

    # Analyze
    console.print("📊 执行 EXPLAIN...", end=" ")
    console.print("[green]✓[/green]")
    console.print("🤖 AI 分析中...", end=" ")
    console.print("[green]✓[/green]")

    try:
        report = coach.analyze(sql)
    except Exception as e:
        console.print(f"\n[red]分析失败: {e}[/red]")
        sys.exit(1)
    finally:
        coach.close()

    # Print report
    output = format_report(report.sql_info, report.explain,
                           report.analysis, report.benchmark)
    console.print(output)

    # Interactive choice
    _interactive_choice(sql, report.analysis.optimized_sql)


def _interactive_choice(original_sql: str, optimized_sql: str) -> None:
    """Ask user which SQL to use and copy to clipboard."""
    if not optimized_sql or optimized_sql == original_sql:
        console.print("\n[dim]无优化建议，使用原始 SQL[/dim]")
        return

    console.print("\n[bold]💡 你想使用哪个 SQL？[/bold]")
    console.print("  [1] 原始 SQL")
    console.print("  [2] 优化后 SQL (推荐)")
    console.print("  [q] 退出")

    while True:
        choice = click.prompt("> ", default="2", show_default=False)
        if choice == "1":
            pyperclip.copy(original_sql)
            console.print("[green]✅ 原始 SQL 已复制到剪贴板！[/green]")
            break
        elif choice == "2":
            pyperclip.copy(optimized_sql)
            console.print("[green]✅ 优化后 SQL 已复制到剪贴板！[/green]")
            break
        elif choice.lower() == "q":
            break
        else:
            console.print("[red]无效选择，请输入 1、2 或 q[/red]")


@main.group()
def config():
    """配置管理。"""
    pass


@config.command("init")
def config_init():
    """初始化 .env 配置文件。"""
    env_path = Path(".env")
    if env_path.exists():
        if not click.confirm(".env 已存在，是否覆盖？"):
            return

    env_path.write_text(ENV_TEMPLATE, encoding="utf-8")
    console.print(f"[green]✓ 配置文件已创建: {env_path.absolute()}[/green]")
    console.print("[yellow]请编辑 .env 文件，填入你的 API Key 和数据库连接信息[/yellow]")


@config.command("test")
def config_test():
    """测试数据库和 AI 连通性。"""
    config = load_config()

    # Test DB
    console.print("🔍 测试数据库连接...", end=" ")
    coach = SQLCoach(config)
    if coach.connect():
        console.print("[green]✓[/green]")
    else:
        console.print("[red]✗ 数据库连接失败[/red]")
    coach.close()

    # Test AI
    console.print("🤖 测试 AI 连接...", end=" ")
    console.print("[yellow]（需要实际调用才能确认）[/yellow]")


if __name__ == "__main__":
    main()
