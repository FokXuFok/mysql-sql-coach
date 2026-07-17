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

- 自动执行 EXPLAIN 并解析执行计划
- 多 AI 模型支持：DeepSeek / OpenAI / Ollama
- 实测优化前后性能对比，给出提速倍数（GUI 含横向柱状图）
- 交互式选择，一键复制 SQL 到剪贴板
- GUI 支持历史记录、Markdown / HTML 报告导出
- 内置 Docker 测试环境
- 无数据库时降级为 AI 推理模式（mock）

## 快速开始

### 方式一：桌面 GUI（推荐普通用户）

从 [Releases](https://github.com/FokXuFok/mysql-sql-coach/releases) 下载对应平台的压缩包，解压后即可使用，无需安装 Python。

**Windows**：下载 `sql-coach-gui-windows.zip` → 解压 → 配置 `.env` → 双击 `sql-coach-gui.exe`

#### 使用前准备：配置 .env

压缩包内已附带 `.env.example` 模板（位于解压后文件夹的 `_internal/` 目录）。首次使用前：

1. 进入解压后的 `sql-coach-gui` 文件夹
2. 将 `_internal\.env.example` 复制到 `sql-coach-gui` 根目录（与 `sql-coach-gui.exe` 同级）
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

配置完成后双击 `sql-coach-gui.exe` 启动，窗口标题栏会显示 `DB: 已连接` 表示数据库连接成功。

> **注意**：`.env` 含敏感信息（密码、API Key），不会被打包进 Release，需要用户自行创建。这就是为什么下载后不能直接运行。

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

# 打包 GUI (需要 pyinstaller)
pyinstaller sql-coach.spec --clean --noconfirm
```

## 项目结构

```
sql-coach/
├── sql_coach/          # 核心库 (CLI + AI 分析 + 数据库)
├── gui/                # PySide6 桌面 GUI
│   ├── app.py          # GUI 入口
│   ├── main_window.py  # 主窗口
│   ├── widgets/        # 组件 (报告视图、图表、历史)
│   ├── workers/        # 后台线程 (分析任务)
│   ├── storage/        # 历史记录存储
│   └── paths.py        # .env 路径处理 (打包/开发双模式)
├── main.py             # 入口: 打包走 GUI, 开发走 CLI
├── sql-coach.spec      # PyInstaller 打包配置 (onedir)
├── .github/workflows/  # CI: 三平台并行构建 Release
└── tests/              # 测试
```

## 技术栈

- **GUI**: PySide6 (Qt6) + matplotlib
- **CLI**: click + rich
- **SQL 解析**: sqlparse
- **数据库**: pymysql
- **AI**: openai SDK (兼容 DeepSeek/OpenAI) + httpx (Ollama)
- **打包**: PyInstaller (onedir 模式)
- **CI**: GitHub Actions (Windows / macOS / Linux 三平台)
- **测试**: pytest + pytest-mock + pytest-cov

## License

MIT
