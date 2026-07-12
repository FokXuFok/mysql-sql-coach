# SQL Coach

> AI-powered MySQL slow query optimization coach

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/yourname/sql-coach/actions/workflows/ci.yml/badge.svg)](https://github.com/yourname/sql-coach/actions)

SQL Coach 是一个命令行工具，输入一条 SQL，自动连接 MySQL 执行 EXPLAIN，调用 AI 大模型分析执行计划，输出优化建议、改写后的 SQL、索引 DDL，并在数据库中实测性能对比，最后让你选择使用哪个版本的 SQL（自动复制到剪贴板）。

## 特性

- 自动执行 EXPLAIN 并解析执行计划
- 多 AI 模型支持：DeepSeek / OpenAI / Ollama
- 实测优化前后性能对比，给出提速倍数
- 交互式选择，一键复制 SQL 到剪贴板
- 内置 Docker 测试环境
- 无数据库时降级为 AI 推理模式

## 快速开始

### 安装

```bash
pip install sql-coach
```

### 配置

```bash
sql-coach config init
# 编辑 .env 文件，填入 API Key 和数据库连接信息
```

### 使用

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
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 运行覆盖率
pytest --cov=sql_coach --cov-report=html
```

## 技术栈

- **CLI**: click + rich
- **SQL 解析**: sqlparse
- **数据库**: pymysql
- **AI**: openai SDK (兼容 DeepSeek/OpenAI) + httpx (Ollama)
- **测试**: pytest + pytest-mock + pytest-cov

## License

MIT
