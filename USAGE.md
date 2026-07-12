# SQL Coach 使用说明

> AI 驱动的 MySQL 慢查询优化教练

输入一条 SQL，自动连接 MySQL 执行 EXPLAIN，调用 AI 分析执行计划，输出优化建议、改写后的 SQL、索引 DDL，并在数据库中实测性能对比，最后让你选择使用哪个版本的 SQL（自动复制到剪贴板）。

---

## 目录

1. [安装](#1-安装)
2. [配置](#2-配置)
3. [快速开始](#3-快速开始)
4. [命令参考](#4-命令参考)
5. [三种使用模式](#5-三种使用模式)
6. [完整示例](#6-完整示例)
7. [Docker 测试环境](#7-docker-测试环境)
8. [支持的 AI 模型](#8-支持的-ai-模型)
9. [常见问题](#9-常见问题)
10. [开发者指南](#10-开发者指南)

---

## 1. 安装

### 从源码安装（开发模式）

```bash
cd sql-coach
pip install -e .
```

安装后 `sql-coach` 命令全局可用。

### 验证安装

```bash
sql-coach --version
# 输出: sql-coach, version 0.1.0
```

### 依赖说明

| 依赖 | 用途 |
|------|------|
| click | 命令行框架 |
| rich | 美化终端输出 |
| sqlparse | SQL 解析 |
| pymysql | MySQL 连接 |
| openai | AI API 调用（兼容 DeepSeek/阿里百炼） |
| httpx | Ollama 本地 API |
| python-dotenv | .env 配置加载 |
| pyperclip | 剪贴板操作 |

---

## 2. 配置

### 2.1 初始化配置文件

```bash
sql-coach config init
```

会在当前目录生成 `.env` 文件，包含所有配置项。

### 2.2 编辑 .env

```ini
# ===== MySQL 连接 =====
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=your_database

# ===== AI 模型选择 =====
# 可选: deepseek / openai / ollama
AI_MODEL=deepseek

# ===== DeepSeek 配置 =====
# 官方 API:
#   DEEPSEEK_BASE_URL=https://api.deepseek.com
#   DEEPSEEK_MODEL=deepseek-chat
# 阿里百炼兼容模式:
#   DEEPSEEK_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
#   DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# ===== OpenAI 配置 =====
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1

# ===== Ollama 配置（本地部署，无需 API Key） =====
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b

# ===== 通用 =====
BENCHMARK_RUNS=3      # 性能对比的执行次数（取平均）
LOG_LEVEL=INFO
```

### 2.3 测试配置

```bash
sql-coach config test
```

会检测数据库连接是否正常。

---

## 3. 快速开始

### 最简用法

```bash
sql-coach analyze "SELECT * FROM users WHERE age > 18"
```

流程：
1. 连接 MySQL
2. 执行 EXPLAIN 获取执行计划
3. 调用 AI 分析问题
4. 实测优化前后性能对比
5. 让你选 1（原始）或 2（优化后）
6. 选中的 SQL 自动复制到剪贴板

---

## 4. 命令参考

### 4.1 analyze - 分析 SQL

```bash
sql-coach analyze [SQL] [选项]
```

| 参数/选项 | 说明 |
|-----------|------|
| `SQL` | 要分析的 SQL 语句（字符串） |
| `-f, --file FILE` | 从文件读取 SQL（适合长 SQL） |
| `-m, --model MODEL` | 临时指定 AI 模型：deepseek/openai/ollama |
| `--mock` | 模拟模式（不需要数据库和 API Key） |

**示例：**

```bash
# 直接传 SQL
sql-coach analyze "SELECT * FROM orders WHERE status='pending'"

# 从文件读取
sql-coach analyze -f slow_query.sql

# 指定模型
sql-coach analyze -m openai "SELECT * FROM users"

# 模拟模式（测试用）
sql-coach analyze --mock "SELECT * FROM users WHERE id=1"
```

### 4.2 config - 配置管理

```bash
# 生成 .env 配置文件
sql-coach config init

# 测试数据库和 AI 连通性
sql-coach config test
```

### 4.3 全局选项

```bash
sql-coach --version    # 查看版本
sql-coach --help       # 查看帮助
```

---

## 4.4 方式二: 交互式入口 (main.py)

适合在 PyCharm / VS Code 等 IDE 中运行, 支持连续分析多条 SQL。

### 启动

```bash
python main.py
```

### 交互流程

```
╔══════════════════════════════════════════╗
║   SQL Coach - AI 慢查询优化教练          ║
╚══════════════════════════════════════════╝
输入 SQL 进行分析, 输入 q 退出

> 输入 SQL (或 q 退出): SELECT * FROM commodity WHERE Cname='牛奶'
分析中: SELECT * FROM commodity WHERE Cname='牛奶';
... (完整报告输出)

摘要
  优化后 SQL: SELECT * FROM commodity WHERE Cname='牛奶'
  索引建议: CREATE INDEX idx_commodity_Cname ON commodity(Cname);
  提速: 1.6x

> 输入 SQL (或 q 退出): SELECT * FROM orders WHERE status='pending'
... (继续分析下一条)

> 输入 SQL (或 q 退出): q
已退出 SQL Coach, 再见
```

### 特点

- **循环分析**: 不用重复启动, 一条接一条分析
- **输入 q 退出**: 输入 `q` / `quit` / `exit` 任一即可退出
- **自动补分号**: SQL 末尾没分号会自动补上
- **错误隔离**: 单条 SQL 分析失败不会退出, 可继续输入下一条
- **降级模式**: 数据库连不上时自动切换到模拟模式

### PyCharm 配置

1. File → Open → 选择 `sql-coach` 目录
2. 配置 Python 解释器 (已装 sql-coach 的 Python 3.10+)
3. 打开 `main.py`, 右键 → Run 'main' (或按 Shift+F10)
4. 在运行控制台输入 SQL 即可

---

## 5. 三种使用模式

### 模式 A：真实模式（完整功能）

需要 MySQL + AI API Key。

```bash
sql-coach analyze "SELECT * FROM orders WHERE status='pending'"
```

- 执行真实 EXPLAIN
- AI 真实分析
- 真实性能对比

### 模式 B：模拟模式（无需配置）

不需要数据库、不需要 API Key。

```bash
sql-coach analyze --mock "SELECT * FROM orders WHERE status='pending'"
```

- 跳过数据库连接
- 使用 MockAIEngine 生成示例分析
- 不执行性能对比
- 适合验证安装、看输出效果

### 模式 C：降级模式（无数据库自动降级）

填了 API Key 但没有 MySQL，会自动降级：

```bash
sql-coach analyze "SELECT * FROM orders WHERE status='pending'"
# 输出: ✗ 数据库连接失败，切换到模拟模式
```

- AI 仍会基于 SQL 结构分析
- 但无法执行 EXPLAIN 和性能对比

---

## 6. 完整示例

### 6.1 基础示例

```bash
$ sql-coach analyze "SELECT * FROM commodity WHERE Cname='牛奶'"

🔍 正在连接 MySQL... ✓
📊 执行 EXPLAIN... ✓
🤖 AI 分析中... ✓

📋 SQL 优化分析报告

📝 原始 SQL:
  SELECT * FROM commodity WHERE Cname='牛奶'

📊 执行计划:
  ┌────┬───────────┬──────┬──────┬──────┬─────────────┐
  │ id │ table     │ type │ key  │ rows │ Extra       │
  │ 1  │ commodity │ ALL  │ NULL │ 8    │ Using where │
  └────┴───────────┴──────┴──────┴──────┴─────────────┘

⚠️ 发现 1 个问题:
  🔴 (critical) commodity: 全表扫描，未使用索引
      → 在 Cname 列上创建索引

✅ 优化后 SQL:
  SELECT * FROM commodity WHERE Cname = '牛奶';

📌 索引建议:
  CREATE INDEX idx_commodity_cname ON commodity (Cname);

🤖 AI 解释:
  EXPLAIN 显示 type=ALL，建议在 Cname 列创建索引。

📊 性能对比:
  原始 SQL:   0.000s  (扫描 8 行)
  优化 SQL:   0.000s  (扫描 8 行)
  提速: 1.4x 🚀

💡 你想使用哪个 SQL？
  [1] 原始 SQL
  [2] 优化后 SQL (推荐)
  [q] 退出
> 2
✅ 优化后 SQL 已复制到剪贴板！
```

### 6.2 从文件读取长 SQL

```bash
# 把复杂 SQL 写入文件
echo "SELECT u.name, COUNT(o.id) as order_count
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
WHERE u.status = 'active'
GROUP BY u.id
ORDER BY order_count DESC;" > slow.sql

# 分析
sql-coach analyze -f slow.sql
```

### 6.3 交互式选择

分析完成后，工具会让你选择：

```
💡 你想使用哪个 SQL？
  [1] 原始 SQL
  [2] 优化后 SQL (推荐)
  [q] 退出
> 
```

| 输入 | 行为 |
|------|------|
| `1` | 复制原始 SQL 到剪贴板 |
| `2` | 复制优化后 SQL 到剪贴板（默认推荐） |
| `q` | 退出，不复制 |
| 其他 | 提示"无效选择，请输入 1、2 或 q" |

直接按回车默认选 `2`（优化后 SQL）。

---

## 7. Docker 测试环境

项目自带一个测试用 MySQL，内置 10 万行数据，方便测试性能优化效果。

### 7.1 启动

```bash
cd docker
docker-compose up -d
```

### 7.2 连接信息

| 项 | 值 |
|----|----|
| Host | localhost |
| Port | 3306 |
| User | root |
| Password | test123 |
| Database | test |

### 7.3 测试数据

| 表 | 行数 | 说明 |
|----|------|------|
| users | 10,000 | 用户表 |
| orders | 100,000 | 订单表（status 列故意没建索引，方便测试） |
| products | 1,000 | 商品表 |

### 7.4 修改 .env 使用 Docker 数据库

```ini
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=test123
DB_NAME=test
```

### 7.5 测试慢查询

```bash
sql-coach analyze "SELECT * FROM orders WHERE status='pending'"
```

orders 表有 10 万行且 status 无索引，能看到明显的性能提升（从全表扫描到索引查找，通常提速 50-100 倍）。

### 7.6 停止

```bash
cd docker
docker-compose down
```

---

## 8. 支持的 AI 模型

### 8.1 DeepSeek（推荐，便宜）

**官方 API：**
```ini
AI_MODEL=deepseek
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

**阿里百炼兼容模式：**
```ini
AI_MODEL=deepseek
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DEEPSEEK_MODEL=deepseek-v4-pro
```

获取 Key：https://platform.deepseek.com 或 https://bailian.console.aliyun.com

### 8.2 OpenAI

```ini
AI_MODEL=openai
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
```

获取 Key：https://platform.openai.com

### 8.3 Ollama（本地免费）

先安装 Ollama：https://ollama.com

```bash
# 下载模型
ollama pull qwen2.5:14b

# 启动服务
ollama serve
```

配置：
```ini
AI_MODEL=ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b
```

### 8.4 模型对比

| 模型 | 优点 | 缺点 |
|------|------|------|
| DeepSeek | 便宜、中文好、API 兼容 | 需要网络 |
| OpenAI | 效果最好 | 贵、需要科学上网 |
| Ollama | 免费、离线可用 | 需要显存、效果略差 |

---

## 9. 常见问题

### Q1: 报错 "Missing credentials" / "API Key 错误"

检查 `.env` 中的 API Key 是否正确，以及对应的 `AI_MODEL` 是否匹配。

### Q2: 报错 "Unknown database 'test'"

数据库不存在。修改 `.env` 中的 `DB_NAME` 为你实际的数据库，或用 Docker 起测试数据库。

### Q3: 报错 "Can't connect to MySQL server"

MySQL 没启动，或连接信息错误。检查：
- MySQL 服务是否运行
- `.env` 中的 host/port/user/password 是否正确

### Q4: 性能对比显示 0.000s vs 0.000s

表数据量太小，查询太快测不出差异。用 Docker 测试环境（10 万行数据）能看到明显效果。

### Q5: 模型名 "deepseek-V4-flash" 报错不存在

阿里百炼上 DeepSeek 最新模型名是 `deepseek-v4-pro`（全小写）。在 `.env` 里改成：
```ini
DEEPSEEK_MODEL=deepseek-v4-pro
```

### Q6: 分析失败，提示 "AI 返回格式异常"

AI 返回的内容不是合法 JSON。通常是模型能力不足（如小参数本地模型）。换用更强的模型，如 `deepseek-v4-pro` 或 `qwen2.5:14b` 以上。

### Q7: 怎么跳过交互直接用优化后的 SQL？

```bash
echo 2 | sql-coach analyze "SELECT * FROM t"
```

### Q8: 怎么把分析结果保存到文件？

```bash
sql-coach analyze "SELECT * FROM t" > report.txt 2>&1
```

注意：因为涉及交互选择，建议配合 `echo 2 |` 一起用。

---

## 10. 开发者指南

### 10.1 项目结构

```
sql-coach/
├── sql_coach/
│   ├── ai/
│   │   ├── base.py           # AIEngine 抽象基类
│   │   ├── deepseek.py       # DeepSeek 引擎
│   │   ├── openai_adapter.py # OpenAI 引擎
│   │   ├── ollama.py         # Ollama 引擎
│   │   ├── mock.py           # 模拟引擎（mock 模式）
│   │   └── factory.py        # 引擎工厂
│   ├── db/
│   │   ├── connector.py      # MySQL 连接器
│   │   └── mock.py           # 模拟连接器
│   ├── engine/
│   │   ├── sql_parser.py     # SQL 解析
│   │   └── explain_runner.py # EXPLAIN 结果解析
│   ├── report/
│   │   ├── benchmark.py      # 性能对比
│   │   └── formatter.py      # 报告格式化
│   ├── models.py             # 数据模型（dataclass）
│   ├── config.py             # 配置加载
│   ├── coach.py              # 主编排服务
│   └── cli.py                # CLI 入口
├── tests/                    # 测试（82 个）
├── docker/                   # Docker 测试环境
├── .github/workflows/ci.yml  # GitHub Actions CI
├── pyproject.toml
└── README.md
```

### 10.2 运行测试

```bash
# 全部测试
pytest tests/ -v

# 不带覆盖率（更快）
pytest tests/ -o addopts="" -v

# 单个测试文件
pytest tests/test_ai_engine.py -v

# 单个测试
pytest tests/test_cli.py::test_cli_version -v
```

### 10.3 添加新的 AI 引擎

1. 在 `sql_coach/ai/` 下新建文件，实现 `AIEngine` 抽象基类：

```python
from .base import AIEngine

class MyEngine(AIEngine):
    def name(self) -> str:
        return "myengine"

    def analyze(self, sql_info, explain_result):
        # 调用你的 API
        return AnalysisResult(...)
```

2. 在 `sql_coach/ai/factory.py` 注册：

```python
elif model == "myengine":
    from .myengine import MyEngine
    return MyEngine(api_key=config.myengine_api_key)
```

3. 在 `sql_coach/cli.py` 的 `--model` 选项中添加：

```python
type=click.Choice(["deepseek", "openai", "ollama", "myengine"])
```

### 10.4 架构说明

```
用户输入 SQL
    │
    ▼
┌─────────┐     ┌──────────────┐     ┌───────────┐
│ SQLCoach │ ──▶ │  sql_parser  │ ──▶ │ SQLInfo   │
│ (编排)   │     └──────────────┘     └───────────┘
│         │
│         │     ┌──────────────┐     ┌───────────────┐
│         │ ──▶ │ DBConnector  │ ──▶ │ ExplainResult │
│         │     │ .explain()   │     └───────────────┘
│         │
│         │     ┌──────────────┐     ┌───────────────┐
│         │ ──▶ │ AIEngine     │ ──▶ │ AnalysisResult│
│         │     │ .analyze()   │     └───────────────┘
│         │
│         │     ┌──────────────┐     ┌────────────────┐
│         │ ──▶ │ benchmark    │ ──▶ │ BenchmarkResult│
│         │     │              │     └────────────────┘
│         │
│         │     ┌──────────────┐
│         │ ──▶ │ formatter    │ ──▶ 终端输出
└─────────┘     └──────────────┘
    │
    ▼
交互选择 → 剪贴板
```

---

## License

MIT
