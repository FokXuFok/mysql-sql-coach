# SQL Coach API 参考文档

> 版本：0.1.0 | 更新日期：2026-10-12

---

## 目录

- [1. 项目概述](#1-项目概述)
- [2. 模块索引](#2-模块索引)
- [3. 数据模型（sql_coach.models）](#3-数据模型sql_coachmodels)
- [4. 配置加载（sql_coach.config）](#4-配置加载sql_coachconfig)
- [5. 主编排服务（sql_coach.coach）](#5-主编排服务sql_coachcoach)
- [6. 优化器分流（sql_coach.optimizer）](#6-优化器分流sql_coachoptimizer)
- [7. SQL 文本清洗（sql_coach.sql_text）](#7-sql-文本清洗sql_coachsql_text)
- [8. 索引实测模式（sql_coach.index_experiment）](#8-索引实测模式sql_coachindex_experiment)
- [9. AI 分析缓存（sql_coach.cache）](#9-ai-分析缓存sql_coachcache)
- [10. AI 引擎（sql_coach.ai）](#10-ai-引擎sql_coachai)
- [11. 数据库连接器（sql_coach.db）](#11-数据库连接器sql_coachdb)
- [12. SQL 解析引擎（sql_coach.engine）](#12-sql-解析引擎sql_coachengine)
- [13. 本地规则引擎（sql_coach.local）](#13-本地规则引擎sql_coachlocal)
- [14. 性能对比与报告格式化（sql_coach.report）](#14-性能对比与报告格式化sql_coachreport)
- [15. 启动环境自检（sql_coach.diagnostics）](#15-启动环境自检sql_coachdiagnostics)
- [16. CLI 命令行接口（sql_coach.cli）](#16-cli-命令行接口sql_coachcli)
- [17. CLI 交互模式（sql_coach.interactive）](#17-cli-交互模式sql_coachinteractive)
- [18. GUI 桌面应用（gui）](#18-gui-桌面应用gui)
- [19. 配置项参考](#19-配置项参考)
- [20. CLI 命令参考](#20-cli-命令参考)

---

## 1. 项目概述

SQL Coach 是一个 AI 驱动的 MySQL 慢查询优化教练。输入一条 SQL，自动连接 MySQL 执行 EXPLAIN，调用 AI 或本地规则引擎分析执行计划，输出优化建议、改写后的 SQL、索引 DDL，并在数据库中实测性能对比。

**技术栈**：Python 3.10+、PySide6 (Qt6)、click + rich、sqlparse、pymysql、openai SDK、PyInstaller、GitHub Actions

**核心架构**：

```
SQL 字符串
  → parse_sql()          解析 SQL 结构
  → SchemaProvider.load() 读取表结构（尽力而为）
  → DBConnector.explain() 执行 EXPLAIN
  → ComplexityScorer.score() 复杂度评分
  → select_optimizer()     分流：local / ai
  → optimizer.optimize()   产出 AnalysisResult
  → benchmark_sqls()       性能对比
  → measure_index_impact()  索引实测（可选）
  → Report                  最终报告
```

---

## 2. 模块索引

| 模块路径 | 职责 |
|---------|------|
| `sql_coach.models` | 全局数据模型（dataclass） |
| `sql_coach.config` | `.env` 配置加载 |
| `sql_coach.coach` | 主编排服务 `SQLCoach`，串联全流程 |
| `sql_coach.optimizer` | 优化器分流：本地规则引擎 vs AI |
| `sql_coach.sql_text` | SQL 文本清洗（去注释、清字面量） |
| `sql_coach.index_experiment` | 索引实测模式（临时建索引 → 复测 → 回滚） |
| `sql_coach.cache` | 基于 SQLite 的 AI 分析结果缓存 |
| `sql_coach.ai.base` | AI 引擎抽象基类 |
| `sql_coach.ai.factory` | AI 引擎工厂 |
| `sql_coach.ai.deepseek` | DeepSeek 引擎 |
| `sql_coach.ai.openai_adapter` | OpenAI 引擎 |
| `sql_coach.ai.ollama` | Ollama 本地引擎 |
| `sql_coach.ai.mock` | 模拟引擎（无需 API） |
| `sql_coach.db.connector` | MySQL 数据库连接器 |
| `sql_coach.db.mock` | 模拟数据库连接器 |
| `sql_coach.engine.sql_parser` | SQL 解析（基于 sqlparse） |
| `sql_coach.engine.explain_runner` | EXPLAIN 执行与结果解析 |
| `sql_coach.local.engine` | 本地规则引擎 `LocalOptimizer` |
| `sql_coach.local.complexity` | SQL 复杂度评分 |
| `sql_coach.local.schema` | 数据库 schema 读取 |
| `sql_coach.local.rules.*` | 13 条本地优化规则 |
| `sql_coach.report.benchmark` | 性能对比基准测试 |
| `sql_coach.report.formatter` | 报告格式化（Rich 文本） |
| `sql_coach.diagnostics.checks` | 环境自检 |
| `sql_coach.diagnostics.installer` | 分层自动修复 |
| `sql_coach.diagnostics.report` | 自检结果格式化 |
| `sql_coach.cli` | CLI 子命令（click） |
| `sql_coach.interactive` | CLI 交互模式 |
| `gui.app` | GUI 启动入口 |
| `gui.main_window` | 主窗口 |
| `gui.paths` | .env 路径处理 |
| `gui.workers.analyze_worker` | 后台分析线程 |
| `gui.storage.history_store` | 历史记录 JSON 存储 |
| `gui.storage.exporter` | 报告导出（Markdown / HTML） |

---

## 3. 数据模型（sql_coach.models）

所有数据模型均使用 `@dataclass` 定义。

### SQLInfo

SQL 解析后的结构化信息。

```python
@dataclass
class SQLInfo:
    raw_sql: str                          # 原始 SQL 文本
    sql_type: str                         # SQL 类型：SELECT/UPDATE/DELETE/INSERT
    tables: list[str]                     # 涉及的表名
    columns: list[str]                    # SELECT 子句的列（SELECT * 时为 ["*"]）
    where_conditions: list[str]          # WHERE 条件列表（按 AND/OR 拆分）
    join_tables: list[str]                # JOIN 的表名（tables[1:]）
    order_by: list[str]                  # ORDER BY 列
```

**惰性属性**：

| 属性 | 返回类型 | 说明 |
|------|---------|------|
| `nocomment_sql` | `str` | 去掉注释、保留字面量内容（供需要匹配字面量的规则使用） |
| `clean_sql` | `str` | 去掉注释并清空字面量内容（供关键字类规则使用） |

---

### ExplainRow

EXPLAIN 结果中的单行。

```python
@dataclass
class ExplainRow:
    id: int
    select_type: str
    table: str
    type: str               # ALL/index/range/ref/eq_ref/const
    key: Optional[str]       # 使用的索引名
    rows: int                # 预估扫描行数
    extra: str               # Extra 信息
```

---

### ExplainResult

EXPLAIN 执行计划的完整结果。

```python
@dataclass
class ExplainResult:
    rows: list[ExplainRow]           # 执行计划行
    is_full_scan: bool                # 是否存在全表扫描
    missing_indexes: list[str]        # 缺失索引的表名
    problems: list[str]               # 识别到的问题描述
```

---

### Complexity

SQL 复杂度评分结果。

```python
@dataclass
class Complexity:
    level: str                        # simple / medium / complex
    score: int                        # 复杂度分数
    reasons: list[str] = field(default_factory=list)  # 加分原因
```

**等级划分**：`score <= 3` → simple；`score <= threshold` → medium；否则 → complex。

---

### Problem

单个优化问题。

```python
@dataclass
class Problem:
    severity: str       # critical / warning / info
    table: str          # 相关表名
    description: str    # 问题描述
    suggestion: str     # 改进建议
```

---

### AnalysisResult

优化分析结果（AI 或本地引擎产出）。

```python
@dataclass
class AnalysisResult:
    problems: list[Problem]        # 发现的问题列表
    optimized_sql: str              # 优化后的 SQL
    index_ddls: list[str]           # 索引建议 DDL 列表
    explanation: str                # 自然语言解释
```

---

### BenchmarkResult

性能对比结果。

```python
@dataclass
class BenchmarkResult:
    original_time: float        # 原始 SQL 平均耗时（秒）
    optimized_time: float       # 优化 SQL 平均耗时（秒）
    speedup: float              # 提速倍数 = original_time / optimized_time
    original_rows: int           # 原始 SQL 扫描行数
    optimized_rows: int          # 优化 SQL 扫描行数
```

---

### IndexImpact

索引实测结果。

```python
@dataclass
class IndexImpact:
    before_time: float           # 建索引前耗时（秒）
    after_time: float            # 建索引后耗时（秒）
    speedup: float               # 提速 = before / after
    applied_ddls: list[str]      # 实际执行成功的 DDL
    skipped_ddls: list[str]      # 跳过的 DDL（索引已存在或无法解析）
    rolled_back: bool            # 是否已成功回滚
    error: str = ""              # 出错信息
    matched_rows: int = 0        # 命中行数（0 表示未知）
    total_rows: int = 0          # 表总行数（0 表示未知）
    selectivity: float = -1.0    # 命中率 0~1；-1 表示未知
    recommended: bool = False    # 是否建议采纳
    verdict: str = ""            # 中文结论
```

---

### DBConfig

数据库连接配置。

```python
@dataclass
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
```

---

### Config

全局配置。

```python
@dataclass
class Config:
    db: DBConfig
    model: str                          # AI 模型名：deepseek / openai / ollama
    deepseek_api_key: str
    openai_api_key: str
    ollama_url: str
    benchmark_runs: int
    mock: bool
    optimizer_mode: str = "ai"          # auto / local / ai
    complexity_threshold: int = 8        # 复杂度阈值
    measure_index: bool = False          # 索引实测模式
```

**类方法**：

| 方法 | 签名 | 说明 |
|------|------|------|
| `from_env` | `@classmethod def from_env(cls, mock: bool = False) -> Config` | 从环境变量加载配置 |

**示例**：

```python
from sql_coach.models import Config, DBConfig

config = Config.from_env()
# 或手动构造
config = Config(
    db=DBConfig(host="localhost", port=3306, user="root",
                password="pass", database="test"),
    model="deepseek",
    deepseek_api_key="sk-xxx",
    openai_api_key="",
    ollama_url="http://localhost:11434",
    benchmark_runs=3,
    mock=False,
    optimizer_mode="auto",
)
```

---

## 4. 配置加载（sql_coach.config）

### ENV_TEMPLATE

`.env` 模板字符串，包含所有配置项。用于 `config init` 命令和自动修复时生成模板。

### load_env_file

```python
def load_env_file(path: str = ".env") -> None
```

加载 `.env` 文件到 `os.environ`，不覆盖已存在的环境变量。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `path` | `str` | `".env"` | .env 文件路径 |

### load_config

```python
def load_config(env_path: str = ".env", mock: bool = False) -> Config
```

从 `.env` 文件和环境变量加载配置，返回 `Config` 对象。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `env_path` | `str` | `".env"` | .env 文件路径 |
| `mock` | `bool` | `False` | 是否使用模拟模式 |

**返回值**：`Config`

**示例**：

```python
from sql_coach.config import load_config

config = load_config()                    # 从 .env 加载
config = load_config(mock=True)           # 模拟模式（不需要数据库和 API）
config = load_config(env_path="/path/.env")
```

### 内部辅助函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `_get_env` | `(key: str, default: str = "") -> str` | 读取字符串环境变量 |
| `_get_env_int` | `(key: str, default: int = 0) -> int` | 读取整数环境变量 |
| `_get_env_bool` | `(key: str, default: bool = False) -> bool` | 读取布尔环境变量（识别 `1/true/yes/on`） |

---

## 5. 主编排服务（sql_coach.coach）

### Report

最终分析报告，由 `SQLCoach.analyze()` 返回。

```python
@dataclass
class Report:
    sql_info: SQLInfo                              # 解析后的 SQL 信息
    explain: Optional[ExplainResult]                # EXPLAIN 结果
    analysis: AnalysisResult                        # 优化分析结果
    benchmark: Optional[BenchmarkResult]            # 性能对比结果
    engine_used: str = "ai"                         # 使用的引擎名
    complexity: Optional[Complexity] = None          # 复杂度评分
    index_impact: Optional[IndexImpact] = None      # 索引实测结果
```

---

### SQLCoach

主编排服务，串联解析 → EXPLAIN → 分流优化 → 性能对比 → 索引实测全流程。

```python
class SQLCoach:
    def __init__(self, config: Config, use_cache: bool = True)
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `config` | `Config` | — | 全局配置 |
| `use_cache` | `bool` | `True` | 是否启用 AI 分析缓存（mock 模式自动跳过） |

**实例属性**：

| 属性 | 类型 | 说明 |
|------|------|------|
| `config` | `Config` | 全局配置 |
| `db` | `DBConnector \| MockConnector` | 数据库连接器（mock 模式自动用 MockConnector） |
| `ai` | `AIEngine` | 惰性创建的 AI 引擎（纯本地模式不创建，不需要 API Key） |
| `schema_provider` | `SchemaProvider` | schema 读取器 |
| `cache` | `AnalysisCache \| None` | AI 分析缓存（mock 模式为 None） |

**方法**：

#### connect

```python
def connect(self) -> bool
```

连接数据库。mock 模式直接返回 `True`。

**返回值**：`bool`，连接是否成功

#### analyze

```python
def analyze(
    self,
    sql: str,
    on_stage: Optional[Callable[[str, int, int, str], None]] = None,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> Report
```

对一条 SQL 执行完整分析流程。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `sql` | `str` | — | 待分析的 SQL 字符串 |
| `on_stage` | `Callable[[str, int, int, str], None] \| None` | `None` | 进度回调 `(stage_name, step, total, status)` |
| `on_chunk` | `Callable[[str], None] \| None` | `None` | AI 流式输出回调 `(text_chunk)` |

**返回值**：`Report`

**流程**：
1. 解析 SQL（`parse_sql`）
2. 读取 schema（连库时）
3. 执行 EXPLAIN（连库时）
4. 复杂度评分 + 分流（local / ai）
5. 性能对比（有优化 SQL 时）
6. 索引实测（`measure_index=True` 时）

**降级机制**：本地规则引擎整体失败时自动降级到 AI（spec §12）。

**示例**：

```python
from sql_coach.config import load_config
from sql_coach.coach import SQLCoach

config = load_config()
coach = SQLCoach(config)
coach.connect()

report = coach.analyze("SELECT * FROM orders WHERE status='pending'")
print(report.engine_used)        # "local" 或 "deepseek"
print(report.analysis.optimized_sql)
print(report.complexity.level)   # "simple" / "medium" / "complex"

coach.close()
```

#### close

```python
def close(self) -> None
```

释放数据库连接等资源。

---

## 6. 优化器分流（sql_coach.optimizer）

### AIOptimizerAdapter

将 `AIEngine` 适配为统一的 Optimizer 接口。

```python
class AIOptimizerAdapter:
    def __init__(self, engine)  # engine: AIEngine
    def name(self) -> str
    def optimize(self, sql_info: SQLInfo, explain_result: Optional[ExplainResult],
                 schema: Schema, on_chunk: Optional[Callable[[str], None]] = None) -> AnalysisResult
```

### LocalOptimizerAdapter

将 `LocalOptimizer` 适配为统一的 Optimizer 接口。

```python
class LocalOptimizerAdapter:
    def __init__(self, engine: Optional[LocalOptimizer] = None)
    def name(self) -> str    # 返回 "local"
    def optimize(self, sql_info: SQLInfo, explain_result: Optional[ExplainResult],
                 schema: Schema, on_chunk: Optional[Callable[[str], None]] = None) -> AnalysisResult
```

### select_optimizer

```python
def select_optimizer(
    config: Config,
    complexity: Optional[Complexity],
    ai_factory: Callable[[], object],
) -> tuple[OptimizerAdapter, str]
```

根据配置和复杂度选择优化器。

| 参数 | 类型 | 说明 |
|------|------|------|
| `config` | `Config` | 全局配置 |
| `complexity` | `Complexity \| None` | 复杂度评分 |
| `ai_factory` | `Callable[[], object]` | 零参可调用对象，返回 AIEngine（仅在需要 AI 时调用） |

**返回值**：`(optimizer, engine_name)`

**分流逻辑**：

| `optimizer_mode` | 行为 |
|------------------|------|
| `"local"` | 始终用本地规则引擎 |
| `"ai"` | 始终用 AI 引擎 |
| `"auto"`（默认） | simple/medium → 本地；complex → AI |

> 设计要点：`ai_factory` 是惰性的，纯本地模式下不会创建 AI 客户端（也就不需要 API Key）。

---

## 7. SQL 文本清洗（sql_coach.sql_text）

提供 SQL 文本清洗工具，供解析产物 `SQLInfo` 和本地规则使用。

### strip_comments

```python
def strip_comments(sql: str) -> str
```

去掉 `-- 到行尾` 与 `/* ... */` 注释，用空格替换（保留换行）。

> 保留 MySQL 可执行注释 `/*! ... */` 与优化器提示 `/*+ ... */`，因为它们会影响语义/执行计划。

| 参数 | 类型 | 说明 |
|------|------|------|
| `sql` | `str` | SQL 文本 |
| **返回值** | `str` | 去注释后的 SQL |

### strip_literals

```python
def strip_literals(sql: str) -> str
```

清空 `'...'` 与 `"..."` 的内容，保留引号本身（如 `'a!=b'` → `''`）。

| 参数 | 类型 | 说明 |
|------|------|------|
| `sql` | `str` | SQL 文本 |
| **返回值** | `str` | 清空字面量后的 SQL |

### clean

```python
def clean(sql: str) -> str
```

先剥离注释，再清空字面量内容。供关键字类规则在正则匹配前调用。

| 参数 | 类型 | 说明 |
|------|------|------|
| `sql` | `str` | SQL 文本 |
| **返回值** | `str` | 清洗后的 SQL |

**示例**：

```python
from sql_coach.sql_text import clean, strip_comments, strip_literals

sql = "SELECT * FROM t WHERE name='a!=b' -- comment"
clean(sql)         # "SELECT * FROM t WHERE name='' "
strip_comments(sql) # "SELECT * FROM t WHERE name='a!=b'  "
strip_literals(sql) # "SELECT * FROM t WHERE name='' -- comment"
```

> **注意**：需要匹配字面量内容的规则（如 `leading_wildcard` 的 `LIKE '%x'`、`function_on_column` 的 `DATE(col)='2026-01-01'`）不要使用 `clean`，应使用 `strip_comments`。

---

## 8. 索引实测模式（sql_coach.index_experiment）

通过临时创建建议索引、复测同一 SQL、再回滚索引，量化索引真实收益。

### 常量

```python
INDEX_SPEEDUP_THRESHOLD = 1.3  # 收益守卫阈值
```

### parse_create_index

```python
def parse_create_index(ddl: str) -> Optional[tuple[str, str]]
```

从 `CREATE INDEX` 语句解析出 `(索引名, 表名)`。兼容可选的 `IF NOT EXISTS`、反引号与大小写。

| 参数 | 类型 | 说明 |
|------|------|------|
| `ddl` | `str` | DDL 语句 |
| **返回值** | `tuple[str, str] \| None` | `(索引名, 表名)`，无法解析时返回 `None` |

### build_drop_index

```python
def build_drop_index(ddl: str) -> Optional[str]
```

生成与 `CREATE INDEX` 对应的 `DROP INDEX` 语句。

| 参数 | 类型 | 说明 |
|------|------|------|
| `ddl` | `str` | CREATE INDEX DDL |
| **返回值** | `str \| None` | 对应的 DROP INDEX 语句 |

### measure_index_impact

```python
def measure_index_impact(
    conn,
    sql: str,
    ddls: list[str],
    runs: int = 3,
) -> Optional[IndexImpact]
```

实测索引收益：建索引前基准 → 临时建索引 → 复测 → 回滚。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `conn` | `DBConnector` | — | 数据库连接器 |
| `sql` | `str` | — | 待测 SQL |
| `ddls` | `list[str]` | — | 索引建议 DDL 列表 |
| `runs` | `int` | `3` | 基准测试次数 |

**返回值**：`IndexImpact | None`（未连接或 ddls 为空时返回 None）

**安全保证**：
- 任何异常都不会向上抛出
- 已成功创建的索引一定会在 `finally` 中回滚
- 回滚失败的信息会记入 `error` 并置 `rolled_back=False`
- 索引已存在时跳过（既不建也不删）
- 默认关闭（`Config.measure_index=False`）

---

## 9. AI 分析缓存（sql_coach.cache）

### AnalysisCache

基于 SQLite 的 AI 分析结果持久缓存。

```python
class AnalysisCache:
    def __init__(self, path=None, ttl=CACHE_TTL_SECONDS)
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `path` | `Path \| None` | `~/.sql-coach/cache.db` | 缓存数据库路径 |
| `ttl` | `int` | `300`（5 分钟） | 缓存存活时间（秒） |

**常量**：

```python
DEFAULT_CACHE_DIR = Path.home() / ".sql-coach"
DEFAULT_CACHE_PATH = DEFAULT_CACHE_DIR / "cache.db"
CACHE_TTL_SECONDS = 300  # 5 分钟
```

**方法**：

| 方法 | 签名 | 说明 |
|------|------|------|
| `get` | `(sql: str) -> Optional[AnalysisResult]` | 获取缓存，过期返回 `None` |
| `put` | `(sql: str, result: AnalysisResult) -> None` | 存入缓存 |
| `delete` | `(sql: str) -> None` | 删除单条缓存 |
| `clear` | `() -> int` | 清空所有缓存，返回删除条数 |
| `count` | `() -> int` | 返回缓存条目数 |

**缓存策略**：以 SQL 的 SHA-256 哈希为 key，TTL 5 分钟，仅缓存非 local 引擎的分析结果。

---

## 10. AI 引擎（sql_coach.ai）

### AIEngine（抽象基类）

```python
class AIEngine(ABC):
    @abstractmethod
    def analyze(
        self,
        sql_info: SQLInfo,
        explain_result: Optional[ExplainResult],
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> AnalysisResult

    @abstractmethod
    def name(self) -> str
```

所有 AI 引擎的统一接口。`analyze` 接收 SQL 信息和 EXPLAIN 结果，返回 `AnalysisResult`。`on_chunk` 用于流式输出。

### create_ai_engine（工厂函数）

```python
def create_ai_engine(model: str, config: Config) -> AIEngine
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | `str` | 模型名：`"deepseek"` / `"openai"` / `"ollama"` |
| `config` | `Config` | 全局配置 |

**返回值**：`AIEngine`

> mock 模式返回 `MockAIEngine`，不调用真实 API。

### DeepSeekEngine

```python
class DeepSeekEngine(AIEngine):
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com",
                 model: str = "deepseek-chat", max_retries: int = 3)
    def name(self) -> str    # "deepseek"
    def analyze(self, sql_info, explain_result, on_chunk=None) -> AnalysisResult
```

基于 OpenAI SDK 兼容接口调用 DeepSeek API。支持流式和非流式模式，失败自动重试（默认 3 次，间隔 1 秒）。

### OpenAIEngine

```python
class OpenAIEngine(AIEngine):
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1",
                 model: str = "gpt-4o", max_retries: int = 3)
    def name(self) -> str    # "openai"
    def analyze(self, sql_info, explain_result, on_chunk=None) -> AnalysisResult
```

基于 OpenAI SDK 调用 GPT-4o。复用 DeepSeek 的 prompt 构建和响应解析逻辑。

### OllamaEngine

```python
class OllamaEngine(AIEngine):
    def __init__(self, url: str = "http://localhost:11434",
                 model: str = "qwen2.5:14b", max_retries: int = 3)
    def name(self) -> str    # "ollama"
    def analyze(self, sql_info, explain_result, on_chunk=None) -> AnalysisResult
```

基于 httpx 调用本地 Ollama `/api/chat` 接口。支持流式和非流式模式，超时 60 秒。

### MockAIEngine

```python
class MockAIEngine(AIEngine):
    def name(self) -> str    # "mock"
    def analyze(self, sql_info, explain_result, on_chunk=None) -> AnalysisResult
```

模拟引擎，不调用任何 API。基于 SQL 结构生成示例分析结果（检测 `SELECT *` 和 WHERE 条件缺索引）。

---

## 11. 数据库连接器（sql_coach.db）

### DBConnector

MySQL 数据库连接器，基于 pymysql。

```python
class DBConnector:
    def __init__(self, config: DBConfig)
```

**方法**：

| 方法 | 签名 | 说明 |
|------|------|------|
| `connect` | `() -> bool` | 建立连接，返回是否成功 |
| `is_connected` | `() -> bool` | 是否已连接 |
| `explain` | `(sql: str) -> ExplainResult` | 执行 `EXPLAIN FORMAT=JSON` 并解析 |
| `benchmark` | `(sql: str, runs: int = 3) -> float` | 多次执行 SQL，返回平均耗时（秒） |
| `execute` | `(sql: str) -> None` | 执行 DDL/DML 语句并 commit |
| `query` | `(sql: str, params=None) -> list[tuple]` | 执行只读查询，返回所有行 |
| `close` | `() -> None` | 关闭连接 |

**示例**：

```python
from sql_coach.models import DBConfig
from sql_coach.db.connector import DBConnector

conn = DBConnector(DBConfig(host="localhost", port=3306, user="root",
                            password="pass", database="test"))
conn.connect()
explain = conn.explain("SELECT * FROM orders WHERE status='pending'")
rows = conn.query("SELECT COUNT(*) FROM orders")
conn.close()
```

### MockConnector

模拟数据库连接器，无真实数据，所有方法返回空结果。

```python
class MockConnector:
    def connect(self) -> bool           # True
    def is_connected(self) -> bool       # True
    def explain(self, sql: str) -> ExplainResult    # 空 ExplainResult
    def benchmark(self, sql: str, runs: int = 3) -> float  # 0.0
    def execute(self, sql: str) -> None  # pass
    def query(self, sql: str, params=None) -> list[tuple]  # []
    def close(self) -> None              # pass
```

---

## 12. SQL 解析引擎（sql_coach.engine）

### parse（sql_parser.py）

```python
def parse(sql: str) -> SQLInfo
```

解析 SQL 字符串，提取表名、列名、WHERE 条件、ORDER BY 等结构化信息。基于 `sqlparse` 库。

| 参数 | 类型 | 说明 |
|------|------|------|
| `sql` | `str` | SQL 字符串 |

**返回值**：`SQLInfo`

**示例**：

```python
from sql_coach.engine.sql_parser import parse

info = parse("SELECT id, name FROM users WHERE age > 18 ORDER BY name")
# info.sql_type     -> "SELECT"
# info.tables       -> ["users"]
# info.columns      -> ["id", "name"]
# info.where_conditions -> ["age > 18"]
# info.order_by     -> ["name"]
```

### run_explain（explain_runner.py）

```python
def run_explain(conn, sql: str) -> ExplainResult
```

在数据库连接上执行 `EXPLAIN FORMAT=JSON` 并解析结果。

| 参数 | 类型 | 说明 |
|------|------|------|
| `conn` | `pymysql.Connection` | 数据库连接 |
| `sql` | `str` | 待 EXPLAIN 的 SQL |

**返回值**：`ExplainResult`

### parse_explain_json

```python
def parse_explain_json(explain_json_str: str) -> ExplainResult
```

解析 `EXPLAIN FORMAT=JSON` 的 JSON 输出。遍历 `query_block` / `nested_loop` / `ordering_operation` / `grouping_operation` 等结构，识别全表扫描、缺失索引、文件排序、临时表等问题。

| 参数 | 类型 | 说明 |
|------|------|------|
| `explain_json_str` | `str` | EXPLAIN JSON 输出 |

**返回值**：`ExplainResult`

---

## 13. 本地规则引擎（sql_coach.local）

### LocalOptimizer

遍历所有规则，汇总 problems / index_ddls / optimized_sql。

```python
class LocalOptimizer:
    def __init__(self, rules: list[Rule] | None = None)
    def optimize(self, sql_info: SQLInfo, schema: Schema) -> AnalysisResult
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `rules` | `list[Rule] \| None` | `None` | 规则列表，`None` 使用 `DEFAULT_RULES` |

**返回值**：`AnalysisResult`

**规则叠加**：改写后的 SQL 会重建 `RuleContext`，让后续规则在同一份 SQL 上叠加，而不是互相覆盖。

**异常隔离**：单条规则异常不影响整体（`_safe` 方法捕获并记录 warning）。

**示例**：

```python
from sql_coach.engine.sql_parser import parse
from sql_coach.local.engine import LocalOptimizer
from sql_coach.local.schema import Schema

sql_info = parse("SELECT * FROM orders WHERE status='pending'")
optimizer = LocalOptimizer()
result = optimizer.optimize(sql_info, Schema())
# result.problems, result.optimized_sql, result.index_ddls
```

### DEFAULT_RULES

```python
DEFAULT_RULES = [
    MissingIndexRule(), SelectStarRule(), LeadingWildcardRule(),
    FunctionOnColumnRule(), ImplicitCastRule(), NoLimitRule(),
    DeepPaginationRule(), OrConditionRule(), SubqueryToJoinRule(),
    NegationRule(), OrderByRandRule(), UnionDedupRule(), RedundantDistinctRule(),
]
```

### ComplexityScorer（complexity.py）

按 SQL 结构特征打分并划分等级。

```python
class ComplexityScorer:
    def __init__(self, threshold: int = DEFAULT_THRESHOLD)  # DEFAULT_THRESHOLD = 8
    def score(self, sql_info: SQLInfo) -> Complexity
```

**评分规则**：

| 特征 | 分数 |
|------|------|
| 2 张表 | +2 |
| ≥3 张表 | +4 |
| 每个子查询/派生表 | +3 |
| CTE (WITH) | +3 |
| UNION | +2 |
| 聚合/分组 (GROUP BY/HAVING) | +2 |
| 聚合函数 (COUNT/SUM/AVG/MAX/MIN) | +2 |
| 多列分组（≥2 列） | +1 |
| 窗口函数 (OVER) | +5 |
| CASE 表达式 | +2 |
| 嵌套函数表达式 | +2 |
| 多 OR 条件 (≥2) | +1 |
| 无 WHERE 全表查询 | +2 |
| 多列排序 (≥2) | +1 |

**等级**：`score <= min(3, threshold)` → simple；`score <= threshold` → medium；否则 → complex。

**常量**：

```python
DEFAULT_THRESHOLD = 8
SIMPLE_MAX = 3
```

### Schema 与 SchemaProvider（schema.py）

#### TableSchema

```python
@dataclass
class TableSchema:
    name: str
    columns: dict[str, str] = field(default_factory=dict)   # 列名(小写) -> 数据类型(小写)
    indexes: list[list[str]] = field(default_factory=list)  # 索引列列表（按顺序）
```

#### Schema

```python
@dataclass
class Schema:
    tables: dict[str, TableSchema] = field(default_factory=dict)
```

| 方法 | 签名 | 说明 |
|------|------|------|
| `has_table` | `(table: str) -> bool` | 该表是否已从数据库读到 |
| `has_index_on` | `(table: str, column: str) -> bool` | 该列是否为某个索引的最左列 |
| `column_type` | `(table: str, column: str) -> Optional[str]` | 获取列的数据类型 |
| `__bool__` | `() -> bool` | 是否有表数据 |

#### SchemaProvider

```python
class SchemaProvider:
    def __init__(self, connector=None)
    def load(self, tables: list[str]) -> Schema
```

从 `information_schema` 读取表结构与索引，按表维度累积缓存。

| 参数 | 类型 | 说明 |
|------|------|------|
| `connector` | `DBConnector \| MockConnector \| None` | 数据库连接器 |

> 缓存按表维度累积，CLI 交互模式一次会话分析多条 SQL 时不会"第一次查了谁就一直返回谁"。

---

### 规则基类（rules/base.py）

```python
@dataclass
class RuleContext:
    sql_info: SQLInfo
    schema: Schema

class Rule(ABC):
    name: str = ""          # 规则名
    risk: str = "safe"      # safe（仅建议）/ rewrite（会改写 SQL）

    def check(self, ctx: RuleContext) -> list[Problem]       # 检测问题
    def rewrite(self, ctx: RuleContext) -> Optional[str]      # 改写 SQL
    def ddls(self, ctx: RuleContext) -> list[str]             # 生成索引 DDL
```

### 内置规则一览

| 规则类 | `name` | `risk` | 说明 |
|--------|--------|--------|------|
| `MissingIndexRule` | `missing_index` | safe | WHERE 条件列缺索引时建议建索引（仅单表） |
| `SelectStarRule` | `select_star` | rewrite | `SELECT *` 有 schema 时展开为显式列 |
| `LeadingWildcardRule` | `leading_wildcard` | safe | `LIKE '%x'` 无法使用索引 |
| `FunctionOnColumnRule` | `function_on_column` | rewrite | `DATE(col)='...'` 索引失效，改写为范围条件 |
| `ImplicitCastRule` | `implicit_cast` | safe | 字符串列与数字比较触发隐式类型转换 |
| `NoLimitRule` | `no_limit` | safe | 无 WHERE 且无 LIMIT 的查询可能返回大量数据 |
| `DeepPaginationRule` | `deep_pagination` | safe | `LIMIT offset,n` 中 offset 过大（≥1000） |
| `OrConditionRule` | `or_condition` | safe | WHERE 含 OR 可能无法有效使用索引 |
| `SubqueryToJoinRule` | `subquery_to_join` | safe | `IN (SELECT ...)` 建议改写为 JOIN/EXISTS |
| `NegationRule` | `negation` | safe | `!=`/`<>`/`NOT IN`/`NOT LIKE`/`NOT EXISTS` 无法有效使用索引 |
| `OrderByRandRule` | `order_by_rand` | safe | `ORDER BY RAND()` 全表随机排序 |
| `UnionDedupRule` | `union_dedup` | safe | `UNION` 去重开销大，建议改用 `UNION ALL` |
| `RedundantDistinctRule` | `redundant_distinct` | safe | `SELECT DISTINCT` 与 `GROUP BY` 同层时 DISTINCT 冗余 |

---

## 14. 性能对比与报告格式化（sql_coach.report）

### benchmark_sqls

```python
def benchmark_sqls(
    conn,
    original_sql: str,
    optimized_sql: str,
    runs: int = 3,
) -> Optional[BenchmarkResult]
```

对比原始 SQL 与优化 SQL 的执行性能。

| 参数 | 类型 | 说明 |
|------|------|------|
| `conn` | `DBConnector \| MockConnector` | 数据库连接器 |
| `original_sql` | `str` | 原始 SQL |
| `optimized_sql` | `str` | 优化 SQL |
| `runs` | `int` | 基准测试次数 |

**返回值**：`BenchmarkResult | None`（连接不可用时返回 None）

### format_report

```python
def format_report(
    sql_info: SQLInfo,
    explain: Optional[ExplainResult],
    analysis: AnalysisResult,
    benchmark: Optional[BenchmarkResult],
    engine_used: str = "ai",
    index_impact: Optional[IndexImpact] = None,
) -> str
```

格式化完整报告为 Rich 文本字符串。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `sql_info` | `SQLInfo` | — | SQL 信息 |
| `explain` | `ExplainResult \| None` | — | EXPLAIN 结果 |
| `analysis` | `AnalysisResult` | — | 分析结果 |
| `benchmark` | `BenchmarkResult \| None` | — | 性能对比 |
| `engine_used` | `str` | `"ai"` | 使用的引擎（控制标题文案：local 显示"本地规则说明"，其他显示"AI 解释"） |
| `index_impact` | `IndexImpact \| None` | `None` | 索引实测结果 |

**返回值**：`str`（Rich 格式的完整报告文本）

### format_problems

```python
def format_problems(problems: list[Problem]) -> str
```

格式化问题列表为字符串。

---

## 15. 启动环境自检（sql_coach.diagnostics）

### CheckResult

```python
@dataclass
class CheckResult:
    name: str           # 检查项名称
    status: str         # ok / warn / fail
    message: str        # 描述信息
    fix_hint: str = ""  # 修复提示
    auto_fixable: bool = False  # 是否可自动修复
    key: str = ""       # 机器可读标识（env_file / mysql / ai / runtime）
```

### 检查函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `check_env_file` | `(env_path: str) -> CheckResult` | 检查 .env 文件是否存在 |
| `check_mysql` | `(config: Config) -> CheckResult` | 检查 MySQL 连接 |
| `check_ai` | `(config: Config, probe: bool = False) -> CheckResult` | 检查 AI 配置（probe=True 时对 Ollama 做轻量试连） |
| `check_runtime` | `() -> CheckResult` | 检查 Python 版本和依赖 |
| `run_all` | `(config: Config, env_path: str = ".env", probe: bool = False) -> list[CheckResult]` | 运行全部检查 |

### FixOutcome

```python
@dataclass
class FixOutcome:
    name: str
    applied: bool
    message: str
    key: str = ""
```

### apply_auto_fixes

```python
def apply_auto_fixes(results: list[CheckResult], env_path: str = ".env") -> list[FixOutcome]
```

只处理 `auto_fixable=True` 的项（目前仅 `env_file`：生成 `.env` 模板）。

### copy_hint

```python
def copy_hint(hint: str) -> bool
```

把修复指引复制到剪贴板，失败返回 `False`。

### format_results

```python
def format_results(results: list[CheckResult]) -> str
```

格式化自检结果为纯文本。

---

## 16. CLI 命令行接口（sql_coach.cli）

基于 click 的 CLI 入口，提供以下子命令：

### main

```python
@click.group()
@click.version_option(__version__)
def main()
```

CLI 根命令组。

### analyze

```python
@main.command()
@click.argument("sql", required=False)
@click.option("--file", "-f", ...)
@click.option("--model", "-m", ...)
@click.option("--mock", is_flag=True, ...)
@click.option("--no-cache", is_flag=True, ...)
@click.option("--engine", "-e", ...)
@click.option("--measure-index", is_flag=True, ...)
def analyze(sql, file, model, mock, no_cache, engine, measure_index)
```

分析并优化 SQL 语句。

| 参数/选项 | 说明 |
|-----------|------|
| `sql`（位置参数） | SQL 字符串 |
| `--file, -f` | 从文件读取 SQL |
| `--model, -m` | 指定 AI 模型：deepseek/openai/ollama |
| `--mock` | 模拟模式（无需数据库） |
| `--no-cache` | 禁用 AI 分析缓存 |
| `--engine, -e` | 优化引擎：auto/local/ai |
| `--measure-index` | 实测索引收益（会临时建索引再回滚） |

### config init

```python
@config.command("init")
def config_init()
```

初始化 `.env` 配置文件。

### config test

```python
@config.command("test")
def config_test()
```

测试数据库和 AI 连通性。

### doctor

```python
@main.command()
@click.option("--fix", is_flag=True, ...)
@click.option("--probe", is_flag=True, ...)
def doctor(fix, probe)
```

环境自检：检查 .env / MySQL / AI 配置 / 运行环境。

| 选项 | 说明 |
|------|------|
| `--fix` | 自动修复可安全修复的项（如生成 .env 模板） |
| `--probe` | 额外对 Ollama 做轻量连通性试连 |

### cache clear

```python
@cache.command("clear")
def cache_clear()
```

清空 AI 分析缓存。

### cache stats

```python
@cache.command("stats")
def cache_stats()
```

查看缓存统计。

---

## 17. CLI 交互模式（sql_coach.interactive）

### run_cli

```python
def run_cli() -> None
```

交互式 CLI 入口：循环读取 SQL 并分析，输入 `q` 退出。

加载配置 → 连接数据库（失败则切换到模拟模式）→ 主循环 `while True` 读取 SQL → `analyze_one` → `coach.close()`。

### analyze_one

```python
def analyze_one(coach: SQLCoach, sql: str) -> None
```

分析单条 SQL 并打印完整报告。

| 参数 | 类型 | 说明 |
|------|------|------|
| `coach` | `SQLCoach` | SQLCoach 实例 |
| `sql` | `str` | SQL 字符串 |

**示例**：

```python
from sql_coach.interactive import run_cli

# 直接运行交互模式
run_cli()
# 在终端中输入 SQL 进行分析，输入 q 退出
```

---

## 18. GUI 桌面应用（gui）

### gui.app.run

```python
def run() -> None
```

GUI 模式启动入口。创建 `QApplication`，定位 `.env` 路径，加载配置，运行环境自检（非首次时跳过），创建并显示 `MainWindow`。

### gui.paths.get_env_path

```python
def get_env_path() -> str
```

返回 `.env` 文件绝对路径。

| 模式 | 路径 |
|------|------|
| 打包模式 (`sys.frozen`) | `.exe` 同目录下的 `.env` |
| 开发模式 | 当前工作目录下的 `.env` |

### MainWindow

```python
class MainWindow(QMainWindow):
    def __init__(self, config: Optional[Config] = None, env_path: str = ".env") -> None
```

主窗口，左右分栏组装 `SqlInputWidget`（40%）和 `ReportView`（60%）。

**关键功能**：
- 工具栏：分析、清空、导出报告、历史记录、设置
- 菜单栏：文件（导出/退出）、设置、帮助（关于）
- 状态栏：DB 连接状态、分析进度、引擎和耗时
- 后台线程分析（`AnalyzeWorker`），防止 GUI 卡死
- 启动时自动检测 DB 连通性，失败切换 mock 模式（非模态提示）
- 历史记录存储（`HistoryStore`）
- 报告导出（`Exporter`，支持 Markdown / HTML）

### AnalyzeWorker

```python
class AnalyzeWorker(QThread):
    finished = Signal(Report)
    error = Signal(str)
    stage_changed = Signal(str)

    def __init__(self, sql: str, config: Config, use_cache: bool = True,
                 parent: Optional[QThread] = None) -> None
    def run(self) -> None
```

后台分析线程。每次分析创建新的 `SQLCoach` 实例，分析完 `close()`。

**信号**：

| 信号 | 参数 | 说明 |
|------|------|------|
| `finished` | `Report` | 分析完成 |
| `error` | `str` | 分析异常 |
| `stage_changed` | `str` | 阶段变化：`"parse"` / `"explain"` / `"ai"` / `"benchmark"` |

### stage_label

```python
def stage_label(stage: str) -> str
```

返回阶段的中文描述。

### HistoryStore

```python
class HistoryStore:
    def __init__(self, path: Optional[str] = None) -> None
```

JSON 文件历史记录存储，路径 `~/.sql-coach/history.json`，最多 100 条。

| 方法 | 签名 | 说明 |
|------|------|------|
| `add` | `(sql: str, report: Report, ai_time_ms: float) -> str` | 添加记录，返回 6 位 hex id |
| `list` | `() -> list[dict]` | 返回全部记录（按时间倒序） |
| `delete` | `(record_id: str) -> bool` | 删除指定 id 记录 |
| `clear` | `() -> int` | 清空全部记录 |
| `get` | `(record_id: str) -> Optional[dict]` | 按 id 取单条记录 |

### Exporter

```python
class Exporter:
    def to_markdown(self, report: Report) -> str
    def to_html(self, report: Report) -> str
    def save(self, report: Report, path: str, fmt: str) -> None
```

报告导出器，纯 Python 实现。

| 方法 | 说明 |
|------|------|
| `to_markdown` | 生成 Markdown 报告 |
| `to_html` | 生成 HTML 报告（内联 CSS，独立文件） |
| `save` | 保存到文件，`fmt` 支持 `"markdown"` / `"html"` |

---

## 19. 配置项参考

所有配置项通过 `.env` 文件或环境变量设置。

### 数据库连接

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DB_HOST` | `localhost` | MySQL 主机地址 |
| `DB_PORT` | `3306` | MySQL 端口 |
| `DB_USER` | `root` | MySQL 用户名 |
| `DB_PASSWORD` | （空） | MySQL 密码 |
| `DB_NAME` | `test` | 数据库名 |

### AI 模型

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `AI_MODEL` | `deepseek` | AI 模型：deepseek / openai / ollama |
| `DEEPSEEK_API_KEY` | （空） | DeepSeek API Key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API 地址 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | DeepSeek 模型名 |
| `OPENAI_API_KEY` | （空） | OpenAI API Key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI API 地址 |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama 服务地址 |
| `OLLAMA_MODEL` | `qwen2.5:14b` | Ollama 模型名 |

### 优化器分流

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `OPTIMIZER_MODE` | `auto` | 优化器模式：auto / local / ai |
| `COMPLEXITY_THRESHOLD` | `8` | 复杂度阈值（≥ 该值走 AI） |
| `MEASURE_INDEX` | `false` | 是否实测索引收益（临时建索引再回滚） |

### 通用

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `BENCHMARK_RUNS` | `3` | 性能对比测试次数 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

---

## 20. CLI 命令参考

### 入口

```bash
sql-coach [OPTIONS] COMMAND [ARGS]
```

### 命令一览

| 命令 | 说明 |
|------|------|
| `sql-coach analyze [SQL]` | 分析并优化 SQL |
| `sql-coach config init` | 初始化 .env 配置文件 |
| `sql-coach config test` | 测试数据库和 AI 连通性 |
| `sql-coach doctor` | 环境自检 |
| `sql-coach cache clear` | 清空 AI 分析缓存 |
| `sql-coach cache stats` | 查看缓存统计 |

### analyze 用法示例

```bash
# 分析单条 SQL
sql-coach analyze "SELECT * FROM orders WHERE status='pending'"

# 从文件读取
sql-coach analyze -f slow.sql

# 模拟模式（不需要数据库）
sql-coach analyze --mock "SELECT * FROM orders WHERE status='pending'"

# 指定 AI 模型
sql-coach analyze -m openai "SELECT * FROM orders"

# 指定优化引擎
sql-coach analyze --engine local "SELECT * FROM orders"

# 实测索引收益
sql-coach analyze --measure-index "SELECT * FROM orders WHERE status='pending'"
```

### doctor 用法示例

```bash
# 基本自检
sql-coach doctor

# 自动修复可安全修复的项
sql-coach doctor --fix

# 对 Ollama 做轻量连通性试连
sql-coach doctor --probe
```

### 交互模式

```bash
# 在 PyCharm 或终端运行
python main.py
# 输入 SQL 进行分析，输入 q 退出
```

### GUI 模式

```bash
# 命令行启动 GUI
python main.py --gui

# 打包后的 exe 直接双击运行
sql-coach-gui.exe
```

---

## 附录：入口分发逻辑

```python
# main.py
def main() -> None:
    if getattr(sys, 'frozen', False) or '--gui' in sys.argv:
        from gui.app import run
        run()          # GUI 模式
    else:
        from sql_coach.interactive import run_cli
        run_cli()      # CLI 交互模式
```

- **打包后**（`sys.frozen=True`）：直接启动 GUI
- **开发模式**（`python main.py`）：进入 CLI 交互模式
- **显式 GUI**（`python main.py --gui`）：启动 GUI
