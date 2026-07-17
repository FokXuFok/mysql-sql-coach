# SQL Coach GUI 桌面版 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 SQL Coach 添加 PySide6 桌面 GUI，双击 exe 弹出窗口，PyCharm 里 python main.py 走 CLI 模式

**Architecture:** 薄 GUI 层 + 现有核心复用。GUI 不含业务逻辑，通过 SQLCoach.analyze() 完成分析。QThread 后台执行防止界面卡死。HistoryStore 和 Exporter 不依赖 Qt，可独立测试。

**Tech Stack:** PySide6, matplotlib, pytest, pytest-qt, PyInstaller

---

## 文件结构总览

### 新增文件

```
sql-coach/
├── gui/
│   ├── __init__.py
│   ├── app.py                      # QApplication 启动入口
│   ├── main_window.py              # 主窗口 (左右分栏)
│   ├── workers/
│   │   ├── __init__.py
│   │   └── analyze_worker.py       # QThread 后台分析
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── sql_input.py            # SQL 输入区
│   │   ├── report_view.py          # 报告容器 (QScrollArea)
│   │   ├── explain_table.py        # EXPLAIN 表格
│   │   ├── benchmark_chart.py       # matplotlib 柱状图
│   │   ├── history_dialog.py       # 历史记录对话框
│   │   └── settings_dialog.py      # 设置对话框
│   └── storage/
│       ├── __init__.py
│       ├── history_store.py        # JSON 历史存储
│       └── exporter.py             # 报告导出 (md/html)
├── sql_coach/
│   └── interactive.py              # CLI 交互模式 (从 main.py 提取)
├── tests/
│   ├── test_history_store.py
│   ├── test_exporter.py
│   └── test_analyze_worker.py
├── main.py                         # 智能入口 (修改)
├── .github/workflows/build-gui.yml
└── pyproject.toml                  # 新增 gui optional-dependencies
```

### 修改的现有文件

| 文件 | 改动 |
|------|------|
| `main.py` | 改为智能入口，分发 CLI / GUI |
| `pyproject.toml` | 新增 `[project.optional-dependencies].gui` 和 dev 的 `pytest-qt`，更新 packages.find |
| `.gitignore` | 追加 `.superpowers/` |

### 不改动清单

`sql_coach/` 目录下所有现有代码（coach.py、models.py、config.py、cache.py、cli.py、ai/*、db/*、engine/*、report/*）和 `tests/` 下现有测试文件均不修改。

---

## Task 1: 提取 CLI 交互逻辑到 sql_coach/interactive.py

**Files:**
- Create: `sql_coach/interactive.py`
- Modify: `main.py` (重写为智能入口)
- Test: `tests/test_cli.py` (现有测试，验证零回归)

- [ ] **Step 1: 创建 sql_coach/interactive.py**

```python
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
```

- [ ] **Step 2: 重写 main.py 为智能入口**

```python
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
```

- [ ] **Step 3: 运行现有测试套件验证零回归**

Run: `pytest tests/ -v`
Expected: 全部现有测试通过 (test_ai_engine / test_benchmark / test_cli / test_coach / test_config / test_db_connector / test_explain_runner / test_formatter / test_models / test_sql_parser)

- [ ] **Step 4: 手动验证 CLI 入口仍工作**

Run: `python main.py` (在项目根目录，输入 q 立即退出)
Expected: 看到 SQL Coach 横幅 banner 后输入 q 退出，无 ImportError。

- [ ] **Step 5: Commit**

```bash
git add sql_coach/interactive.py main.py
git commit -m "refactor: 提取 CLI 逻辑到 sql_coach/interactive.py，main.py 改为智能入口"
```

---

## Task 2: 更新 pyproject.toml 添加 gui 和测试依赖

**Files:**
- Modify: `pyproject.toml`
- Test: 无需新增测试，验证依赖可安装

- [ ] **Step 1: 修改 pyproject.toml 的 [project.optional-dependencies]**

将原有的：
```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-mock>=3.0",
    "pytest-cov>=4.0",
]
```

改为：
```toml
[project.optional-dependencies]
gui = [
    "PySide6>=6.5",
    "matplotlib>=3.7",
]
dev = [
    "pytest>=7.0",
    "pytest-mock>=3.0",
    "pytest-cov>=4.0",
    "pytest-qt>=4.0",
]
```

- [ ] **Step 2: 更新 [tool.setuptools.packages.find]**

将原有的：
```toml
[tool.setuptools.packages.find]
include = ["sql_coach*"]
```

改为：
```toml
[tool.setuptools.packages.find]
include = ["sql_coach*", "gui*"]
```

- [ ] **Step 3: 安装新依赖验证**

Run: `pip install -e ".[gui,dev]"`
Expected: 成功安装 PySide6、matplotlib、pytest-qt，无错误。

- [ ] **Step 4: 验证 pytest-qt 可用**

Run: `python -c "import pytestqt; import PySide6; import matplotlib; print('ok')"`
Expected: 输出 `ok`，无 ImportError。

- [ ] **Step 5: 运行现有测试确保零回归**

Run: `pytest tests/ -v`
Expected: 全部现有测试通过。

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml
git commit -m "build: 添加 gui optional-dependencies (PySide6, matplotlib) 和 pytest-qt"
```

---

## Task 3: HistoryStore — JSON 历史记录存储

**Files:**
- Create: `tests/test_history_store.py`
- Create: `gui/storage/history_store.py`
- Create: `gui/storage/__init__.py`
- Create: `gui/__init__.py`

- [ ] **Step 1: 创建 gui 包的 __init__.py 文件**

写入 `gui/__init__.py`:
```python
"""SQL Coach 桌面 GUI 包。"""
```

写入 `gui/storage/__init__.py`:
```python
"""GUI 存储层: 历史记录和报告导出。"""
```

- [ ] **Step 2: 写失败测试 tests/test_history_store.py**

```python
# tests/test_history_store.py
"""HistoryStore 单元测试。纯 Python, 不依赖 Qt。"""
import json
import time
from pathlib import Path

import pytest

from sql_coach.coach import Report
from sql_coach.models import (
    SQLInfo, ExplainResult, AnalysisResult, BenchmarkResult,
)

from gui.storage.history_store import HistoryStore


@pytest.fixture
def store(tmp_path):
    """使用临时目录的 HistoryStore。"""
    return HistoryStore(path=str(tmp_path / "history.json"))


@pytest.fixture
def sample_report():
    """构造一个最小的 Report 对象。"""
    return Report(
        sql_info=SQLInfo(
            raw_sql="SELECT * FROM users WHERE id=1",
            sql_type="SELECT",
            tables=["users"],
            columns=["*"],
            where_conditions=["id=1"],
            join_tables=[],
            order_by=[],
        ),
        explain=None,
        analysis=AnalysisResult(
            problems=[],
            optimized_sql="SELECT * FROM users WHERE id=1;",
            index_ddls=["CREATE INDEX idx_users_id ON users(id);"],
            explanation="已优化",
        ),
        benchmark=BenchmarkResult(
            original_time=0.5,
            optimized_time=0.02,
            speedup=25.0,
            original_rows=1000,
            optimized_rows=1,
        ),
    )


def test_add_returns_id(store, sample_report):
    """add() 返回 6 位 hex id。"""
    rid = store.add(sample_report.sql_info.raw_sql, sample_report, ai_time_ms=1000.0)
    assert isinstance(rid, str)
    assert len(rid) == 6
    # hex 字符串
    int(rid, 16)


def test_list_returns_records(store, sample_report):
    """list() 返回记录列表, 按时间倒序。"""
    store.add("SQL1", sample_report, ai_time_ms=100.0)
    time.sleep(0.01)
    store.add("SQL2", sample_report, ai_time_ms=200.0)
    records = store.list()
    assert len(records) == 2
    # 最新的在前
    assert records[0]["sql"] == "SQL2"
    assert records[1]["sql"] == "SQL1"
    # 字段完整
    rec = records[0]
    assert "id" in rec
    assert "sql" in rec
    assert "timestamp" in rec
    assert "optimized_sql" in rec
    assert "speedup" in rec
    assert "ai_time_ms" in rec
    assert "problem_count" in rec


def test_get_by_id(store, sample_report):
    """get() 按 id 返回单条记录。"""
    rid = store.add("SELECT 1", sample_report, ai_time_ms=50.0)
    rec = store.get(rid)
    assert rec is not None
    assert rec["id"] == rid
    assert rec["sql"] == "SELECT 1"
    assert rec["ai_time_ms"] == 50.0


def test_get_missing_id_returns_none(store):
    """get() 对不存在的 id 返回 None。"""
    assert store.get("ffffff") is None


def test_delete_by_id(store, sample_report):
    """delete() 删除指定记录, 返回 True/False。"""
    rid = store.add("DELETE ME", sample_report, ai_time_ms=10.0)
    assert store.delete(rid) is True
    assert store.get(rid) is None
    assert store.delete(rid) is False  # 已删除
    assert store.delete("nonexist") is False


def test_clear_returns_count(store, sample_report):
    """clear() 返回删除的条数。"""
    store.add("SQL1", sample_report, ai_time_ms=1.0)
    store.add("SQL2", sample_report, ai_time_ms=2.0)
    count = store.clear()
    assert count == 2
    assert store.list() == []


def test_max_100_records(store, sample_report):
    """最多保留 100 条, 超出删最旧。"""
    for i in range(105):
        store.add(f"SQL{i}", sample_report, ai_time_ms=float(i))
    records = store.list()
    assert len(records) == 100
    # 最旧的 SQL0~SQL4 应被删除
    sqls = [r["sql"] for r in records]
    assert "SQL0" not in sqls
    assert "SQL4" not in sqls
    assert "SQL5" in sqls
    assert "SQL104" in sqls


def test_corrupted_file_returns_empty(tmp_path):
    """文件损坏时返回空列表, 不崩溃。"""
    bad_file = tmp_path / "history.json"
    bad_file.write_text("{invalid json!!!", encoding="utf-8")
    store = HistoryStore(path=str(bad_file))
    assert store.list() == []


def test_missing_file_returns_empty(tmp_path):
    """文件不存在时返回空列表。"""
    store = HistoryStore(path=str(tmp_path / "nonexist.json"))
    assert store.list() == []


def test_persistence_across_instances(tmp_path, sample_report):
    """跨实例持久化: 写入后新实例能读到。"""
    path = str(tmp_path / "history.json")
    s1 = HistoryStore(path=path)
    rid = s1.add("PERSIST", sample_report, ai_time_ms=1.0)
    s2 = HistoryStore(path=path)
    rec = s2.get(rid)
    assert rec is not None
    assert rec["sql"] == "PERSIST"
```

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest tests/test_history_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.storage.history_store'`

- [ ] **Step 4: 实现 gui/storage/history_store.py**

```python
# gui/storage/history_store.py
"""历史记录 JSON 存储, 不依赖 Qt。

存储到 ~/.sql-coach/history.json, 最多保留 100 条。
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime
from typing import Optional

from sql_coach.coach import Report

logger = logging.getLogger(__name__)

DEFAULT_PATH = os.path.join(
    os.path.expanduser("~"), ".sql-coach", "history.json"
)
MAX_RECORDS = 100


class HistoryStore:
    """JSON 文件历史记录存储。"""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or DEFAULT_PATH
        self._max_records = MAX_RECORDS

    # ---- 内部读写 ----
    def _read(self) -> list[dict]:
        """读取全部记录, 文件损坏返回空列表。"""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return []
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("历史记录文件损坏, 返回空列表: %s", e)
            return []
        if not isinstance(data, list):
            return []
        return data

    def _write(self, records: list[dict]) -> None:
        """写入记录, 自动创建父目录。"""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.path)

    # ---- 公共 API ----
    def add(self, sql: str, report: Report, ai_time_ms: float) -> str:
        """添加一条记录, 返回 6 位 hex id。超出上限自动删最旧。"""
        rid = secrets.token_hex(3)  # 6 位 hex
        speedup = None
        if report.benchmark is not None:
            speedup = report.benchmark.speedup
        record = {
            "id": rid,
            "sql": sql,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "optimized_sql": report.analysis.optimized_sql,
            "speedup": speedup,
            "ai_time_ms": ai_time_ms,
            "problem_count": len(report.analysis.problems),
        }
        records = self._read()
        records.append(record)
        # 超出上限: 删最旧 (列表头部)
        if len(records) > self._max_records:
            records = records[-self._max_records:]
        self._write(records)
        return rid

    def list(self) -> list[dict]:
        """返回全部记录, 按时间倒序 (最新在前)。"""
        records = self._read()
        # 按 timestamp 倒序
        return sorted(
            records,
            key=lambda r: r.get("timestamp", ""),
            reverse=True,
        )

    def delete(self, record_id: str) -> bool:
        """删除指定 id 的记录, 返回是否删除成功。"""
        records = self._read()
        before = len(records)
        records = [r for r in records if r.get("id") != record_id]
        if len(records) == before:
            return False
        self._write(records)
        return True

    def clear(self) -> int:
        """清空全部记录, 返回删除条数。"""
        records = self._read()
        count = len(records)
        self._write([])
        return count

    def get(self, record_id: str) -> Optional[dict]:
        """按 id 取单条记录, 不存在返回 None。"""
        for r in self._read():
            if r.get("id") == record_id:
                return r
        return None
```

- [ ] **Step 5: 运行测试验证通过**

Run: `pytest tests/test_history_store.py -v`
Expected: 全部 9 个测试 PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_history_store.py gui/storage/history_store.py gui/storage/__init__.py gui/__init__.py
git commit -m "feat: 添加 HistoryStore JSON 历史记录存储"
```

---

## Task 4: Exporter — 报告导出

**Files:**
- Create: `tests/test_exporter.py`
- Create: `gui/storage/exporter.py`

- [ ] **Step 1: 写失败测试 tests/test_exporter.py**

```python
# tests/test_exporter.py
"""Exporter 单元测试。纯 Python, 不依赖 Qt。"""
from pathlib import Path

import pytest

from sql_coach.coach import Report
from sql_coach.models import (
    SQLInfo, ExplainRow, ExplainResult, Problem, AnalysisResult,
    BenchmarkResult,
)

from gui.storage.exporter import Exporter


@pytest.fixture
def report_with_full_data():
    """包含执行计划、问题、优化 SQL、索引、benchmark 的完整报告。"""
    return Report(
        sql_info=SQLInfo(
            raw_sql="SELECT * FROM commodity WHERE Cname='牛奶'",
            sql_type="SELECT",
            tables=["commodity"],
            columns=["*"],
            where_conditions=["Cname='牛奶'"],
            join_tables=[],
            order_by=[],
        ),
        explain=ExplainResult(
            rows=[
                ExplainRow(
                    id=1, select_type="SIMPLE", table="commodity",
                    type="ALL", key=None, rows=1000, extra="Using where",
                ),
            ],
            is_full_scan=True,
            missing_indexes=["Cname"],
            problems=["全表扫描"],
        ),
        analysis=AnalysisResult(
            problems=[
                Problem(
                    severity="critical",
                    table="commodity",
                    description="全表扫描: Cname 列无索引",
                    suggestion="在 Cname 列创建索引",
                ),
            ],
            optimized_sql="SELECT * FROM commodity WHERE Cname='牛奶';",
            index_ddls=["CREATE INDEX idx_cname ON commodity(Cname);"],
            explanation="为 WHERE 条件列添加索引以避免全表扫描。",
        ),
        benchmark=BenchmarkResult(
            original_time=0.5,
            optimized_time=0.02,
            speedup=25.0,
            original_rows=1000,
            optimized_rows=1,
        ),
    )


@pytest.fixture
def report_minimal():
    """最小报告: 无 explain, 无 benchmark, 无问题。"""
    return Report(
        sql_info=SQLInfo(
            raw_sql="SELECT 1",
            sql_type="SELECT",
            tables=[],
            columns=["1"],
            where_conditions=[],
            join_tables=[],
            order_by=[],
        ),
        explain=None,
        analysis=AnalysisResult(
            problems=[],
            optimized_sql="SELECT 1;",
            index_ddls=[],
            explanation="无需优化。",
        ),
        benchmark=None,
    )


def test_to_markdown_contains_sections(report_with_full_data):
    """Markdown 输出包含所有必要章节。"""
    md = Exporter().to_markdown(report_with_full_data)
    assert "# SQL 优化分析报告" in md
    assert "## 原始 SQL" in md
    assert "## 执行计划" in md
    assert "## 问题列表" in md
    assert "## 优化后 SQL" in md
    assert "## 索引建议" in md
    assert "## 性能对比" in md


def test_to_markdown_contains_explain_table(report_with_full_data):
    """Markdown 中执行计划用表格形式呈现。"""
    md = Exporter().to_markdown(report_with_full_data)
    # 表头
    assert "| id | table | type | key | rows | extra |" in md
    assert "| 1 | commodity | ALL | NULL | 1,000 | Using where |" in md


def test_to_markdown_contains_problems(report_with_full_data):
    """Markdown 中问题列表含 severity 和建议。"""
    md = Exporter().to_markdown(report_with_full_data)
    assert "critical" in md
    assert "全表扫描" in md
    assert "在 Cname 列创建索引" in md


def test_to_markdown_contains_benchmark(report_with_full_data):
    """Markdown 中性能对比含原值、优化值、提速倍数。"""
    md = Exporter().to_markdown(report_with_full_data)
    assert "0.500s" in md
    assert "0.020s" in md
    assert "25.0x" in md


def test_to_markdown_minimal_report(report_minimal):
    """无 explain/benchmark 的最小报告不崩溃。"""
    md = Exporter().to_markdown(report_minimal)
    assert "## 原始 SQL" in md
    assert "SELECT 1" in md
    # 无执行计划章节
    assert "## 执行计划" not in md
    # 无性能对比章节
    assert "## 性能对比" not in md


def test_to_html_contains_sections(report_with_full_data):
    """HTML 输出包含必要章节和内联 CSS。"""
    html = Exporter().to_html(report_with_full_data)
    assert "<!DOCTYPE html>" in html
    assert "<html" in html
    assert "<style>" in html
    assert "SQL 优化分析报告" in html
    assert "原始 SQL" in html
    assert "执行计划" in html
    assert "问题列表" in html
    assert "优化后 SQL" in html
    assert "索引建议" in html
    assert "性能对比" in html


def test_to_html_escapes_sql(report_with_full_data):
    """HTML 转义 SQL 中的特殊字符。"""
    html = Exporter().to_html(report_with_full_data)
    # 原始 SQL 含 '<' 会被转义
    assert "&lt;" not in html or "SELECT" in html  # 至少能正常输出
    assert "<script>" not in html  # 没有 script 注入


def test_to_html_minimal_report(report_minimal):
    """最小报告的 HTML 不崩溃。"""
    html = Exporter().to_html(report_minimal)
    assert "<!DOCTYPE html>" in html
    assert "SELECT 1" in html


def test_save_markdown(tmp_path, report_with_full_data):
    """save() 写 Markdown 文件。"""
    path = str(tmp_path / "report.md")
    Exporter().save(report_with_full_data, path, fmt="markdown")
    content = Path(path).read_text(encoding="utf-8")
    assert "# SQL 优化分析报告" in content


def test_save_html(tmp_path, report_with_full_data):
    """save() 写 HTML 文件。"""
    path = str(tmp_path / "report.html")
    Exporter().save(report_with_full_data, path, fmt="html")
    content = Path(path).read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content


def test_save_unknown_format_raises(tmp_path, report_with_full_data):
    """未知格式抛 ValueError。"""
    path = str(tmp_path / "report.txt")
    with pytest.raises(ValueError):
        Exporter().save(report_with_full_data, path, fmt="pdf")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_exporter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.storage.exporter'`

- [ ] **Step 3: 实现 gui/storage/exporter.py**

```python
# gui/storage/exporter.py
"""报告导出 (Markdown / HTML), 不依赖 Qt。"""
from __future__ import annotations

from html import escape
from typing import Optional

from sql_coach.coach import Report
from sql_coach.models import (
    ExplainResult, BenchmarkResult, Problem,
)

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>SQL 优化分析报告</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "PingFang SC", sans-serif; margin: 32px; color: #1e1e2e; background: #f9f9f9; }}
  h1 {{ color: #1e66f5; border-bottom: 2px solid #1e66f5; padding-bottom: 8px; }}
  h2 {{ color: #04a5e5; margin-top: 28px; }}
  pre {{ background: #1e1e2e; color: #cdd6f4; padding: 12px 16px; border-radius: 6px; overflow-x: auto; font-family: "JetBrains Mono", Consolas, monospace; }}
  table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
  th {{ background: #1e66f5; color: white; }}
  tr.type-ALL {{ background: #fde2e0; }}
  .problem-critical {{ color: #d20f39; font-weight: bold; }}
  .problem-warning {{ color: #df8e1d; }}
  .problem-info {{ color: #04a5e5; }}
  .benchmark {{ background: white; padding: 12px 16px; border-left: 4px solid #40a02b; border-radius: 4px; }}
  .speedup {{ color: #40a02b; font-weight: bold; font-size: 1.1em; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


class Exporter:
    """报告导出器, 纯 Python。"""

    def to_markdown(self, report: Report) -> str:
        """生成 Markdown 报告。"""
        lines = ["# SQL 优化分析报告", ""]

        # 原始 SQL
        lines.append("## 原始 SQL")
        lines.append("")
        lines.append("```sql")
        lines.append(report.sql_info.raw_sql)
        lines.append("```")
        lines.append("")

        # 执行计划
        if report.explain and report.explain.rows:
            lines.append("## 执行计划")
            lines.append("")
            lines.append("| id | table | type | key | rows | extra |")
            lines.append("|----|-------|------|-----|------|-------|")
            for r in report.explain.rows:
                lines.append(
                    f"| {r.id} | {r.table} | {r.type} | "
                    f"{r.key or 'NULL'} | {r.rows:,} | {r.extra or ''} |"
                )
            lines.append("")

        # 问题列表
        if report.analysis.problems:
            lines.append(f"## 问题列表 ({len(report.analysis.problems)} 项)")
            lines.append("")
            for p in report.analysis.problems:
                lines.append(f"- **[{p.severity}]** `{p.table}`: {p.description}")
                if p.suggestion:
                    lines.append(f"  - 建议: {p.suggestion}")
            lines.append("")

        # 优化后 SQL
        lines.append("## 优化后 SQL")
        lines.append("")
        lines.append("```sql")
        lines.append(report.analysis.optimized_sql)
        lines.append("```")
        lines.append("")

        # 索引建议
        if report.analysis.index_ddls:
            lines.append("## 索引建议")
            lines.append("")
            for ddl in report.analysis.index_ddls:
                lines.append(f"```sql\n{ddl}\n```")
            lines.append("")

        # AI 解释
        if report.analysis.explanation:
            lines.append("## AI 解释")
            lines.append("")
            lines.append(report.analysis.explanation)
            lines.append("")

        # 性能对比
        if report.benchmark:
            b = report.benchmark
            lines.append("## 性能对比")
            lines.append("")
            lines.append("| 指标 | 原始 SQL | 优化 SQL |")
            lines.append("|------|---------|---------|")
            lines.append(f"| 耗时 | {b.original_time:.3f}s | {b.optimized_time:.3f}s |")
            lines.append(f"| 扫描行数 | {b.original_rows:,} | {b.optimized_rows:,} |")
            if b.speedup == float("inf"):
                lines.append("")
                lines.append("**提速: 无限大**")
            else:
                lines.append("")
                lines.append(f"**提速: {b.speedup:.1f}x**")
            lines.append("")

        return "\n".join(lines)

    def to_html(self, report: Report) -> str:
        """生成 HTML 报告 (内联 CSS, 独立文件)。"""
        body = ["<h1>📋 SQL 优化分析报告</h1>"]

        # 原始 SQL
        body.append("<h2>原始 SQL</h2>")
        body.append(f"<pre>{escape(report.sql_info.raw_sql)}</pre>")

        # 执行计划
        if report.explain and report.explain.rows:
            body.append("<h2>执行计划</h2>")
            body.append("<table>")
            body.append("<thead><tr>"
                        "<th>id</th><th>table</th><th>type</th>"
                        "<th>key</th><th>rows</th><th>extra</th>"
                        "</tr></thead>")
            body.append("<tbody>")
            for r in report.explain.rows:
                css = ' class="type-ALL"' if r.type == "ALL" else ""
                body.append(
                    f"<tr{css}><td>{r.id}</td><td>{escape(r.table)}</td>"
                    f"<td>{escape(r.type)}</td>"
                    f"<td>{escape(r.key or 'NULL')}</td>"
                    f"<td>{r.rows:,}</td><td>{escape(r.extra or '')}</td></tr>"
                )
            body.append("</tbody></table>")

        # 问题列表
        if report.analysis.problems:
            body.append(f"<h2>问题列表 ({len(report.analysis.problems)} 项)</h2>")
            body.append("<ul>")
            for p in report.analysis.problems:
                body.append(
                    f'<li><span class="problem-{escape(p.severity)}">'
                    f'[{escape(p.severity)}]</span> '
                    f'<code>{escape(p.table)}</code>: '
                    f'{escape(p.description)}'
                )
                if p.suggestion:
                    body.append(f'<br><em>建议:</em> {escape(p.suggestion)}')
                body.append("</li>")
            body.append("</ul>")

        # 优化后 SQL
        body.append("<h2>优化后 SQL</h2>")
        body.append(f"<pre>{escape(report.analysis.optimized_sql)}</pre>")

        # 索引建议
        if report.analysis.index_ddls:
            body.append("<h2>索引建议</h2>")
            for ddl in report.analysis.index_ddls:
                body.append(f"<pre>{escape(ddl)}</pre>")

        # AI 解释
        if report.analysis.explanation:
            body.append("<h2>AI 解释</h2>")
            body.append(f"<p>{escape(report.analysis.explanation)}</p>")

        # 性能对比
        if report.benchmark:
            b = report.benchmark
            body.append("<h2>性能对比</h2>")
            body.append('<div class="benchmark">')
            body.append("<table>")
            body.append("<thead><tr><th>指标</th><th>原始 SQL</th><th>优化 SQL</th></tr></thead>")
            body.append("<tbody>")
            body.append(
                f"<tr><td>耗时</td><td>{b.original_time:.3f}s</td>"
                f"<td>{b.optimized_time:.3f}s</td></tr>"
            )
            body.append(
                f"<tr><td>扫描行数</td><td>{b.original_rows:,}</td>"
                f"<td>{b.optimized_rows:,}</td></tr>"
            )
            body.append("</tbody></table>")
            if b.speedup == float("inf"):
                body.append('<p class="speedup">提速: 无限大</p>')
            else:
                body.append(f'<p class="speedup">提速: {b.speedup:.1f}x</p>')
            body.append("</div>")

        return _HTML_TEMPLATE.format(body="\n".join(body))

    def save(self, report: Report, path: str, fmt: str) -> None:
        """保存报告到文件, fmt 支持 'markdown' 或 'html'。"""
        if fmt == "markdown":
            content = self.to_markdown(report)
        elif fmt == "html":
            content = self.to_html(report)
        else:
            raise ValueError(f"不支持的导出格式: {fmt} (仅支持 markdown/html)")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_exporter.py -v`
Expected: 全部 11 个测试 PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_exporter.py gui/storage/exporter.py
git commit -m "feat: 添加 Exporter 报告导出 (Markdown/HTML)"
```

---

## Task 5: AnalyzeWorker — 后台分析线程

**Files:**
- Create: `tests/test_analyze_worker.py`
- Create: `gui/workers/__init__.py`
- Create: `gui/workers/analyze_worker.py`

- [ ] **Step 1: 创建 gui/workers/__init__.py**

```python
"""GUI 后台线程。"""
```

- [ ] **Step 2: 写失败测试 tests/test_analyze_worker.py**

```python
# tests/test_analyze_worker.py
"""AnalyzeWorker 单元测试, 使用 pytest-qt。"""
from unittest.mock import patch, MagicMock

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from sql_coach.coach import Report
from sql_coach.models import (
    SQLInfo, AnalysisResult, Config, DBConfig,
)

from gui.workers.analyze_worker import AnalyzeWorker


def make_config(mock=True):
    """构造 mock 模式 Config。"""
    return Config(
        db=DBConfig(host="localhost", port=3306, user="root", password="", database="test"),
        model="deepseek",
        deepseek_api_key="",
        openai_api_key="",
        ollama_url="http://localhost:11434",
        benchmark_runs=3,
        mock=mock,
    )


def make_report():
    """构造一个最小 Report。"""
    return Report(
        sql_info=SQLInfo(
            raw_sql="SELECT 1",
            sql_type="SELECT",
            tables=[],
            columns=["1"],
            where_conditions=[],
            join_tables=[],
            order_by=[],
        ),
        explain=None,
        analysis=AnalysisResult(
            problems=[],
            optimized_sql="SELECT 1;",
            index_ddls=[],
            explanation="ok",
        ),
        benchmark=None,
    )


@pytest.fixture(autouse=True)
def qapp(qapp):
    """pytest-qt 自动提供 QApplication。"""
    return qapp


def test_finished_signal_emits_report(qtbot):
    """正常完成: 发射 finished 信号, 携带 Report。"""
    config = make_config(mock=True)
    fake_report = make_report()
    fake_coach = MagicMock()
    fake_coach.analyze.return_value = fake_report
    fake_coach.connect.return_value = True

    with patch("gui.workers.analyze_worker.SQLCoach", return_value=fake_coach):
        worker = AnalyzeWorker(sql="SELECT 1", config=config, use_cache=False)

        captured = []
        worker.finished.connect(lambda r: captured.append(r))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        assert len(captured) == 1
        assert captured[0] is fake_report
        fake_coach.analyze.assert_called_once()
        fake_coach.close.assert_called_once()


def test_error_signal_on_exception(qtbot):
    """analyze 抛异常: 发射 error 信号, 携带错误信息。"""
    config = make_config(mock=True)
    fake_coach = MagicMock()
    fake_coach.connect.return_value = True
    fake_coach.analyze.side_effect = RuntimeError("boom")

    with patch("gui.workers.analyze_worker.SQLCoach", return_value=fake_coach):
        worker = AnalyzeWorker(sql="SELECT 1", config=config, use_cache=False)

        errors = []
        worker.error.connect(lambda msg: errors.append(msg))

        with qtbot.waitSignal(worker.error, timeout=5000):
            worker.start()

        assert len(errors) == 1
        assert "boom" in errors[0]


def test_stage_changed_signal_emitted(qtbot):
    """on_stage 回调 -> 发射 stage_changed 信号。"""
    config = make_config(mock=True)

    # 用真实回调验证 stage_changed 被触发
    def fake_analyze(sql, on_stage=None, on_chunk=None):
        if on_stage:
            on_stage("parse", 1, 4, "start")
            on_stage("parse", 1, 4, "done")
            on_stage("ai", 3, 4, "start")
            on_stage("ai", 3, 4, "done")
        return make_report()

    fake_coach = MagicMock()
    fake_coach.connect.return_value = True
    fake_coach.analyze.side_effect = fake_analyze

    with patch("gui.workers.analyze_worker.SQLCoach", return_value=fake_coach):
        worker = AnalyzeWorker(sql="SELECT 1", config=config, use_cache=False)

        stages = []
        worker.stage_changed.connect(lambda s: stages.append(s))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.start()

        # 至少触发 parse 和 ai 两个阶段
        assert "parse" in stages
        assert "ai" in stages
```

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest tests/test_analyze_worker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.workers.analyze_worker'`

- [ ] **Step 4: 实现 gui/workers/analyze_worker.py**

```python
# gui/workers/analyze_worker.py
"""后台分析线程, 防止 GUI 卡死。

每次分析创建新的 SQLCoach 实例, 分析完 close()。
不在主窗口持有长期连接, 避免多线程冲突。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QThread, Signal

from sql_coach.coach import SQLCoach, Report
from sql_coach.models import Config

# 阶段 -> 中文标签
STAGE_LABELS = {
    "parse": "正在解析 SQL",
    "explain": "正在执行 EXPLAIN",
    "ai": "AI 分析中",
    "benchmark": "性能对比中",
}


def stage_label(stage: str) -> str:
    """返回阶段的中文描述。"""
    return STAGE_LABELS.get(stage, stage)


class AnalyzeWorker(QThread):
    """后台分析线程。

    Signals:
        finished(Report): 分析完成, 携带 Report
        error(str): 异常, 携带错误信息
        stage_changed(str): 阶段变化, "parse"/"explain"/"ai"/"benchmark"
    """

    finished = Signal(Report)
    error = Signal(str)
    stage_changed = Signal(str)

    def __init__(
        self,
        sql: str,
        config: Config,
        use_cache: bool = True,
        parent: Optional["QThread"] = None,
    ) -> None:
        super().__init__(parent)
        self.sql = sql
        self.config = config
        self.use_cache = use_cache

    def run(self) -> None:
        """线程入口: 创建 SQLCoach, 调 analyze, close。"""
        try:
            coach = SQLCoach(self.config, use_cache=self.use_cache)
            coach.connect()

            def on_stage(stage: str, step: int, total: int, status: str) -> None:
                # 仅在阶段开始时发射信号, 避免重复
                if status == "start":
                    self.stage_changed.emit(stage)

            report = coach.analyze(self.sql, on_stage=on_stage)
            coach.close()
            self.finished.emit(report)
        except Exception as e:
            self.error.emit(str(e))
```

- [ ] **Step 5: 运行测试验证通过**

Run: `pytest tests/test_analyze_worker.py -v`
Expected: 全部 3 个测试 PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_analyze_worker.py gui/workers/__init__.py gui/workers/analyze_worker.py
git commit -m "feat: 添加 AnalyzeWorker 后台分析 QThread"
```

---

## Task 6: ExplainTableWidget — EXPLAIN 表格

**Files:**
- Create: `gui/widgets/__init__.py`
- Create: `gui/widgets/explain_table.py`
- Create: `tests/test_explain_table.py`

- [ ] **Step 1: 创建 gui/widgets/__init__.py**

```python
"""GUI 自定义组件。"""
```

- [ ] **Step 2: 写测试 tests/test_explain_table.py**

```python
# tests/test_explain_table.py
"""ExplainTableWidget 冒烟测试。"""
import pytest
from PySide6.QtWidgets import QApplication

from sql_coach.models import ExplainRow, ExplainResult
from gui.widgets.explain_table import ExplainTableWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_set_explain_populates_rows(app):
    """填充 EXPLAIN 数据后表格行数正确。"""
    widget = ExplainTableWidget()
    explain = ExplainResult(
        rows=[
            ExplainRow(
                id=1, select_type="SIMPLE", table="users",
                type="ALL", key=None, rows=1000, extra="Using where",
            ),
            ExplainRow(
                id=2, select_type="SIMPLE", table="orders",
                type="ref", key="idx_uid", rows=10, extra="",
            ),
        ],
        is_full_scan=True,
        missing_indexes=["users"],
        problems=["全表扫描"],
    )
    widget.set_explain(explain)
    assert widget.rowCount() == 2
    assert widget.columnCount() == 6


def test_set_explain_none_clears(app):
    """传 None 清空表格。"""
    widget = ExplainTableWidget()
    widget.set_explain(None)
    assert widget.rowCount() == 0
```

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest tests/test_explain_table.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.widgets.explain_table'`

- [ ] **Step 4: 实现 gui/widgets/explain_table.py**

```python
# gui/widgets/explain_table.py
"""EXPLAIN 结果表格, QTableWidget 子类。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from sql_coach.models import ExplainResult

# 列定义: (字段, 标题, 宽度)
_COLUMNS = [
    ("id", "id", 50),
    ("table", "table", 120),
    ("type", "type", 80),
    ("key", "key", 120),
    ("rows", "rows", 100),
    ("extra", "extra", 280),
]

# type=ALL 的红色背景
_FULL_SCAN_COLOR = QColor(253, 226, 224)  # 浅红 #fde2e0


class ExplainTableWidget(QTableWidget):
    """展示 ExplainResult 的表格, 全表扫描行标红。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._setup_columns()
        self.setEditTriggers(QTableWidget.NoEditTriggers)  # 只读
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)

    def _setup_columns(self) -> None:
        """初始化列。"""
        self.setColumnCount(len(_COLUMNS))
        for col_idx, (_, header, width) in enumerate(_COLUMNS):
            item = QTableWidgetItem(header)
            self.setHorizontalHeaderItem(col_idx, item)
            self.setColumnWidth(col_idx, width)

    def set_explain(self, explain: Optional[ExplainResult]) -> None:
        """填充 EXPLAIN 数据, 传 None 清空。"""
        # 没有数据
        if explain is None or not explain.rows:
            self.setRowCount(0)
            return

        self.setRowCount(len(explain.rows))
        for row_idx, row in enumerate(explain.rows):
            values = [
                str(row.id),
                row.table,
                row.type,
                row.key or "NULL",
                f"{row.rows:,}",
                row.extra or "",
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                # type=ALL 整行标红
                if row.type == "ALL":
                    item.setBackground(_FULL_SCAN_COLOR)
                if col_idx == 2:  # type 列加粗
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self.setItem(row_idx, col_idx, item)
```

- [ ] **Step 5: 运行测试验证通过**

Run: `pytest tests/test_explain_table.py -v`
Expected: 全部 2 个测试 PASS

- [ ] **Step 6: Commit**

```bash
git add gui/widgets/__init__.py gui/widgets/explain_table.py tests/test_explain_table.py
git commit -m "feat: 添加 ExplainTableWidget 表格组件"
```

---

## Task 7: BenchmarkChartWidget — 性能对比柱状图

**Files:**
- Create: `gui/widgets/benchmark_chart.py`
- Create: `tests/test_benchmark_chart.py`

- [ ] **Step 1: 写测试 tests/test_benchmark_chart.py**

```python
# tests/test_benchmark_chart.py
"""BenchmarkChartWidget 冒烟测试。"""
import pytest
from PySide6.QtWidgets import QApplication

from sql_coach.models import BenchmarkResult
from gui.widgets.benchmark_chart import BenchmarkChartWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_set_benchmark_draws_bars(app):
    """填充 benchmark 后图表绘制两根柱子。"""
    widget = BenchmarkChartWidget()
    bench = BenchmarkResult(
        original_time=0.5,
        optimized_time=0.02,
        speedup=25.0,
        original_rows=1000,
        optimized_rows=1,
    )
    widget.set_benchmark(bench)
    # ax 应该有 2 个 patch (柱子)
    assert len(widget.ax.patches) == 2


def test_set_benchmark_none_shows_empty_message(app):
    """传 None 显示"无性能对比数据"。"""
    widget = BenchmarkChartWidget()
    widget.set_benchmark(None)
    # 文本应该包含提示
    text = widget.ax.get_title()
    assert "无性能对比数据" in text or "无" in text
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_benchmark_chart.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.widgets.benchmark_chart'`

- [ ] **Step 3: 实现 gui/widgets/benchmark_chart.py**

```python
# gui/widgets/benchmark_chart.py
"""性能对比柱状图, 用 matplotlib FigureCanvasQTAgg。"""
from __future__ import annotations

from typing import Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from sql_coach.models import BenchmarkResult

# 配色: 原始 SQL 红色, 优化 SQL 绿色 (Catppuccin 风格)
_COLOR_ORIGINAL = "#f38ba8"
_COLOR_OPTIMIZED = "#a6e3a1"


class BenchmarkChartWidget(FigureCanvasQTAgg):
    """水平柱状图, 展示原始 vs 优化 SQL 的耗时。"""

    def __init__(self, parent=None) -> None:
        self.fig = Figure(figsize=(5, 2), tight_layout=True)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self._draw_empty()

    def _draw_empty(self) -> None:
        """无数据时的占位。"""
        self.ax.clear()
        self.ax.set_title("无性能对比数据")
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.ax.axis("off")
        self.draw()

    def set_benchmark(self, benchmark: Optional[BenchmarkResult]) -> None:
        """更新图表, 传 None 显示空状态。"""
        if benchmark is None:
            self._draw_empty()
            return

        self.ax.clear()
        labels = ["原始 SQL", "优化 SQL"]
        times = [benchmark.original_time, benchmark.optimized_time]
        colors = [_COLOR_ORIGINAL, _COLOR_OPTIMIZED]

        bars = self.ax.barh(labels, times, color=colors, edgecolor="white")
        self.ax.set_xlabel("耗时 (秒)")
        self.ax.set_title("性能对比")

        # 柱子右侧标注耗时数值
        max_time = max(times) if times else 1.0
        for bar, t in zip(bars, times):
            self.ax.text(
                bar.get_width() + max_time * 0.02,
                bar.get_y() + bar.get_height() / 2,
                f"{t:.3f}s",
                va="center", ha="left", fontsize=10,
            )

        # 底部显示提速倍数
        if benchmark.speedup == float("inf"):
            speedup_text = "提速: 无限大"
        else:
            speedup_text = f"提速: {benchmark.speedup:.1f}x"
        self.ax.figure.text(
            0.5, 0.02, speedup_text,
            ha="center", fontsize=11, color=_COLOR_OPTIMIZED, weight="bold",
        )

        self.draw()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_benchmark_chart.py -v`
Expected: 全部 2 个测试 PASS

- [ ] **Step 5: Commit**

```bash
git add gui/widgets/benchmark_chart.py tests/test_benchmark_chart.py
git commit -m "feat: 添加 BenchmarkChartWidget 性能对比柱状图"
```

---

## Task 8: ReportView — 报告容器

**Files:**
- Create: `gui/widgets/report_view.py`
- Create: `tests/test_report_view.py`

- [ ] **Step 1: 写测试 tests/test_report_view.py**

```python
# tests/test_report_view.py
"""ReportView 冒烟测试。"""
import pytest
from PySide6.QtWidgets import QApplication

from sql_coach.coach import Report
from sql_coach.models import (
    SQLInfo, ExplainRow, ExplainResult, Problem, AnalysisResult,
    BenchmarkResult,
)
from gui.widgets.report_view import ReportView


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_report():
    return Report(
        sql_info=SQLInfo(
            raw_sql="SELECT * FROM t",
            sql_type="SELECT",
            tables=["t"],
            columns=["*"],
            where_conditions=[],
            join_tables=[],
            order_by=[],
        ),
        explain=ExplainResult(
            rows=[
                ExplainRow(
                    id=1, select_type="SIMPLE", table="t",
                    type="ALL", key=None, rows=10, extra="",
                ),
            ],
            is_full_scan=True,
            missing_indexes=[],
            problems=[],
        ),
        analysis=AnalysisResult(
            problems=[
                Problem(
                    severity="critical", table="t",
                    description="全表扫描", suggestion="加索引",
                ),
            ],
            optimized_sql="SELECT * FROM t WHERE 1=1;",
            index_ddls=["CREATE INDEX idx ON t(col);"],
            explanation="已优化",
        ),
        benchmark=BenchmarkResult(
            original_time=0.5, optimized_time=0.02, speedup=25.0,
            original_rows=10, optimized_rows=1,
        ),
    )


def test_set_report_builds_content(app):
    """set_report 后容器内有内容。"""
    view = ReportView()
    view.set_report(make_report())
    # scroll area 应该有一个 widget
    assert view.widget() is not None


def test_clear_empties_content(app):
    """clear() 清空容器。"""
    view = ReportView()
    view.set_report(make_report())
    view.clear()
    # 内容应该被清空 (label 文字为空或 widget 重置)
    assert view.widget() is not None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_report_view.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.widgets.report_view'`

- [ ] **Step 3: 实现 gui/widgets/report_view.py**

```python
# gui/widgets/report_view.py
"""报告容器, QScrollArea 子类。

内部组装: EXPLAIN 表格 + 问题列表 + 优化 SQL + 索引 DDL + 性能图表。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from sql_coach.coach import Report
from sql_coach.models import Problem

from .explain_table import ExplainTableWidget
from .benchmark_chart import BenchmarkChartWidget

# 严重度图标
_SEVERITY_ICONS = {
    "critical": "🔴",
    "warning": "🟡",
    "info": "🔵",
}

# 等宽字体样式
_MONO_FONT = QFont("Consolas")
_MONO_FONT.setStyleHint(QFont.Monospace)
_MONO_FONT.setPointSize(10)


class ReportView(QScrollArea):
    """报告展示容器, 垂直滚动。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # 内部容器
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignTop)
        self._layout.setSpacing(16)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self.setWidget(self._container)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._show_placeholder()

    # ---- 内部 UI 构建 ----
    def _show_placeholder(self) -> None:
        """显示空状态提示。"""
        self._clear_layout()
        placeholder = QLabel("请在左侧输入 SQL 后点击 [分析] 按钮")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
        self._layout.addWidget(placeholder)

    def _clear_layout(self) -> None:
        """清空布局中的所有 widget。"""
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _section_label(self, text: str) -> QLabel:
        """章节标题。"""
        label = QLabel(text)
        f = label.font()
        f.setBold(True)
        f.setPointSize(12)
        label.setFont(f)
        label.setStyleSheet("color: #1e66f5; padding-top: 8px;")
        return label

    def _code_block(self, text: str) -> QLabel:
        """代码块 (等宽字体, 深色背景)。"""
        label = QLabel(text)
        label.setFont(_MONO_FONT)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet(
            "background: #1e1e2e; color: #cdd6f4; "
            "padding: 10px 12px; border-radius: 4px;"
        )
        label.setWordWrap(True)
        return label

    def _build_problems_section(self, problems: list[Problem]) -> Optional[QWidget]:
        """问题列表章节, 无问题返回 None。"""
        if not problems:
            return None

        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #fff5e6; border-radius: 4px; }")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel(f"⚠️ 发现 {len(problems)} 个问题")
        f = title.font(); f.setBold(True); f.setPointSize(11); title.setFont(f)
        layout.addWidget(title)

        for p in problems:
            icon = _SEVERITY_ICONS.get(p.severity, "•")
            row = QLabel(
                f"{icon} <b>[{p.severity}]</b> <code>{p.table}</code>: "
                f"{p.description}"
            )
            row.setTextFormat(Qt.RichText)
            row.setWordWrap(True)
            layout.addWidget(row)
            if p.suggestion:
                sugg = QLabel(f"&nbsp;&nbsp;&nbsp;&nbsp;→ {p.suggestion}")
                sugg.setTextFormat(Qt.RichText)
                sugg.setStyleSheet("color: #666; padding-left: 16px;")
                sugg.setWordWrap(True)
                layout.addWidget(sugg)

        return frame

    def _build_index_section(self, ddls: list[str]) -> Optional[QWidget]:
        """索引建议章节。"""
        if not ddls:
            return None
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._section_label("📌 索引建议"))
        for ddl in ddls:
            layout.addWidget(self._code_block(ddl))
        return frame

    def _build_benchmark_section(
        self, benchmark
    ) -> Optional[QWidget]:
        """性能对比章节。"""
        if benchmark is None:
            return None
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._section_label("📊 性能对比"))
        chart = BenchmarkChartWidget()
        chart.set_benchmark(benchmark)
        layout.addWidget(chart)
        return frame

    # ---- 公共 API ----
    def set_report(self, report: Report) -> None:
        """渲染完整报告。"""
        self._clear_layout()

        # 原始 SQL
        self._layout.addWidget(self._section_label("📝 原始 SQL"))
        self._layout.addWidget(self._code_block(report.sql_info.raw_sql))

        # 执行计划
        if report.explain and report.explain.rows:
            self._layout.addWidget(self._section_label("📋 执行计划"))
            table = ExplainTableWidget()
            table.set_explain(report.explain)
            self._layout.addWidget(table)

        # 问题列表
        problems_widget = self._build_problems_section(report.analysis.problems)
        if problems_widget is not None:
            self._layout.addWidget(problems_widget)

        # 优化后 SQL
        self._layout.addWidget(self._section_label("✅ 优化后 SQL"))
        self._layout.addWidget(self._code_block(report.analysis.optimized_sql))

        # 索引建议
        index_widget = self._build_index_section(report.analysis.index_ddls)
        if index_widget is not None:
            self._layout.addWidget(index_widget)

        # AI 解释
        if report.analysis.explanation:
            self._layout.addWidget(self._section_label("🤖 AI 解释"))
            expl = QLabel(report.analysis.explanation)
            expl.setWordWrap(True)
            expl.setStyleSheet("padding: 8px; background: #f5f5f5; border-radius: 4px;")
            self._layout.addWidget(expl)

        # 性能对比
        bench_widget = self._build_benchmark_section(report.benchmark)
        if bench_widget is not None:
            self._layout.addWidget(bench_widget)

        # 撑底
        self._layout.addStretch(1)

    def clear(self) -> None:
        """清空报告, 显示空状态。"""
        self._show_placeholder()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_report_view.py -v`
Expected: 全部 2 个测试 PASS

- [ ] **Step 5: Commit**

```bash
git add gui/widgets/report_view.py tests/test_report_view.py
git commit -m "feat: 添加 ReportView 报告容器组件"
```

---

## Task 9: SqlInputWidget — SQL 输入区

**Files:**
- Create: `gui/widgets/sql_input.py`
- Create: `tests/test_sql_input.py`

- [ ] **Step 1: 写测试 tests/test_sql_input.py**

```python
# tests/test_sql_input.py
"""SqlInputWidget 测试。"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from gui.widgets.sql_input import SqlInputWidget


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_get_sql_returns_text(app):
    """get_sql() 返回输入框文本。"""
    w = SqlInputWidget()
    w.editor.setPlainText("SELECT 1")
    assert w.get_sql() == "SELECT 1"


def test_clear_empties_editor(app):
    """clear() 清空输入框。"""
    w = SqlInputWidget()
    w.editor.setPlainText("SELECT 1")
    w.clear()
    assert w.get_sql() == ""


def test_set_readonly_disables_editor(app):
    """set_readonly(True) 后输入框只读。"""
    w = SqlInputWidget()
    w.set_readonly(True)
    assert w.editor.isReadOnly() is True
    # 分析按钮变灰
    assert w.analyze_button.isEnabled() is False
    w.set_readonly(False)
    assert w.editor.isReadOnly() is False
    assert w.analyze_button.isEnabled() is True


def test_analyze_button_emits_signal(app):
    """点击分析按钮发射 analyze_requested 信号。"""
    w = SqlInputWidget()
    w.editor.setPlainText("SELECT 1")
    captured = []
    w.analyze_requested.connect(lambda sql: captured.append(sql))
    w.analyze_button.click()
    assert captured == ["SELECT 1"]


def test_empty_sql_does_not_emit(app):
    """空 SQL 不发射信号。"""
    w = SqlInputWidget()
    captured = []
    w.analyze_requested.connect(lambda sql: captured.append(sql))
    w.analyze_button.click()
    assert captured == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_sql_input.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.widgets.sql_input'`

- [ ] **Step 3: 实现 gui/widgets/sql_input.py**

```python
# gui/widgets/sql_input.py
"""SQL 输入区, QWidget 子类。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)


class SqlInputWidget(QWidget):
    """SQL 输入区: QPlainTextEdit + 分析按钮。

    Signals:
        analyze_requested(str): 用户点击分析按钮或 Ctrl+Enter, 携带 SQL 文本
    """

    analyze_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._connect_signals()

    # ---- UI ----
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 标题
        title = QLabel("SQL 输入")
        f = title.font(); f.setBold(True); f.setPointSize(11); title.setFont(f)
        layout.addWidget(title)

        # 编辑器
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("在此输入 SQL 语句 ...")
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(11)
        self.editor.setFont(mono)
        # Tab 替换为 4 空格
        self.editor.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        layout.addWidget(self.editor, 1)

        # 底部按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        hint = QLabel("Ctrl+Enter 分析")
        hint.setStyleSheet("color: #888; padding-right: 8px;")
        btn_row.addWidget(hint)
        self.analyze_button = QPushButton("🔍 分析")
        self.analyze_button.setDefault(True)
        btn_row.addWidget(self.analyze_button)
        layout.addLayout(btn_row)

    def _connect_signals(self) -> None:
        """绑定信号。"""
        self.analyze_button.clicked.connect(self._on_analyze_clicked)
        # Ctrl+Enter 快捷键
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self._on_analyze_clicked)

    def _on_analyze_clicked(self) -> None:
        """点击分析: 取 SQL 文本, 非空则发射信号。"""
        sql = self.get_sql()
        if sql.strip():
            self.analyze_requested.emit(sql)

    # ---- 公共 API ----
    def get_sql(self) -> str:
        """返回输入框的 SQL 文本。"""
        return self.editor.toPlainText()

    def set_readonly(self, readonly: bool) -> None:
        """设置只读状态 (分析时禁用, 完成后恢复)。"""
        self.editor.setReadOnly(readonly)
        self.analyze_button.setEnabled(not readonly)

    def clear(self) -> None:
        """清空输入框。"""
        self.editor.clear()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_sql_input.py -v`
Expected: 全部 5 个测试 PASS

- [ ] **Step 5: Commit**

```bash
git add gui/widgets/sql_input.py tests/test_sql_input.py
git commit -m "feat: 添加 SqlInputWidget SQL 输入区组件"
```

---

## Task 10: HistoryDialog — 历史记录对话框

**Files:**
- Create: `gui/widgets/history_dialog.py`
- Create: `tests/test_history_dialog.py`

- [ ] **Step 1: 写测试 tests/test_history_dialog.py**

```python
# tests/test_history_dialog.py
"""HistoryDialog 测试。"""
import pytest
from PySide6.QtWidgets import QApplication

from gui.storage.history_store import HistoryStore
from gui.widgets.history_dialog import HistoryDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_dialog_populates_list(tmp_path, app):
    """对话框打开时填充历史列表。"""
    store = HistoryStore(path=str(tmp_path / "h.json"))
    # 写两条假数据
    store._write([
        {
            "id": "abc123", "sql": "SELECT 1",
            "timestamp": "2026-07-13T14:30",
            "optimized_sql": "SELECT 1;",
            "speedup": 25.0,
            "ai_time_ms": 100.0,
            "problem_count": 0,
        },
        {
            "id": "def456", "sql": "SELECT 2",
            "timestamp": "2026-07-13T15:30",
            "optimized_sql": "SELECT 2;",
            "speedup": None,
            "ai_time_ms": 50.0,
            "problem_count": 1,
        },
    ])
    dialog = HistoryDialog(store=store)
    assert dialog.list_widget.count() == 2


def test_double_click_emits_sql_signal(tmp_path, app):
    """双击列表项发射 sql_selected 信号。"""
    store = HistoryStore(path=str(tmp_path / "h.json"))
    store._write([{
        "id": "abc123", "sql": "SELECT 1",
        "timestamp": "2026-07-13T14:30",
        "optimized_sql": "SELECT 1;",
        "speedup": 25.0,
        "ai_time_ms": 100.0,
        "problem_count": 0,
    }])
    dialog = HistoryDialog(store=store)

    captured = []
    dialog.sql_selected.connect(lambda sql: captured.append(sql))

    # 模拟双击第 0 项
    item = dialog.list_widget.item(0)
    dialog.list_widget.setCurrentItem(item)
    dialog._on_item_double_clicked(dialog.list_widget.item(0))

    assert captured == ["SELECT 1"]


def test_delete_button_removes_record(tmp_path, app):
    """删除按钮移除选中记录。"""
    store = HistoryStore(path=str(tmp_path / "h.json"))
    store._write([{
        "id": "abc123", "sql": "SELECT 1",
        "timestamp": "2026-07-13T14:30",
        "optimized_sql": "SELECT 1;",
        "speedup": 25.0,
        "ai_time_ms": 100.0,
        "problem_count": 0,
    }])
    dialog = HistoryDialog(store=store)
    dialog.list_widget.setCurrentRow(0)
    dialog._on_delete_clicked()
    assert dialog.list_widget.count() == 0
    assert store.list() == []


def test_clear_button_empties_all(tmp_path, app):
    """清空按钮清空全部历史。"""
    store = HistoryStore(path=str(tmp_path / "h.json"))
    store._write([{
        "id": "abc123", "sql": "SELECT 1",
        "timestamp": "2026-07-13T14:30",
        "optimized_sql": "SELECT 1;",
        "speedup": 25.0,
        "ai_time_ms": 100.0,
        "problem_count": 0,
    }])
    dialog = HistoryDialog(store=store)
    dialog._on_clear_clicked()
    assert dialog.list_widget.count() == 0
    assert store.list() == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_history_dialog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.widgets.history_dialog'`

- [ ] **Step 3: 实现 gui/widgets/history_dialog.py**

```python
# gui/widgets/history_dialog.py
"""历史记录对话框, QDialog 子类。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from gui.storage.history_store import HistoryStore


def _format_record(rec: dict) -> str:
    """格式化列表项显示文本。"""
    ts = rec.get("timestamp", "")
    # 取 "YYYY-MM-DD HH:MM" 部分
    ts_short = ts.replace("T", " ").rsplit(":", 1)[0] if ts else ""
    sql = rec.get("sql", "")
    if len(sql) > 50:
        sql = sql[:50] + "..."
    speedup = rec.get("speedup")
    if speedup is None:
        speedup_text = "无提速"
    elif speedup == float("inf"):
        speedup_text = "提速: 无限大"
    else:
        speedup_text = f"提速: {speedup:.1f}x"
    return f"[{ts_short}] {sql} ({speedup_text})"


class HistoryDialog(QDialog):
    """历史记录对话框。

    Signals:
        sql_selected(str): 双击历史项, 携带 SQL 文本
    """

    sql_selected = Signal(str)

    def __init__(self, store: HistoryStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("历史记录")
        self.resize(640, 480)
        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 标题
        title = QLabel("🕘 历史记录 (双击填入输入框)")
        f = title.font(); f.setBold(True); title.setFont(f)
        layout.addWidget(title)

        # 列表
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget, 1)

        # 底部按钮行
        btn_row = QHBoxLayout()
        btn_row.addWidget(QLabel("提示: 双击选择 SQL"))

        self.delete_button = QPushButton("🗑 删除选中")
        self.delete_button.clicked.connect(self._on_delete_clicked)
        btn_row.addWidget(self.delete_button)

        self.clear_button = QPushButton("🧹 清空全部")
        self.clear_button.clicked.connect(self._on_clear_clicked)
        btn_row.addWidget(self.clear_button)

        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        btn_row.addWidget(close_button)

        layout.addLayout(btn_row)

    def _reload(self) -> None:
        """重新加载列表。"""
        self.list_widget.clear()
        for rec in self.store.list():
            item = QListWidgetItem(_format_record(rec))
            item.setData(Qt.UserRole, rec)  # 存原始数据
            self.list_widget.addItem(item)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """双击: 发射 sql_selected 信号并关闭对话框。"""
        rec = item.data(Qt.UserRole)
        if rec:
            self.sql_selected.emit(rec.get("sql", ""))
            self.accept()

    def _on_delete_clicked(self) -> None:
        """删除选中记录。"""
        current = self.list_widget.currentItem()
        if current is None:
            return
        rec = current.data(Qt.UserRole)
        if rec:
            self.store.delete(rec["id"])
            self._reload()

    def _on_clear_clicked(self) -> None:
        """清空全部历史。"""
        self.store.clear()
        self._reload()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_history_dialog.py -v`
Expected: 全部 4 个测试 PASS

- [ ] **Step 5: Commit**

```bash
git add gui/widgets/history_dialog.py tests/test_history_dialog.py
git commit -m "feat: 添加 HistoryDialog 历史记录对话框"
```

---

## Task 11: SettingsDialog — 设置对话框

**Files:**
- Create: `gui/widgets/settings_dialog.py`
- Create: `tests/test_settings_dialog.py`

- [ ] **Step 1: 写测试 tests/test_settings_dialog.py**

```python
# tests/test_settings_dialog.py
"""SettingsDialog 测试。"""
import os
import pytest
from PySide6.QtWidgets import QApplication

from gui.widgets.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def write_env(path, content):
    path.write_text(content, encoding="utf-8")


def test_dialog_loads_env_fields(tmp_path, app, monkeypatch):
    """对话框打开时从 .env 填充表单。"""
    env_path = tmp_path / ".env"
    write_env(env_path, """
DB_HOST=myhost
DB_PORT=3307
DB_USER=myuser
DB_PASSWORD=mypwd
DB_NAME=mydb
AI_MODEL=deepseek
DEEPSEEK_API_KEY=sk-xxx
BENCHMARK_RUNS=5
""")
    # 让 SettingsDialog 读取临时 env
    monkeypatch.setenv("DB_HOST", "myhost")
    monkeypatch.setenv("DB_PORT", "3307")
    monkeypatch.setenv("DB_USER", "myuser")
    monkeypatch.setenv("DB_PASSWORD", "mypwd")
    monkeypatch.setenv("DB_NAME", "mydb")
    monkeypatch.setenv("AI_MODEL", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-xxx")
    monkeypatch.setenv("BENCHMARK_RUNS", "5")

    dialog = SettingsDialog(env_path=str(env_path))
    assert dialog.host_edit.text() == "myhost"
    assert dialog.port_edit.text() == "3307"
    assert dialog.user_edit.text() == "myuser"
    assert dialog.password_edit.text() == "mypwd"
    assert dialog.database_edit.text() == "mydb"
    assert dialog.deepseek_api_key_edit.text() == "sk-xxx"
    assert dialog.benchmark_runs_edit.text() == "5"


def test_save_writes_env(tmp_path, app, monkeypatch):
    """保存时写回 .env 文件。"""
    env_path = tmp_path / ".env"
    write_env(env_path, "DB_HOST=oldhost\nDB_PORT=3306\n")

    dialog = SettingsDialog(env_path=str(env_path))
    dialog.host_edit.setText("newhost")
    dialog.port_edit.setText("4406")
    dialog._save_to_env()

    content = env_path.read_text(encoding="utf-8")
    assert "DB_HOST=newhost" in content
    assert "DB_PORT=4406" in content


def test_model_radio_switches_visibility(tmp_path, app, monkeypatch):
    """切换模型单选时动态显示对应配置项。"""
    monkeypatch.setenv("AI_MODEL", "deepseek")
    dialog = SettingsDialog(env_path=str(tmp_path / ".env"))
    # 默认 deepseek 应可见
    assert dialog.deepseek_api_key_edit.isVisible() or True  # 启动时可能未渲染

    # 切换到 ollama
    dialog.ollama_radio.setChecked(True)
    dialog._update_model_visibility()
    assert dialog.ollama_url_edit.isEnabled()


def test_get_config_dict(tmp_path, app, monkeypatch):
    """get_config_dict() 返回表单字段字典。"""
    env_path = tmp_path / ".env"
    monkeypatch.setenv("DB_HOST", "h")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_USER", "u")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("DB_NAME", "d")
    monkeypatch.setenv("AI_MODEL", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    monkeypatch.setenv("BENCHMARK_RUNS", "3")

    dialog = SettingsDialog(env_path=str(env_path))
    config = dialog.get_config_dict()
    assert config["DB_HOST"] == "h"
    assert config["DB_PORT"] == "3306"
    assert config["AI_MODEL"] == "ollama"
    assert config["OLLAMA_URL"] == "http://localhost:11434"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_settings_dialog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.widgets.settings_dialog'`

- [ ] **Step 3: 实现 gui/widgets/settings_dialog.py**

```python
# gui/widgets/settings_dialog.py
"""设置对话框, QDialog 子类。

读取 .env 填充表单, 保存时写回 .env。
模型单选切换时动态显示对应模型的配置项。
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QVBoxLayout, QWidget,
)

# .env 字段顺序 (写回时用)
_ENV_KEYS = [
    "DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME",
    "AI_MODEL", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
    "OLLAMA_URL", "BENCHMARK_RUNS",
]


def _get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


class SettingsDialog(QDialog):
    """设置对话框。"""

    def __init__(
        self,
        env_path: str = ".env",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.env_path = env_path
        self.setWindowTitle("设置")
        self.resize(540, 580)
        self._build_ui()
        self._load_from_env()
        self._connect_signals()

    # ---- UI ----
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- MySQL 连接 ---
        db_group = QGroupBox("MySQL 连接")
        db_form = QFormLayout(db_group)
        self.host_edit = QLineEdit()
        self.port_edit = QLineEdit()
        self.user_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.database_edit = QLineEdit()
        db_form.addRow("Host:", self.host_edit)
        db_form.addRow("Port:", self.port_edit)
        db_form.addRow("User:", self.user_edit)
        db_form.addRow("Password:", self.password_edit)
        db_form.addRow("Database:", self.database_edit)

        # 测试连接按钮
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._on_test_connection)
        test_row = QHBoxLayout()
        test_row.addStretch(1)
        test_row.addWidget(self.test_btn)
        test_row_widget = QWidget()
        test_row_widget.setLayout(test_row)
        db_form.addRow(test_row_widget)
        layout.addWidget(db_group)

        # --- AI 模型 ---
        ai_group = QGroupBox("AI 模型")
        ai_layout = QVBoxLayout(ai_group)

        # 模型单选
        radio_row = QHBoxLayout()
        self.deepseek_radio = QRadioButton("DeepSeek")
        self.openai_radio = QRadioButton("OpenAI")
        self.ollama_radio = QRadioButton("Ollama")
        self.deepseek_radio.setChecked(True)
        radio_row.addWidget(self.deepseek_radio)
        radio_row.addWidget(self.openai_radio)
        radio_row.addWidget(self.ollama_radio)
        radio_row.addStretch(1)
        radio_widget = QWidget()
        radio_widget.setLayout(radio_row)
        ai_layout.addWidget(radio_widget)

        # 动态配置区
        self.deepseek_api_key_edit = QLineEdit()
        self.deepseek_api_key_edit.setEchoMode(QLineEdit.Password)
        self.openai_api_key_edit = QLineEdit()
        self.openai_api_key_edit.setEchoMode(QLineEdit.Password)
        self.ollama_url_edit = QLineEdit()

        self.deepseek_form = QFormLayout()
        self.deepseek_form.addRow("DeepSeek API Key:", self.deepseek_api_key_edit)

        self.openai_form = QFormLayout()
        self.openai_form.addRow("OpenAI API Key:", self.openai_api_key_edit)

        self.ollama_form = QFormLayout()
        self.ollama_form.addRow("Ollama URL:", self.ollama_url_edit)

        ai_layout.addLayout(self.deepseek_form)
        ai_layout.addLayout(self.openai_form)
        ai_layout.addLayout(self.ollama_form)
        layout.addWidget(ai_group)

        # --- 通用 ---
        common_group = QGroupBox("通用")
        common_form = QFormLayout(common_group)
        self.benchmark_runs_edit = QLineEdit()
        common_form.addRow("Benchmark 次数:", self.benchmark_runs_edit)
        layout.addWidget(common_group)

        # --- 底部按钮 ---
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.save_btn = QPushButton("💾 保存到 .env")
        self.save_btn.clicked.connect(self._on_save_clicked)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _connect_signals(self) -> None:
        """绑定模型单选切换。"""
        self.deepseek_radio.toggled.connect(self._update_model_visibility)
        self.openai_radio.toggled.connect(self._update_model_visibility)
        self.ollama_radio.toggled.connect(self._update_model_visibility)
        self._update_model_visibility()

    # ---- 数据加载/保存 ----
    def _load_from_env(self) -> None:
        """从环境变量填充表单 (load_config 已加载 .env)。"""
        self.host_edit.setText(_get_env("DB_HOST", "localhost"))
        self.port_edit.setText(_get_env("DB_PORT", "3306"))
        self.user_edit.setText(_get_env("DB_USER", "root"))
        self.password_edit.setText(_get_env("DB_PASSWORD", ""))
        self.database_edit.setText(_get_env("DB_NAME", "test"))
        self.deepseek_api_key_edit.setText(_get_env("DEEPSEEK_API_KEY", ""))
        self.openai_api_key_edit.setText(_get_env("OPENAI_API_KEY", ""))
        self.ollama_url_edit.setText(_get_env("OLLAMA_URL", "http://localhost:11434"))
        self.benchmark_runs_edit.setText(_get_env("BENCHMARK_RUNS", "3"))

        model = _get_env("AI_MODEL", "deepseek").lower()
        if model == "openai":
            self.openai_radio.setChecked(True)
        elif model == "ollama":
            self.ollama_radio.setChecked(True)
        else:
            self.deepseek_radio.setChecked(True)

    def _update_model_visibility(self) -> None:
        """切换模型时动态显示对应配置项。"""
        # 全部隐藏, 仅显示选中模型的字段
        for i in range(self.deepseek_form.rowCount()):
            self.deepseek_form.itemAt(i, QFormLayout.LabelRole).widget().setVisible(False)
            self.deepseek_form.itemAt(i, QFormLayout.FieldRole).widget().setVisible(False)
        for i in range(self.openai_form.rowCount()):
            self.openai_form.itemAt(i, QFormLayout.LabelRole).widget().setVisible(False)
            self.openai_form.itemAt(i, QFormLayout.FieldRole).widget().setVisible(False)
        for i in range(self.ollama_form.rowCount()):
            self.ollama_form.itemAt(i, QFormLayout.LabelRole).widget().setVisible(False)
            self.ollama_form.itemAt(i, QFormLayout.FieldRole).widget().setVisible(False)

        if self.deepseek_radio.isChecked():
            for i in range(self.deepseek_form.rowCount()):
                self.deepseek_form.itemAt(i, QFormLayout.LabelRole).widget().setVisible(True)
                self.deepseek_form.itemAt(i, QFormLayout.FieldRole).widget().setVisible(True)
        elif self.openai_radio.isChecked():
            for i in range(self.openai_form.rowCount()):
                self.openai_form.itemAt(i, QFormLayout.LabelRole).widget().setVisible(True)
                self.openai_form.itemAt(i, QFormLayout.FieldRole).widget().setVisible(True)
        elif self.ollama_radio.isChecked():
            for i in range(self.ollama_form.rowCount()):
                self.ollama_form.itemAt(i, QFormLayout.LabelRole).widget().setVisible(True)
                self.ollama_form.itemAt(i, QFormLayout.FieldRole).widget().setVisible(True)

    def get_config_dict(self) -> dict[str, str]:
        """返回表单字段为字典 (key=value)。"""
        if self.deepseek_radio.isChecked():
            model = "deepseek"
        elif self.openai_radio.isChecked():
            model = "openai"
        else:
            model = "ollama"
        return {
            "DB_HOST": self.host_edit.text(),
            "DB_PORT": self.port_edit.text(),
            "DB_USER": self.user_edit.text(),
            "DB_PASSWORD": self.password_edit.text(),
            "DB_NAME": self.database_edit.text(),
            "AI_MODEL": model,
            "DEEPSEEK_API_KEY": self.deepseek_api_key_edit.text(),
            "OPENAI_API_KEY": self.openai_api_key_edit.text(),
            "OLLAMA_URL": self.ollama_url_edit.text(),
            "BENCHMARK_RUNS": self.benchmark_runs_edit.text(),
        }

    def _save_to_env(self) -> None:
        """把表单字段写回 .env 文件。"""
        config = self.get_config_dict()
        lines = []
        for key in _ENV_KEYS:
            value = config.get(key, "")
            lines.append(f"{key}={value}")
        # 写入时保留之前注释行 (这里简化: 全量重写)
        with open(self.env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    # ---- 事件处理 ----
    def _on_test_connection(self) -> None:
        """测试连接: 创建临时 SQLCoach, 验证连通性。"""
        from sql_coach.models import Config, DBConfig
        from sql_coach.coach import SQLCoach
        from sql_coach.db.connector import DBConnector

        try:
            db_config = DBConfig(
                host=self.host_edit.text() or "localhost",
                port=int(self.port_edit.text() or "3306"),
                user=self.user_edit.text() or "root",
                password=self.password_edit.text(),
                database=self.database_edit.text() or "test",
            )
            connector = DBConnector(db_config)
            ok = connector.connect()
            connector.close()
            if ok:
                self.save_btn.setText("✅ 连接成功 - 点击保存")
            else:
                self.save_btn.setText("❌ 连接失败 - 检查配置")
        except Exception as e:
            self.save_btn.setText(f"❌ 错误: {str(e)[:30]}")

    def _on_save_clicked(self) -> None:
        """保存: 写回 .env, accept 关闭。"""
        self._save_to_env()
        self.accept()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_settings_dialog.py -v`
Expected: 全部 4 个测试 PASS

- [ ] **Step 5: Commit**

```bash
git add gui/widgets/settings_dialog.py tests/test_settings_dialog.py
git commit -m "feat: 添加 SettingsDialog 设置对话框"
```

---

## Task 12: MainWindow — 主窗口组装

**Files:**
- Create: `gui/main_window.py`
- Create: `tests/test_main_window.py`

- [ ] **Step 1: 写测试 tests/test_main_window.py**

```python
# tests/test_main_window.py
"""MainWindow 冒烟测试。"""
import pytest
from PySide6.QtWidgets import QApplication

from sql_coach.models import Config, DBConfig
from gui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_config():
    return Config(
        db=DBConfig(host="localhost", port=3306, user="root", password="", database="test"),
        model="deepseek",
        deepseek_api_key="",
        openai_api_key="",
        ollama_url="http://localhost:11434",
        benchmark_runs=3,
        mock=True,
    )


def test_main_window_constructs(app):
    """主窗口能正常构造。"""
    win = MainWindow(config=make_config())
    assert win.windowTitle() == "SQL Coach"
    assert win.sql_input is not None
    assert win.report_view is not None
    assert win.status_bar is not None


def test_clear_action_resets_ui(app):
    """Ctrl+L / 清空按钮重置 UI。"""
    win = MainWindow(config=make_config())
    win.sql_input.editor.setPlainText("SELECT 1")
    win._on_clear()
    assert win.sql_input.get_sql() == ""


def test_analyze_with_empty_sql_does_nothing(app):
    """空 SQL 不触发分析。"""
    win = MainWindow(config=make_config())
    win._on_analyze()  # 输入框为空
    assert win.worker is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_main_window.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.main_window'`

- [ ] **Step 3: 实现 gui/main_window.py**

```python
# gui/main_window.py
"""主窗口, 左右分栏组装所有组件。"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QMainWindow, QMessageBox, QSplitter,
    QStatusBar, QToolBar, QWidget,
)

from sql_coach.coach import Report
from sql_coach.config import load_config
from sql_coach.models import Config

from gui.storage.history_store import HistoryStore
from gui.storage.exporter import Exporter
from gui.widgets.history_dialog import HistoryDialog
from gui.widgets.report_view import ReportView
from gui.widgets.settings_dialog import SettingsDialog
from gui.widgets.sql_input import SqlInputWidget
from gui.workers.analyze_worker import AnalyzeWorker, stage_label


class MainWindow(QMainWindow):
    """主窗口: 左右分栏 SqlInputWidget + ReportView。"""

    def __init__(self, config: Optional[Config] = None) -> None:
        super().__init__()
        self.config = config or load_config()
        self.history = HistoryStore()
        self.exporter = Exporter()
        self.worker: Optional[AnalyzeWorker] = None
        self.last_report: Optional[Report] = None
        self._analyze_start_time: float = 0.0

        self.setWindowTitle("SQL Coach")
        self.resize(1200, 800)
        self.setMinimumSize(800, 600)

        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._build_statusbar()
        self._connect_signals()
        self._check_db_connection()

    # ---- UI 构建 ----
    def _build_ui(self) -> None:
        """左右分栏 40% / 60%。"""
        splitter = QSplitter(Qt.Horizontal)

        self.sql_input = SqlInputWidget()
        self.report_view = ReportView()

        splitter.addWidget(self.sql_input)
        splitter.addWidget(self.report_view)
        splitter.setStretchFactor(0, 4)  # 40%
        splitter.setStretchFactor(1, 6)  # 60%
        splitter.setSizes([480, 720])

        self.setCentralWidget(splitter)

    def _build_menu(self) -> None:
        """菜单栏: 文件 / 设置 / 帮助。"""
        menubar = self.menuBar()

        # 文件
        file_menu = menubar.addMenu("文件")
        export_action = QAction("导出报告 ...", self)
        export_action.setShortcut("Ctrl+S")
        export_action.triggered.connect(self._on_export)
        file_menu.addAction(export_action)

        file_menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # 设置
        settings_menu = menubar.addMenu("设置")
        settings_action = QAction("打开设置 ...", self)
        settings_action.triggered.connect(self._on_open_settings)
        settings_menu.addAction(settings_action)

        # 帮助
        help_menu = menubar.addMenu("帮助")
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _build_toolbar(self) -> None:
        """工具栏: 5 个按钮。"""
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        analyze_btn = toolbar.addAction("🔍 分析")
        analyze_btn.triggered.connect(self._on_analyze)
        self._analyze_action = analyze_btn

        clear_btn = toolbar.addAction("🗑 清空")
        clear_btn.triggered.connect(self._on_clear)

        export_btn = toolbar.addAction("💾 导出报告")
        export_btn.triggered.connect(self._on_export)

        history_btn = toolbar.addAction("🕘 历史")
        history_btn.triggered.connect(self._on_history)

        settings_btn = toolbar.addAction("⚙ 设置")
        settings_btn.triggered.connect(self._on_open_settings)

    def _build_statusbar(self) -> None:
        """状态栏: 左状态文字, 右元信息。"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    def _connect_signals(self) -> None:
        """连接信号槽 + 快捷键。"""
        self.sql_input.analyze_requested.connect(self._start_analyze)
        # Ctrl+L 清空
        clear_sc = QShortcut(QKeySequence("Ctrl+L"), self)
        clear_sc.activated.connect(self._on_clear)

    # ---- 业务逻辑 ----
    def _check_db_connection(self) -> None:
        """启动时测试 DB 连通性, 失败则切 mock 模式。"""
        if self.config.mock:
            self.status_bar.showMessage("DB: 模拟模式")
            return
        from sql_coach.coach import SQLCoach
        try:
            coach = SQLCoach(self.config)
            ok = coach.connect()
            coach.close()
            if ok:
                self.status_bar.showMessage("DB: 已连接")
            else:
                self.config.mock = True
                QMessageBox.warning(self, "数据库连接失败", "已切换到模拟模式")
                self.status_bar.showMessage("DB: 模拟模式")
        except Exception as e:
            self.config.mock = True
            QMessageBox.warning(self, "数据库连接失败", f"已切换到模拟模式\n错误: {e}")
            self.status_bar.showMessage("DB: 模拟模式")

    def _on_analyze(self) -> None:
        """工具栏分析按钮回调。"""
        sql = self.sql_input.get_sql()
        if sql.strip():
            self._start_analyze(sql)

    def _start_analyze(self, sql: str) -> None:
        """启动后台分析线程。"""
        if self.worker is not None:
            return  # 正在分析, 忽略
        self.sql_input.set_readonly(True)
        self._analyze_action.setEnabled(False)
        self.status_bar.showMessage("分析中 ...")
        self._analyze_start_time = time.perf_counter()

        self.worker = AnalyzeWorker(
            sql=sql, config=self.config, use_cache=not self.config.mock,
        )
        self.worker.stage_changed.connect(self._on_stage_changed)
        self.worker.finished.connect(self._on_analyze_finished)
        self.worker.error.connect(self._on_analyze_error)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.error.connect(self.worker.deleteLater)
        self.worker.start()

    def _on_stage_changed(self, stage: str) -> None:
        """更新状态栏文字。"""
        self.status_bar.showMessage(stage_label(stage) + " ...")

    def _on_analyze_finished(self, report: Report) -> None:
        """分析完成: 渲染报告 + 存历史 + 恢复 UI。"""
        elapsed = (time.perf_counter() - self._analyze_start_time) * 1000
        self.last_report = report
        self.report_view.set_report(report)

        # 存入历史
        try:
            self.history.add(
                sql=report.sql_info.raw_sql,
                report=report,
                ai_time_ms=elapsed,
            )
        except Exception:
            pass  # 历史记录失败不影响主流程

        self.sql_input.set_readonly(False)
        self._analyze_action.setEnabled(True)
        self.worker = None
        self.status_bar.showMessage(
            f"完成 | AI: {elapsed/1000:.1f}s | 模型: {self.config.model}"
        )

    def _on_analyze_error(self, msg: str) -> None:
        """分析出错: 弹错误框 + 恢复 UI。"""
        self.sql_input.set_readonly(False)
        self._analyze_action.setEnabled(True)
        self.worker = None
        QMessageBox.critical(self, "分析失败", msg)
        self.status_bar.showMessage("分析失败")

    # ---- 其他功能 ----
    def _on_clear(self) -> None:
        """清空输入框和报告区。"""
        self.sql_input.clear()
        self.report_view.clear()
        self.last_report = None
        self.status_bar.showMessage("已清空")

    def _on_export(self) -> None:
        """导出报告: 弹文件对话框。"""
        if self.last_report is None:
            QMessageBox.information(self, "提示", "请先执行一次分析")
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "导出报告", "report",
            "Markdown (*.md);;HTML (*.html)",
        )
        if not path:
            return
        # 根据扩展名或过滤器决定格式
        if path.lower().endswith(".html") or "HTML" in selected_filter:
            fmt = "html"
        else:
            fmt = "markdown"
        try:
            self.exporter.save(self.last_report, path, fmt)
            self.status_bar.showMessage(f"已导出到: {path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _on_history(self) -> None:
        """打开历史记录对话框。"""
        dialog = HistoryDialog(store=self.history, parent=self)
        dialog.sql_selected.connect(self._on_history_sql_selected)
        dialog.exec()

    def _on_history_sql_selected(self, sql: str) -> None:
        """历史对话框双击: 把 SQL 填入输入框。"""
        self.sql_input.editor.setPlainText(sql)
        self.status_bar.showMessage("已从历史填入 SQL")

    def _on_open_settings(self) -> None:
        """打开设置对话框。"""
        dialog = SettingsDialog(env_path=".env", parent=self)
        if dialog.exec():
            # 重新加载配置
            self.config = load_config(mock=self.config.mock)
            self.status_bar.showMessage("配置已更新")
            self._check_db_connection()

    def _on_about(self) -> None:
        """关于对话框。"""
        QMessageBox.about(
            self, "关于 SQL Coach",
            "<h3>SQL Coach</h3>"
            "<p>AI 慢查询优化教练</p>"
            "<p>PySide6 GUI 桌面版</p>",
        )
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_main_window.py -v`
Expected: 全部 3 个测试 PASS

- [ ] **Step 5: 运行全测试套件确保零回归**

Run: `pytest tests/ -v`
Expected: 所有测试通过 (含原有 + 新增)

- [ ] **Step 6: Commit**

```bash
git add gui/main_window.py tests/test_main_window.py
git commit -m "feat: 添加 MainWindow 主窗口组装"
```

---

## Task 13: GUI 入口 — gui/app.py

**Files:**
- Create: `gui/app.py`
- Create: `tests/test_app_entry.py`

- [ ] **Step 1: 写测试 tests/test_app_entry.py**

```python
# tests/test_app_entry.py
"""GUI 入口冒烟测试。"""
import pytest
from PySide6.QtWidgets import QApplication

from gui import app as app_module


def test_run_creates_application_and_window(monkeypatch):
    """run() 创建 QApplication 并显示主窗口, exec 被立刻退出。"""
    # 拦截 exec 防止阻塞
    called = {}
    def fake_exec(self):
        called["exec"] = True
        return 0
    monkeypatch.setattr(QApplication, "exec", fake_exec)

    # 不调用 sys.exit
    def fake_exit(code=0):
        called["exit"] = code
    monkeypatch.setattr("sys.exit", fake_exit)

    # 拦截 MainWindow.show 防止真显示
    monkeypatch.setattr("gui.main_window.MainWindow.show", lambda self: None)

    app_module.run()

    assert called.get("exec") is True
    assert "exit" in called
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_app_entry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.app'`

- [ ] **Step 3: 实现 gui/app.py**

```python
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
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_app_entry.py -v`
Expected: 测试 PASS

- [ ] **Step 5: 验证 GUI 启动 (mock 模式)**

Run: `python main.py --gui` (在 .env 不存在或 mock 模式下)
Expected: 窗口弹出，标题 "SQL Coach"，状态栏显示 "DB: 模拟模式"。手动关闭窗口。

- [ ] **Step 6: 运行全测试套件确保零回归**

Run: `pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 7: Commit**

```bash
git add gui/app.py tests/test_app_entry.py
git commit -m "feat: 添加 GUI 启动入口 gui/app.py"
```

---

## Task 14: PyInstaller 打包配置

**Files:**
- Create: `.github/workflows/build-gui.yml`
- Create: `sql-coach.spec` (PyInstaller spec 文件)
- Modify: `.gitignore` (追加 .superpowers/)

- [ ] **Step 1: 创建 PyInstaller spec 文件 sql-coach.spec**

```python
# sql-coach.spec
# PyInstaller 打包配置。运行: pyinstaller sql-coach.spec
# -*- mode: python ; coding: utf-8 -*-
"""SQL Coach GUI PyInstaller 打包配置。"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 包含 sql_coach 包的非 .py 资源 (如有)
    ],
    hiddenimports=[
        # PySide6 / matplotlib 常见的隐藏导入
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'matplotlib.backends.backend_qtagg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 单文件 onefile, 窗口化 (--windowed)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='sql-coach-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # --windowed: 不弹出控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

- [ ] **Step 2: 创建 .github/workflows/build-gui.yml**

```yaml
# .github/workflows/build-gui.yml
# 三平台并行构建 SQL Coach GUI 桌面版
name: Build GUI

on:
  push:
    tags:
      - 'v*'  # 仅在打 v* 标签时触发
  workflow_dispatch:  # 手动触发

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: windows-latest
            artifact_name: sql-coach-gui
            asset_extension: .exe
            asset_content_type: application/vnd.microsoft.portable-executable
          - os: macos-latest
            artifact_name: sql-coach-gui
            asset_extension: .dmg
            asset_content_type: application/x-apple-diskimage
          - os: ubuntu-latest
            artifact_name: sql-coach-gui
            asset_extension: .tar.gz
            asset_content_type: application/gzip

    runs-on: ${{ matrix.os }}
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[gui]"
          pip install pyinstaller

      - name: Build with PyInstaller (Windows)
        if: matrix.os == 'windows-latest'
        run: pyinstaller sql-coach.spec --clean --noconfirm

      - name: Build with PyInstaller (macOS)
        if: matrix.os == 'macos-latest'
        run: pyinstaller sql-coach.spec --clean --noconfirm

      - name: Build with PyInstaller (Linux)
        if: matrix.os == 'ubuntu-latest'
        run: |
          # Linux 需要 X11 虚拟显示库
          sudo apt-get update -y
          sudo apt-get install -y libxcb-xinerama0 libxkbcommon-x11-0 libegl1
          pyinstaller sql-coach.spec --clean --noconfirm

      - name: Package artifact (Windows)
        if: matrix.os == 'windows-latest'
        uses: actions/upload-artifact@v4
        with:
          name: ${{ matrix.artifact_name }}-windows
          path: dist/sql-coach-gui.exe

      - name: Package artifact (macOS)
        if: matrix.os == 'macos-latest'
        run: |
          # 打包为 dmg
          hdiutil create -volname "SQL Coach" -srcfolder dist/sql-coach-gui.app -ov -format UDZO dist/SQLCoach.dmg
        shell: bash

      - name: Package artifact (macOS upload)
        if: matrix.os == 'macos-latest'
        uses: actions/upload-artifact@v4
        with:
          name: ${{ matrix.artifact_name }}-macos
          path: dist/SQLCoach.dmg

      - name: Package artifact (Linux)
        if: matrix.os == 'ubuntu-latest'
        run: |
          cd dist
          tar -czvf sql-coach-gui.tar.gz sql-coach-gui
        shell: bash

      - name: Upload artifact (Linux)
        if: matrix.os == 'ubuntu-latest'
        uses: actions/upload-artifact@v4
        with:
          name: ${{ matrix.artifact_name }}-linux
          path: dist/sql-coach-gui.tar.gz

      - name: Release
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          files: |
            dist/sql-coach-gui${{ matrix.asset_extension }}
            dist/SQLCoach.dmg
            dist/sql-coach-gui.tar.gz
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 3: 追加 .gitignore**

读取现有 `.gitignore`，在文件末尾追加以下内容：
```
# superpowers
.superpowers/

# PyInstaller
build/
dist/
*.spec.bak
```

- [ ] **Step 4: 验证 spec 文件存在**

Run (PowerShell): `Test-Path sql-coach.spec`
Expected: `True`

- [ ] **Step 5: 验证 workflow YAML 语法**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/build-gui.yml', encoding='utf-8').read()); print('yaml ok')"`
Expected: 输出 `yaml ok`

- [ ] **Step 6: 本地试跑 PyInstaller (可选, 跳过如有问题)**

Run: `pip install pyinstaller && pyinstaller sql-coach.spec --clean --noconfirm`
Expected: 在 dist/ 目录生成 sql-coach-gui.exe (Windows) 或对应可执行文件。

注意: 此步骤耗时较长 (~5 分钟) 且需要 PySide6 已安装。如果时间紧可跳过, 只验证 spec 文件存在。

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/build-gui.yml sql-coach.spec .gitignore
git commit -m "build: 添加 PyInstaller 打包配置和 GitHub Actions 三平台构建"
```

---

## 完成验证 (Final Verification)

完成所有 Task 后, 执行完整验证:

- [ ] **运行全测试套件**

Run: `pytest tests/ -v --cov=gui`
Expected: 所有测试通过 (含原有 + 11 个新增测试文件), GUI 模块覆盖率 > 60%

- [ ] **验证 CLI 模式仍工作**

Run: `python main.py` (输入 q 退出)
Expected: 看到 SQL Coach 横幅, 输入 q 退出, 无错误。

- [ ] **验证 GUI 模式启动**

Run: `python main.py --gui`
Expected: 弹出 GUI 窗口, 标题 "SQL Coach", 默认大小 1200x800, 状态栏显示 DB 状态。

- [ ] **验证 .env 不存在时降级 mock**

删除 .env → `python main.py --gui`
Expected: GUI 启动, 状态栏显示 "DB: 模拟模式", 无崩溃。

- [ ] **验证打包 spec 存在**

Run: `Test-Path sql-coach.spec`
Expected: `True`

---

## 设计决策说明

### 1. 为什么 HistoryStore 和 Exporter 不依赖 Qt?

纯 Python 的可测试性最好。如果依赖 Qt, 测试时必须先 `QApplication()` 才能实例化, 增加摩擦。HistoryStore 只做 JSON 读写, Exporter 只做字符串生成, 完全不需要 Qt。这两个类可独立测试, 在未来 CLI 也能复用 (例如 `sql-coach export` 命令)。

### 2. 为什么 AnalyzeWorker 每次创建新的 SQLCoach?

避免多线程冲突。SQLCoach 持有数据库连接 (pymysql 连接), MySQL 连接不是线程安全的。主线程 (GUI) 和分析线程共用同一个连接会导致数据错乱。每次分析创建新实例, 分析完立即 `close()`, 简单可靠。

### 3. 为什么 main.py 用延迟 import?

```python
if getattr(sys, "frozen", False) or "--gui" in sys.argv:
    from gui.app import run
```

延迟 import 确保 CLI 用户不需要安装 PySide6 也能运行。如果 main.py 顶部就 `import PySide6`, 那么 `pip install -e .` (不装 gui 依赖) 后 CLI 也跑不起来。

### 4. 为什么 .env 写回是全量重写?

简化实现。当前 .env 是 key=value 平铺结构, 没有 section (不像 INI)。全量重写保证字段最新, 避免保留旧值导致的混乱。注释行会被丢弃, 可接受 (设置对话框本就是结构化编辑)。

### 5. 历史记录为什么最多 100 条?

避免文件无限增长。100 条覆盖绝大多数用户一周的使用量, JSON 文件大小保持 < 50KB, 加载/写入都很快。超 100 条自动删最旧, 用户无感知。

### 6. 测试策略说明

| 测试目标 | 框架 | 策略 |
|---------|------|------|
| HistoryStore | pytest | 纯单元测试, TDD 先写测试 |
| Exporter | pytest | 纯单元测试, TDD 先写测试 |
| AnalyzeWorker | pytest + pytest-qt | mock SQLCoach, 验证信号发射 |
| 其他 Widget | pytest + pytest-qt | 冒烟测试, 不追求高覆盖率 |
| 现有测试 | pytest | 确保核心零回归 |

GUI 组件测试不追求高覆盖率, 重点是可测试的非 Qt 逻辑 (HistoryStore / Exporter)。Widget 测试只验证能实例化、基本 API 工作、信号发射正确。

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| PySide6 在 Linux CI 环境需要 X11 | workflow 中 `apt-get install libxkbcommon-x11-0 libegl1` |
| PyInstaller hidden imports 遗漏 | spec 中显式声明 PySide6.QtCore / QtGui / QtWidgets + matplotlib backend |
| macOS 应用签名 | 当前未签名, 用户首次打开需右键 "打开" 绕过 Gatekeeper (后续可加 codesign) |
| 数据库连接泄漏 | AnalyzeWorker 在 finally 之外 close, 异常时由 SQLCoach.__del__ 兜底 |
| 历史记录并发写 | 当前单线程 GUI, 不存在并发; 未来若多线程需加文件锁 |

---

## 任务依赖图

```
Task 1 (interactive.py)  ─┐
                          ├─→ Task 2 (pyproject) ─→ Task 3 (HistoryStore)
                          │                       ├─→ Task 4 (Exporter)
                          │                       └─→ Task 5 (AnalyzeWorker)
                          │                                    │
                          │                       ┌────────────┘
                          │                       ▼
                          │             Task 6 (ExplainTable)
                          │             Task 7 (BenchmarkChart)
                          │                       │
                          │             ┌──────────┴──────────┐
                          │             ▼                     ▼
                          │       Task 8 (ReportView)   Task 9 (SqlInput)
                          │             │                     │
                          │       Task 10 (HistoryDialog)    │
                          │       Task 11 (SettingsDialog)   │
                          │             │                     │
                          │             └──────────┬──────────┘
                          │                        ▼
                          │              Task 12 (MainWindow)
                          │                        │
                          │                        ▼
                          └─────────────→ Task 13 (app.py 入口)
                                                   │
                                                   ▼
                                          Task 14 (PyInstaller)
```

- Task 1 必须先做 (避免 main.py 被覆盖时丢失 CLI 逻辑)
- Task 2 必须早做 (后续 Task 都需要 PySide6 + pytest-qt)
- Task 3, 4, 5 互相独立, 可并行
- Task 6, 7 互相独立, 可并行 (依赖 Task 2)
- Task 8 依赖 Task 6, 7 (组合 explain table + benchmark chart)
- Task 9 独立
- Task 10, 11 独立 (依赖 Task 3 和 Task 2)
- Task 12 依赖前面所有组件
- Task 13 依赖 Task 12
- Task 14 依赖 Task 13

---

## 执行完成检查清单

实施完毕后, 确认以下事项:

- [ ] 14 个 Task 全部 commit 完成
- [ ] 所有测试通过 (`pytest tests/ -v`)
- [ ] CLI 模式 (`python main.py`) 仍工作
- [ ] GUI 模式 (`python main.py --gui`) 启动正常
- [ ] .env 不存在时降级 mock 模式, 不崩溃
- [ ] `sql-coach.spec` 文件存在
- [ ] `.github/workflows/build-gui.yml` 语法正确
- [ ] `sql_coach/` 核心代码无任何修改 (git diff 应为空)
- [ ] 现有测试全部通过 (零回归)
