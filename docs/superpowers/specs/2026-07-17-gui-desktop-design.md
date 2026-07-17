# SQL Coach 桌面 GUI 设计文档

> 日期: 2026-07-17
> 状态: 已批准，待实施

## 1. 概述

为 SQL Coach 添加 PySide6 桌面 GUI，作为 exe 打包后的默认界面。保留现有 CLI 作为 PyCharm 开发模式。

### 目标

- 双击 exe → 弹出 GUI 窗口，像正常软件一样使用
- PyCharm 里 `python main.py` → CLI 交互模式（终端输入输出，不弹窗口）
- PyCharm 里 `python main.py --gui` → 强制启动 GUI（调试用）
- 全平台支持（Windows / macOS / Linux）+ PyInstaller 打包
- 上传 GitHub，别人 clone 后 `pip install -e ".[gui]"` 即可运行

### 非目标

- 不做 SQL 语法高亮（普通 QPlainTextEdit）
- 不做 AI 流式输出显示（等完成后一次性渲染）
- 不做 SaaS / 多用户 / 权限系统
- 不修改 `sql_coach/` 核心代码

## 2. 入口设计

`main.py` 智能入口，检测运行环境选择模式：

```python
import sys

def main():
    if getattr(sys, 'frozen', False) or '--gui' in sys.argv:
        # PyInstaller 打包环境 或 显式指定 --gui
        from gui.app import run
        run()
    else:
        # PyCharm / 终端 → CLI 交互模式
        from sql_coach.interactive import run_cli
        run_cli()
```

- `sys.frozen` 是 PyInstaller 打包后才有的属性
- CLI 逻辑从现有 `main.py` 提取到 `sql_coach/interactive.py`，保持行为不变
- `main.py` 只做模式分发，不含业务逻辑

## 3. 架构

### 3.1 模块依赖关系

```
main.py (智能入口)
    │
    ├── sys.frozen 或 --gui → gui/app.py (GUI 模式)
    │                            │
    │                            ▼
    │                       gui/main_window.py (主窗口, 左右分栏)
    │                            ├── gui/widgets/sql_input.py
    │                            ├── gui/widgets/report_view.py
    │                            │     ├── gui/widgets/explain_table.py
    │                            │     └── gui/widgets/benchmark_chart.py
    │                            ├── gui/widgets/history_dialog.py
    │                            ├── gui/widgets/settings_dialog.py
    │                            ├── gui/workers/analyze_worker.py
    │                            └── gui/storage/
    │                                  ├── history_store.py
    │                                  └── exporter.py
    │
    └── 否则 → sql_coach/interactive.py (CLI 模式)
```

### 3.2 设计原则

1. **薄 GUI 层**：GUI 不含业务逻辑，所有分析通过 `SQLCoach.analyze()` 完成
2. **核心零改动**：`sql_coach/` 目录不修改，GUI 只 import `SQLCoach`、`Config`、`load_config` 和数据模型
3. **线程隔离**：`AnalyzeWorker(QThread)` 后台执行分析，主线程永不阻塞
4. **可测试逻辑独立**：`HistoryStore` 和 `Exporter` 不依赖 Qt，纯 Python，可单元测试

## 4. 主窗口布局

```
┌──────────────────────────────────────────────────────────┐
│ 文件  设置  帮助                              [_][□][X]  │ ← QMenuBar
├──────────────────────────────────────────────────────────┤
│ [🔍 分析]  [🗑 清空]  [💾 导出报告]  [🕘 历史]  [⚙ 设置] │ ← QToolBar
├────────────────────┬─────────────────────────────────────┤
│                    │                                     │
│  SQL 输入区        │  报告展示区                          │
│  (QPlainTextEdit)  │  (QScrollArea, 垂直滚动)             │
│  等宽字体, Tab=4    │                                     │
│                    │  ┌─ 📋 执行计划 ──────────────┐     │
│  右键菜单:          │  │ QTableWidget               │     │
│    粘贴/清空/导入   │  │ id|table|type|key|rows|extra│     │
│                    │  └────────────────────────────┘     │
│                    │                                     │
│                    │  ┌─ ⚠️ 发现问题 ───────────────┐     │
│                    │  │ 🔴 critical: 全表扫描       │     │
│                    │  │    → 在Cname列创建索引       │     │
│                    │  └────────────────────────────┘     │
│                    │                                     │
│                    │  ┌─ ✅ 优化后 SQL ─────[📋复制]┐    │
│                    │  │ SELECT * FROM commodity      │    │
│                    │  │ WHERE Cname='牛奶';          │    │
│                    │  └──────────────────────────────┘    │
│                    │                                     │
│                    │  ┌─ 📌 索引建议 ─────[📋复制]──┐    │
│                    │  │ CREATE INDEX idx_cname ...   │    │
│                    │  └──────────────────────────────┘    │
│                    │                                     │
│                    │  ┌─ 📊 性能对比 ───────────────┐    │
│                    │  │ 原始SQL ████████ 8.2ms       │    │
│                    │  │ 优化SQL █ 0.3ms              │    │
│                    │  │ 提速: 27x 🚀                 │    │
│                    │  └──────────────────────────────┘    │
│                    │                                     │
│  [🔍 分析]         │                                     │
│  (底部靠右)        │                                     │
├────────────────────┴─────────────────────────────────────┤
│ 就绪 | AI: 8.2s | 缓存: 命中 | DB: 已连接 | 模型: DeepSeek│ ← QStatusBar
└──────────────────────────────────────────────────────────┘
```

### 组件规格

| 组件 | Qt 类 | 说明 |
|------|-------|------|
| 菜单栏 | QMenuBar | 文件(导出/退出)、设置(打开设置对话框)、帮助(关于) |
| 工具栏 | QToolBar | 分析、清空、导出、历史、设置 5 个按钮 |
| SQL 输入 | QPlainTextEdit | 左侧 40% 宽，等宽字体，底部放分析按钮 |
| 报告区 | QScrollArea | 右侧 60% 宽，垂直滚动，内容动态生成 |
| 状态栏 | QStatusBar | 左：状态文字；右：AI耗时/缓存状态/DB连接/模型名 |

### 窗口属性

- 默认大小: 1200x800
- 最小大小: 800x600
- 窗口标题: "SQL Coach"

### 交互行为

1. **分析流程**: 输入 SQL → 点"分析"按钮或 Ctrl+Enter → 输入框变只读 + 按钮变灰 → 状态栏显示阶段 → 完成后渲染报告 → 恢复可编辑
2. **清空**: 清空输入框和报告区
3. **历史**: 弹出 QDialog，列表展示，双击填入输入框，可删除选中记录
4. **设置**: 弹出 QDialog，编辑 .env 配置
5. **导出**: QFileDialog 选路径和格式，保存报告

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+Enter | 触发分析 |
| Ctrl+S | 导出报告 |
| Ctrl+L | 清空输入和报告 |

## 5. 后台线程与信号槽

```python
class AnalyzeWorker(QThread):
    """后台分析线程，防止界面卡死。"""
    finished = Signal(Report)      # 分析完成，传回 Report
    error = Signal(str)            # 出错，传错误信息
    stage_changed = Signal(str)    # 阶段变化: "parse"/"explain"/"ai"/"benchmark"

    def __init__(self, sql: str, config: Config, use_cache: bool):
        super().__init__()
        self.sql = sql
        self.config = config
        self.use_cache = use_cache

    def run(self):
        try:
            coach = SQLCoach(self.config, use_cache=self.use_cache)
            coach.connect()

            def on_stage(stage, step, total, status):
                if status == "start":
                    self.stage_changed.emit(stage)

            report = coach.analyze(self.sql, on_stage=on_stage)
            coach.close()
            self.finished.emit(report)
        except Exception as e:
            self.error.emit(str(e))
```

### 信号响应

| 信号 | 主窗口响应 |
|------|-----------|
| `stage_changed` | 状态栏更新文字: "正在解析SQL" / "正在执行EXPLAIN" / "AI分析中" / "性能对比中" |
| `finished` | 渲染报告 + 恢复按钮 + 存入历史记录 |
| `error` | 弹 QMessageBox.critical + 恢复按钮 |

### 数据库连接生命周期

每次分析创建新的 `SQLCoach` 实例，分析完 `close()`。不在主窗口持有长期连接，避免多线程冲突。

## 6. 历史记录存储

### 文件位置

`~/.sql-coach/history.json`

### JSON 结构

```json
[
  {
    "id": "a1b2c3",
    "sql": "SELECT * FROM commodity WHERE Cname='牛奶'",
    "timestamp": "2026-07-13T14:30:00",
    "optimized_sql": "SELECT * FROM commodity WHERE Cname = '牛奶';",
    "speedup": 27.3,
    "ai_time_ms": 8200,
    "problem_count": 1
  }
]
```

### HistoryStore 类

```python
class HistoryStore:
    """历史记录 JSON 存储，不依赖 Qt。"""
    def __init__(self, path=None): ...
    def add(self, sql: str, report: Report, ai_time_ms: float) -> str:  # 返回 id
    def list(self) -> list[dict]:                    # 按时间倒序
    def delete(self, record_id: str) -> bool:        # 删除单条
    def clear(self) -> int:                           # 清空全部
    def get(self, record_id: str) -> dict | None:    # 取单条
```

### 设计要点

- `id` 用 6 位随机 hex（`secrets.token_hex(3)`）
- 只存摘要信息，不含完整 Report 对象
- 最多保留 100 条，超出自动删最旧的
- 文件不存在或格式损坏时返回空列表，不崩溃

### 历史面板交互

- 列表项格式: `[2026-07-13 14:30] SELECT * FROM commodity... (提速 27x)`
- 双击: 把 SQL 填入输入框，关闭对话框
- 选中 + 删除按钮: 删除该条
- 底部"清空全部"按钮: 清空所有历史

## 7. 设置对话框

```
┌─ 设置 ──────────────────────────────┐
│                                     │
│  ── MySQL 连接 ──                   │
│  Host:    [localhost          ]     │
│  Port:    [3306               ]     │
│  User:    [root               ]     │
│  Password:[********            ]    │
│  Database:[test               ]     │
│  [测试连接]                         │
│                                     │
│  ── AI 模型 ──                      │
│  模型: ( )DeepSeek ( )OpenAI ( )Ollama│
│                                     │
│  (选中模型的配置项动态显示)            │
│                                     │
│  ── 通用 ──                         │
│  Benchmark次数: [3            ]      │
│                                     │
│  [保存到.env]  [取消]               │
└─────────────────────────────────────┘
```

### 行为

- 启动时读取当前 `.env` 填充表单
- "测试连接"按钮实时验证数据库连通性
- 保存时写回 `.env` 文件
- 模型单选切换时，动态显示对应模型的配置项（DeepSeek 显示 API Key/Base URL/Model；OpenAI 显示 API Key/Base URL；Ollama 显示 URL/Model）

## 8. 导出功能

### 支持格式

1. **Markdown** (.md) — 纯文本，含表格，适合贴 GitHub Issue / Wiki
2. **HTML** (.html) — 带内联 CSS 的独立文件，图表用 base64 PNG 嵌入

### 导出内容

- 原始 SQL
- 执行计划表格
- 问题列表（severity + 描述 + 建议）
- 优化后 SQL
- 索引 DDL
- 性能对比数据 + 图表（HTML 格式含图片，Markdown 格式含文字描述）

### Exporter 类

```python
class Exporter:
    """报告导出，不依赖 Qt。"""
    def to_markdown(self, report: Report) -> str: ...
    def to_html(self, report: Report) -> str: ...
    def save(self, report: Report, path: str, fmt: str) -> None: ...
```

### 导出对话框

- `QFileDialog.getSaveFileName`，过滤器: `Markdown (*.md);;HTML (*.html)`
- 根据扩展名自动判断格式
- 导出完成后状态栏提示路径

## 9. 性能对比图表

### 展示方式

水平柱状图，红绿对比:

```
原始 SQL  ████████████████████ 8.20 ms
优化 SQL  █ 0.30 ms
提速: 27.3x 🚀
```

### 实现

- 用 `matplotlib.backends.backend_qtagg.FigureCanvasQTAgg` 嵌入 Qt
- 两根水平柱子（`barh`），原始 SQL 红色 (#f38ba8)，优化 SQL 绿色 (#a6e3a1)
- 柱子右侧标注耗时数值
- 底部显示提速倍数
- 无 benchmark 数据时（mock 模式或无优化 SQL）显示"无性能对比数据"

## 10. 打包策略

### PyInstaller

```bash
# Windows
pyinstaller --name sql-coach-gui --windowed --onefile main.py

# macOS
pyinstaller --name "SQL Coach" --windowed --osx-bundle-identifier com.fokxufok.sqlcoach main.py

# Linux
pyinstaller --name sql-coach-gui --onefile main.py
```

### GitHub Actions 自动构建

`.github/workflows/build-gui.yml`，三平台并行 build:

| 平台 | runner | 产物 | 格式 |
|------|--------|------|------|
| Windows | windows-latest | sql-coach-gui.exe | .exe |
| macOS | macos-latest | SQL Coach.app | .dmg |
| Linux | ubuntu-latest | sql-coach-gui | .tar.gz |

Release 页面自动上传三平台产物。

### 依赖增量

| 新增依赖 | 用途 | 体积影响 |
|----------|------|----------|
| PySide6>=6.5 | GUI 框架 | ~60MB |
| matplotlib>=3.7 | 图表 | ~20MB |
| 总打包体积 | — | ~80MB |

`pyproject.toml` 新增 `gui` optional-dependencies:

```toml
[project.optional-dependencies]
gui = ["PySide6>=6.5", "matplotlib>=3.7"]
```

安装方式: `pip install -e ".[gui]"`

## 11. 测试策略

| 测试目标 | 框架 | 范围 |
|----------|------|------|
| HistoryStore | pytest | add/list/delete/clear/get，含边界情况（空文件、超100条、损坏文件） |
| Exporter | pytest | Markdown 和 HTML 输出格式校验 |
| AnalyzeWorker | pytest + pytest-qt | 信号发射正确性（mock SQLCoach） |
| 现有 82 个测试 | pytest | 确保核心零回归 |

GUI 组件测试用 `pytest-qt`，不追求高覆盖率，重点是可测试的非 Qt 逻辑。

新增 dev 依赖: `pytest-qt>=4.0`

## 12. 启动行为

1. 启动时读取 `.env`，创建临时 `SQLCoach` 实例测试数据库连通性，测试完立即 `close()`
2. 连接成功 → 状态栏显示"DB: 已连接"，后续分析时再创建新连接
3. 连接失败 → 弹提示框"数据库连接失败，已切换到模拟模式"，状态栏显示"DB: 模拟模式"
4. 不退出应用，用户仍可在设置对话框修改配置后重试

注意：启动时只做连通性测试，不持有持久连接。每次分析都创建新的 `SQLCoach` 实例（见第 5 节）。

## 13. 文件结构

### 新增文件

```
sql-coach/
├── gui/
│   ├── __init__.py
│   ├── app.py                    # QApplication 启动
│   ├── main_window.py            # 主窗口 (左右分栏)
│   ├── workers/
│   │   ├── __init__.py
│   │   └── analyze_worker.py     # QThread 后台分析
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── sql_input.py          # SQL 输入区
│   │   ├── report_view.py        # 报告容器 (QScrollArea)
│   │   ├── explain_table.py      # EXPLAIN 表格
│   │   ├── benchmark_chart.py    # matplotlib 柱状图
│   │   ├── history_dialog.py     # 历史记录对话框
│   │   └── settings_dialog.py    # 设置对话框
│   └── storage/
│       ├── __init__.py
│       ├── history_store.py      # JSON 历史存储
│       └── exporter.py           # 报告导出 (md/html)
├── sql_coach/
│   └── interactive.py            # CLI 交互模式 (从 main.py 提取)
├── tests/
│   ├── test_history_store.py
│   ├── test_exporter.py
│   └── test_analyze_worker.py
├── main.py                       # 智能入口 (修改)
├── .github/workflows/build-gui.yml
└── pyproject.toml                # 新增 gui optional-dependencies
```

### 修改的现有文件

| 文件 | 改动 |
|------|------|
| `main.py` | 改为智能入口，分发 CLI / GUI |
| `pyproject.toml` | 新增 `[project.optional-dependencies].gui` 和 dev 的 `pytest-qt` |
| `.gitignore` | 追加 `.superpowers/` |

## 14. 不改动清单

以下文件/目录**不做任何修改**:

- `sql_coach/coach.py`
- `sql_coach/models.py`
- `sql_coach/config.py`
- `sql_coach/cache.py`
- `sql_coach/cli.py`
- `sql_coach/ai/*`
- `sql_coach/db/*`
- `sql_coach/engine/*`
- `sql_coach/report/*`
- `tests/` 下现有测试文件
