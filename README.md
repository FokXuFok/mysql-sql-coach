# SQL Coach

> AI 驱动的 MySQL 慢查询优化教练 · 支持 CLI 与桌面 GUI

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/FokXuFok/mysql-sql-coach/actions/workflows/ci.yml/badge.svg)](https://github.com/FokXuFok/mysql-sql-coach/actions)
[![Release](https://img.shields.io/github/v/release/FokXuFok/mysql-sql-coach)](https://github.com/FokXuFok/mysql-sql-coach/releases)

SQL Coach 输入一条 SQL，自动连接 MySQL 执行 EXPLAIN，调用 AI 大模型分析执行计划，输出优化建议、改写后的 SQL、索引 DDL，并在数据库中实测性能对比，让你选择使用哪个版本的 SQL（自动复制到剪贴板）。

提供两种使用方式：
- **桌面 GUI**（推荐普通用户）：下载即用，无需安装 Python，图形化操作
- **命令行 CLI**（推荐开发者）：在 PyCharm / 终端运行，支持连续分析多条 SQL

## 特性

- 双模式入口：桌面 GUI（PySide6）+ 命令行 CLI（click + rich）
- 自动执行 EXPLAIN 并解析执行计划
- 多 AI 模型支持：DeepSeek / OpenAI / Ollama
- 实测优化前后性能对比，给出提速倍数（GUI 含横向柱状图）
- 交互式选择，一键复制 SQL 到剪贴板
- GUI 支持历史记录、Markdown / HTML 报告导出
- 内置 Docker 测试环境（10 万行测试数据）
- 无数据库时降级为 AI 推理模式（mock）
- 本地规则引擎：13 条规则，简单/中等 SQL 毫秒级优化，复杂 SQL 才调用 AI（自动分流）
- 索引实测模式：临时建索引 → 复测 → 自动回滚，基于选择性数据给出"建议采纳/不建议创建"结论
- 启动环境自检：自动检测 .env / MySQL / AI 配置，能安全修复的自动修复
- **自然语言转 SQL**：用中文描述需求（如"查询销售额最高的10个客户"）直接生成并执行 SQL，**纯本地算法、不调用 AI**
- 跨平台支持：Windows / macOS / Linux

## 快速开始

### 方式一：桌面 GUI（推荐普通用户）

从 [Releases](https://github.com/FokXuFok/mysql-sql-coach/releases) 下载对应平台的压缩包，解压后即可使用，无需安装 Python。

本地开发构建的 exe 位于项目根目录 `sql-coach-gui.exe`（仅 Windows，其他平台从 Release 下载）。

| 平台 | 下载文件 | 启动方式 |
|------|---------|---------|
| Windows | `sql-coach-gui-windows.zip` | 解压 → 双击 `sql-coach-gui.exe` |
| macOS | `sql-coach-gui-macos.tar.gz` | 解压 → 双击 `sql-coach-gui` |
| Linux | `sql-coach-gui-linux.tar.gz` | 解压 → 终端执行 `./sql-coach-gui` |

#### 使用前准备：配置 .env

压缩包内已附带 `.env.example` 模板（位于解压后文件夹的 `_internal/` 目录）。首次使用前：

1. 进入解压后的 `sql-coach-gui` 文件夹
2. 将 `_internal/.env.example` 复制到 `sql-coach-gui` 根目录（与可执行文件同级）
3. 重命名为 `.env`
4. 用文本编辑器打开 `.env`，填入你的 MySQL 连接信息和 AI API Key

```ini
# MySQL 连接
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=你的MySQL密码
DB_NAME=text

# AI 模型 (deepseek / openai / ollama / mock)
AI_MODEL=deepseek
DEEPSEEK_API_KEY=你的API key
```

配置完成后启动程序，窗口标题栏会显示 `DB: 已连接` 表示数据库连接成功。

> **注意**：`.env` 含敏感信息（密码、API Key），不会被打包进 Release，需要用户自行创建。这就是为什么下载后不能直接运行。

#### GUI 主要功能

- SQL 输入框支持多行编辑，回车键即可触发分析
- 分析报告区域展示 EXPLAIN 表格、AI 优化建议、索引 DDL、性能对比柱状图
- 历史记录对话框可查看之前的分析记录
- 一键导出 Markdown / HTML 报告
- 设置对话框可调整 AI 模型、数据库连接、性能对比次数、索引实测开关
- **模式切换**：工具栏最左侧可在「优化模式」与「自然语言模式」间切换

## 自然语言转 SQL

用中文描述你想查什么，工具会**在本地**解析并生成 SQL、执行查询、展示结果。
**全程不调用 AI 大模型**——基于 jieba 分词 + schema 词典 + 模板生成。

### GUI

工具栏模式下拉切到「自然语言模式」，在左侧输入描述，点「✨ 生成 SQL」：

```
查询销售额最高的10个客户
```
→ 生成并执行：
```sql
SELECT customer_name, SUM(amount) FROM customers GROUP BY customer_name
ORDER BY SUM(amount) DESC LIMIT 10;
```

右侧上方展示生成的 SQL（可复制、可一键「送入优化模式」继续分析），下方是查询结果表格。

### CLI

```bash
# 生成并执行
sql-coach nl2sql "查询销售额最高的10个客户"

# 只生成不执行
sql-coach nl2sql "统计每个城市的用户数量" --no-execute

# 模拟模式（不连数据库，仅演示生成）
sql-coach nl2sql "查询最近10条订单" --mock
```

### 支持的说法（示例）

| 自然语言 | 生成的 SQL |
|---------|-----------|
| 查询销售额最高的10个客户 | `SELECT customer_name, SUM(amount) FROM customers GROUP BY customer_name ORDER BY SUM(amount) DESC LIMIT 10;` |
| 查找status为pending的订单 | `SELECT * FROM orders WHERE status = 'pending';` |
| 统计每个城市的用户数量 | `SELECT city, COUNT(*) FROM users GROUP BY city;` |
| 查询最近10条订单 | `SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;` |
| 有多少条status为paid的订单 | `SELECT COUNT(*) AS cnt FROM orders WHERE status = 'paid';` |
| 查询用户的平均年龄 | `SELECT AVG(age) FROM users;` |

> **能力边界**：目前只支持**单表**查询（含 WHERE / GROUP BY / ORDER BY / LIMIT / 聚合）。
> 多表 JOIN 需要显式指定关联关系，属后续演进方向。
> 生成的表名/列名会与数据库真实 schema 校验，识别不出时给出警告而不是瞎猜。

### 方式二：命令行 CLI（推荐开发者）

#### 安装

```bash
git clone https://github.com/FokXuFok/mysql-sql-coach.git
cd mysql-sql-coach
pip install -e .
```

#### 配置

```bash
sql-coach config init
# 编辑 .env 文件，填入 API Key 和数据库连接信息
```

#### 使用

在 PyCharm 中打开项目，直接运行 `main.py`，进入交互式 CLI 模式，输入 SQL 即可分析，输入 `q` 退出。支持连续分析多条 SQL，无需重复启动。

也可使用命令行子命令：

```bash
# 分析单条 SQL
sql-coach analyze "SELECT * FROM orders WHERE status='pending'"

# 从文件读取
sql-coach analyze -f slow.sql

# 模拟模式（不需要数据库）
sql-coach analyze --mock "SELECT * FROM orders WHERE status='pending'"

# 指定 AI 模型
sql-coach analyze -m openai "SELECT * FROM orders"
```

## 示例输出

```
$ sql-coach analyze "SELECT * FROM orders WHERE status='pending'"

🔍 正在连接 MySQL  ✓
📊 执行 EXPLAIN    ✓
🤖 AI 分析中       ✓
⚡ 性能对比        ✓

📋 SQL 优化分析报告

📝 原始 SQL:
  SELECT * FROM orders WHERE status='pending'

📊 执行计划:
  ┌────┬────────┬──────┬───────┬──────────────┐
  │ id │ table  │ type │ rows  │ Extra        │
  ├────┼────────┼──────┼───────┼──────────────┤
  │ 1  │ orders │ ALL  │ 42万  │ Using where  │
  └────┴────────┴──────┴───────┴──────────────┘

⚠️ 发现 2 个问题:
  🔴 (critical) orders: full scan
      → add index on status

✅ 优化后 SQL:
  SELECT id FROM orders FORCE INDEX(idx_status) WHERE status='pending'

📊 性能对比:
  原始 SQL:   2.31s  (扫描 42万 行)
  优化 SQL:   0.04s  (扫描 200 行)
  提速:       57.8x 🚀

💡 你想使用哪个 SQL？
  [1] 原始 SQL
  [2] 优化后 SQL (推荐)
  [q] 退出
> 2

✅ 优化后 SQL 已复制到剪贴板！
```

## Docker 测试环境

```bash
cd docker
docker-compose up -d
```

内置测试数据：
- users: 10,000 行
- orders: 100,000 行（无 status 索引，方便测试）

## 开发

```bash
# 安装开发依赖 (含 GUI)
pip install -e ".[gui,dev]"

# 运行测试
pytest tests/ -v

# 运行覆盖率
pytest --cov=sql_coach --cov-report=html

# GUI 开发模式
python main.py --gui

# 打包 GUI (onefile, exe 输出到项目根目录)
pyinstaller sql-coach-onefile.spec --clean --noconfirm --distpath .

# 打包 GUI (onedir, 输出到项目根目录的 sql-coach-gui/ 文件夹)
pyinstaller sql-coach.spec --clean --noconfirm --distpath .
```

## 项目结构

```
sql-coach/
├── sql_coach/              # 核心库 (CLI + AI 分析 + 数据库)
│   ├── ai/                 # AI 引擎 (DeepSeek/OpenAI/Ollama/Mock + 工厂)
│   ├── db/                 # 数据库连接器 (MySQL + Mock)
│   ├── engine/             # SQL 解析 + EXPLAIN 结果解析
│   ├── local/              # 本地规则引擎 (13 条规则 + 复杂度评分 + schema 读取)
│   ├── nl/                 # 自然语言转 SQL (jieba 分词 + 意图/实体 + 模板生成)
│   ├── report/             # 性能对比 + 报告格式化
│   ├── diagnostics/        # 启动环境自检 (检查 + 修复 + 报告)
│   ├── models.py           # 数据模型 (dataclass)
│   ├── config.py           # 配置加载 (.env)
│   ├── coach.py            # 主编排服务
│   ├── optimizer.py        # 优化器分流 (auto/local/ai)
│   ├── index_experiment.py # 索引实测模式 (临时建索引 → 复测 → 回滚)
│   ├── sql_text.py         # SQL 文本清洗 (去注释/清字面量)
│   ├── cache.py            # AI 分析缓存 (SQLite)
│   ├── interactive.py      # CLI 交互模式 (python main.py 入口)
│   └── cli.py              # click 子命令入口
├── gui/                    # PySide6 桌面 GUI
│   ├── app.py              # GUI 启动入口
│   ├── main_window.py      # 主窗口
│   ├── paths.py            # .env 路径处理 (打包/开发双模式)
│   ├── widgets/            # 组件 (SQL 输入、EXPLAIN 表格、报告视图、图表、历史、设置、自检)
│   ├── workers/            # 后台线程 (分析 / NL 生成任务)
│   └── storage/            # 历史记录存储 + 报告导出
├── docs/                   # 文档
│   ├── api-reference.md    # API 参考文档
│   └── nl-to-sql-design.md # 自然语言转 SQL 设计文档
├── main.py                 # 入口: 打包走 GUI, 开发走 CLI
├── sql-coach-onefile.spec  # PyInstaller 打包配置 (onefile, exe 输出到根目录)
├── sql-coach.spec          # PyInstaller 打包配置 (onedir)
├── .github/workflows/      # CI: 三平台并行构建 Release
├── docker/                 # Docker 测试环境
└── tests/                  # 测试 (582 passed)
```

## 技术栈

- **GUI**: PySide6 (Qt6) + matplotlib
- **CLI**: click + rich
- **SQL 解析**: sqlparse
- **NL 分词**: jieba（自然语言转 SQL，惰性加载 + 无 jieba 降级）
- **数据库**: pymysql
- **AI**: openai SDK (兼容 DeepSeek/OpenAI) + httpx (Ollama)
- **打包**: PyInstaller (onefile + onedir 双模式, 三平台分发)
- **CI**: GitHub Actions (Windows / macOS / Linux 三平台并行构建)
- **测试**: pytest + pytest-mock + pytest-cov

## 优化分流

SQL Coach 会按 SQL 复杂度自动选择优化引擎：

- **简单 / 中等** → 本地规则引擎（毫秒级，不联网）
- **复杂** → AI 大模型

在 `.env` 中可通过两个配置项控制：

```ini
# 优化器分流: auto / local / ai
OPTIMIZER_MODE=auto
# 复杂度阈值（分数 >= 该值走 AI）
COMPLEXITY_THRESHOLD=8
```

- `OPTIMIZER_MODE=auto`（默认）：自动分流；`local`：始终本地；`ai`：始终调用 AI
- `COMPLEXITY_THRESHOLD` 默认 `8`：复杂度评分大于等于该值时走 AI

也可在命令行临时指定引擎：

```bash
sql-coach analyze --engine local "SELECT * FROM orders WHERE status='pending'"
```

## 索引实测模式（可选）

普通性能对比测的是「原始 SQL vs 改写后 SQL」，而索引类建议不改写 SQL，提速恒为 1.0x。
开启索引实测后，程序会**临时创建建议索引 → 复测同一 SQL → 自动回滚**，
基于真实选择性给出「建议采纳 / 不建议创建」结论（实测提速 < 1.3x 判为不建议）。

在 `.env` 中开启（默认关闭）：

```ini
# 是否实测索引收益（会临时建索引→复测→回滚，请谨慎开启）
MEASURE_INDEX=true
```

GUI 也可在「设置」对话框中随时开关；CLI 可用 `--measure-index` 临时开启。

> **注意**：该模式会对数据库执行 DDL（建索引/删索引），需要相应权限，
> 请勿在无法建索引或不愿承担 DDL 风险的生产库上开启。

## License

MIT
