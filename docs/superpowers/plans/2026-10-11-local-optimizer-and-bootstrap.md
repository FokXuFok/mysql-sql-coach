# 本地算法分流 + 启动自检 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让简单/中等复杂度的 SQL 由本地规则引擎毫秒级优化，复杂 SQL 才走 AI；同时提供单文件 onefile exe 与启动环境自检（分层修复）。

**Architecture:** 新增 `sql_coach/local/`（复杂度评分 + 规则引擎 + schema 读取）与 `sql_coach/optimizer.py`（唯一分流点，本地与 AI 产出同一种 `AnalysisResult`）；`SQLCoach.analyze()` 增加"读 schema → 评分 → 分流"三步；新增 `sql_coach/diagnostics/` 做启动自检。`ai/`、`engine/`、`report/`、`cache.py` 零改动，`db/` 仅新增只读 `query()`。

**Tech Stack:** Python 3.10+、sqlparse、pymysql、click、rich、PySide6、pytest、PyInstaller（onefile）

**关键约定（务必遵守）:**
- 所有注释/文档用中文；提交信息用中文。
- 每条新逻辑都先写失败测试（TDD），再写最小实现。
- `Config` 新增字段的 **dataclass 默认值是 `"ai"`**（保证既有直接构造 Config 的调用与测试行为不变）；`Config.from_env()` 里默认值是 `"auto"`（真实运行走自动分流）。
- 测试统一用项目 venv：`./.venv/Scripts/python.exe -m pytest`（Windows）。

---

## Task 0: 准备开发环境

**Files:**
- 无代码改动（仅环境）

- [ ] **Step 1: 安装项目依赖到 venv**

当前 `.venv` 是空壳，先装齐依赖。

Run:
```bash
./.venv/Scripts/python.exe -m pip install -e ".[gui,dev]"
```

- [ ] **Step 2: 确认测试基线可跑**

Run:
```bash
./.venv/Scripts/python.exe -m pytest tests/ -q -o addopts=""
```
Expected: 全部通过（约 134 个用例）。若失败先排查环境，不要继续。

---

## Task 1: 数据模型与配置增量

**Files:**
- Modify: `sql_coach/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_models.py`：

```python
def test_complexity_dataclass_defaults():
    from sql_coach.models import Complexity
    c = Complexity(level="simple", score=0)
    assert c.reasons == []


def test_config_optimizer_fields_direct_construction():
    """直接构造 Config 时默认走 AI，保持既有行为不变。"""
    from sql_coach.models import Config, DBConfig
    config = Config(db=DBConfig(host="h", port=3306, user="u", password="p", database="d"),
                    model="deepseek", deepseek_api_key="k", openai_api_key="",
                    ollama_url="http://localhost:11434", benchmark_runs=3, mock=False)
    assert config.optimizer_mode == "ai"
    assert config.complexity_threshold == 8


def test_config_from_env_optimizer_defaults(monkeypatch):
    from sql_coach.models import Config
    monkeypatch.delenv("OPTIMIZER_MODE", raising=False)
    monkeypatch.delenv("COMPLEXITY_THRESHOLD", raising=False)
    config = Config.from_env()
    assert config.optimizer_mode == "auto"
    assert config.complexity_threshold == 8


def test_config_from_env_optimizer_override(monkeypatch):
    from sql_coach.models import Config
    monkeypatch.setenv("OPTIMIZER_MODE", "local")
    monkeypatch.setenv("COMPLEXITY_THRESHOLD", "5")
    config = Config.from_env()
    assert config.optimizer_mode == "local"
    assert config.complexity_threshold == 5
```

- [ ] **Step 2: 运行测试确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_models.py -q -o addopts="" -k "complexity or optimizer"`
Expected: FAIL（`ImportError: cannot import name 'Complexity'` / `TypeError: unexpected keyword`）

- [ ] **Step 3: 实现**

在 `sql_coach/models.py` 顶部已导入 `dataclass, field`。在 `Problem` 定义之前插入 `Complexity`：

```python
@dataclass
class Complexity:
    level: str  # simple / medium / complex
    score: int
    reasons: list[str] = field(default_factory=list)
```

把 `Config` 改为（在 `mock: bool` 之后追加两个带默认值的字段）：

```python
@dataclass
class Config:
    db: DBConfig
    model: str
    deepseek_api_key: str
    openai_api_key: str
    ollama_url: str
    benchmark_runs: int
    mock: bool
    optimizer_mode: str = "ai"          # dataclass 默认保持既有行为；from_env 默认 auto
    complexity_threshold: int = 8
```

并在 `Config.from_env` 的 `return cls(...)` 中追加：

```python
            optimizer_mode=_get_env("OPTIMIZER_MODE", "auto"),
            complexity_threshold=_get_env_int("COMPLEXITY_THRESHOLD", 8),
```

- [ ] **Step 4: 运行测试确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_models.py tests/test_coach.py tests/test_config.py -q -o addopts=""`
Expected: PASS（含原有用例，验证无回归）

- [ ] **Step 5: 提交**

```bash
git add sql_coach/models.py tests/test_models.py
git commit -m "feat(models): 新增 Complexity 与 Config 分流字段"
```

---

## Task 2: 复杂度评分器

**Files:**
- Create: `sql_coach/local/__init__.py`
- Create: `sql_coach/local/complexity.py`
- Test: `tests/test_complexity.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_complexity.py`：

```python
"""复杂度评分器测试。"""
from sql_coach.models import SQLInfo
from sql_coach.local.complexity import ComplexityScorer


def make_info(sql, sql_type="SELECT", tables=(), columns=(), where=(), order_by=()):
    return SQLInfo(raw_sql=sql, sql_type=sql_type, tables=list(tables),
                   columns=list(columns), where_conditions=list(where),
                   join_tables=[], order_by=list(order_by))


def test_simple_single_table():
    info = make_info("SELECT * FROM orders WHERE status='pending'",
                     tables=["orders"], columns=["*"], where=["status='pending'"])
    c = ComplexityScorer().score(info)
    assert c.level == "simple"
    assert c.score <= 3


def test_medium_two_tables_group_by():
    info = make_info(
        "SELECT u.city, COUNT(*) FROM users u JOIN orders o ON u.id=o.user_id GROUP BY u.city",
        tables=["users", "orders"], where=["u.id=o.user_id"])
    c = ComplexityScorer().score(info)
    assert c.level == "medium"


def test_complex_window_three_tables():
    info = make_info(
        "SELECT ROW_NUMBER() OVER (ORDER BY a.id) FROM a JOIN b ON a.id=b.id JOIN c ON b.id=c.id",
        tables=["a", "b", "c"], where=["a.id=b.id", "b.id=c.id"])
    c = ComplexityScorer().score(info)
    assert c.level == "complex"
    assert any("窗口" in r for r in c.reasons)


def test_threshold_override():
    # 单表(0) + 聚合/分组(2) = 2；带 WHERE 所以不叠加"无 WHERE"惩罚
    info = make_info("SELECT a, COUNT(*) FROM t WHERE x=1 GROUP BY a",
                     tables=["t"], columns=["a"], where=["x=1"])
    assert ComplexityScorer(threshold=1).score(info).level == "complex"
    assert ComplexityScorer(threshold=8).score(info).level == "simple"


def test_reasons_recorded():
    info = make_info("SELECT * FROM a JOIN b ON a.id=b.id", tables=["a", "b"])
    c = ComplexityScorer().score(info)
    assert any("2 张表" in r for r in c.reasons)


def test_correlated_subquery_not_specially_penalized():
    info = make_info(
        "SELECT u.id FROM users u WHERE (SELECT COUNT(*) FROM orders o "
        "WHERE o.user_id=u.id) > 3",
        tables=["users", "orders"],
        where=["(SELECT COUNT(*) FROM orders o WHERE o.user_id=u.id) > 3"])
    c = ComplexityScorer().score(info)
    # 2 表(+2) + 1 个子查询(+3) + COUNT(*) 聚合函数(+2) = 7；无"相关子查询"专项加分
    assert c.score == 7
    assert all("相关子查询" not in r for r in c.reasons)
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_complexity.py -q -o addopts=""`
Expected: FAIL（`ModuleNotFoundError: No module named 'sql_coach.local'`）

- [ ] **Step 3: 实现**

创建 `sql_coach/local/__init__.py`（空文件即可）。

创建 `sql_coach/local/complexity.py`：

```python
"""SQL 复杂度评分：纯结构分析，不调用 AI。"""
import re

from ..models import SQLInfo, Complexity

DEFAULT_THRESHOLD = 8
SIMPLE_MAX = 3


class ComplexityScorer:
    """按 SQL 结构特征打分并划分等级。"""

    def __init__(self, threshold: int = DEFAULT_THRESHOLD):
        # 阈值下界钳制：0/负数会让一切判为 complex
        self.threshold = max(1, threshold)

    def score(self, sql_info: SQLInfo) -> Complexity:
        sql = sql_info.raw_sql or ""
        upper = sql.upper()
        s = 0
        reasons: list[str] = []

        n = len(sql_info.tables)
        if n == 2:
            s += 2
            reasons.append("2 张表")
        elif n >= 3:
            s += 4
            reasons.append(f"{n} 张表")

        subqueries = max(0, len(re.findall(r"\bSELECT\b", upper)) - 1)
        if subqueries:
            s += 3 * subqueries
            reasons.append(f"{subqueries} 个子查询/派生表")

        if re.search(r"\bWITH\b", upper):
            s += 3
            reasons.append("CTE")
        if re.search(r"\bUNION\b", upper):
            s += 2
            reasons.append("UNION")
        if re.search(r"\b(GROUP\s+BY|HAVING)\b", upper):
            s += 2
            reasons.append("聚合/分组")
        elif re.search(r"\b(COUNT|SUM|AVG|MAX|MIN)\s*\(", upper):
            s += 2
            reasons.append("聚合函数")
        if re.search(r"\bOVER\s*\(", upper):
            s += 5
            reasons.append("窗口函数")
        if re.search(r"\bCASE\b", upper):
            s += 2
            reasons.append("CASE 表达式")
        if len(re.findall(r"\bOR\b", upper)) >= 2:
            s += 1
            reasons.append("多 OR 条件")
        if sql_info.sql_type == "SELECT" and not sql_info.where_conditions:
            s += 2
            reasons.append("无 WHERE 全表查询")
        if len(sql_info.order_by) >= 2:
            s += 1
            reasons.append("多列排序")

        if s <= min(SIMPLE_MAX, self.threshold):
            level = "simple"
        elif s <= self.threshold:
            level = "medium"
        else:
            level = "complex"
        return Complexity(level=level, score=s, reasons=reasons)
```

> **关于相关子查询**：早期设计曾打算对相关子查询额外 +5，但纯正则启发式在
> "子查询内部含函数/嵌套括号"时会漏判、在"子查询自带别名/派生表"时会误判（双向都错），
> 会把简单查询误抬成 complex、把复杂查询漏判为 medium。因此**本期不做相关子查询识别**，
> 仅保留"子查询/派生表 +3"这一稳健计数。

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_complexity.py -q -o addopts=""`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sql_coach/local/__init__.py sql_coach/local/complexity.py tests/test_complexity.py
git commit -m "feat(local): 新增 SQL 复杂度评分器"
```

---

## Task 3: Schema 读取（含 DBConnector.query）

**Files:**
- Create: `sql_coach/local/schema.py`
- Modify: `sql_coach/db/connector.py`（新增只读 `query`）
- Modify: `sql_coach/db/mock.py`（新增 `query`）
- Test: `tests/test_schema.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_schema.py`：

```python
"""schema 读取测试。"""
from sql_coach.local.schema import Schema, TableSchema, SchemaProvider


class FakeConnector:
    def __init__(self, connected=True):
        self.connected = connected
        self.calls = []

    def is_connected(self):
        return self.connected

    def query(self, sql, params=None):
        self.calls.append(sql)
        wanted = {str(p).lower() for p in (params or ())}
        if "information_schema.COLUMNS" in sql:
            rows = [("orders", "id", "bigint"),
                    ("orders", "status", "varchar"),
                    ("orders", "created_at", "datetime"),
                    ("users", "id", "bigint"),
                    ("users", "phone", "varchar")]
        elif "information_schema.STATISTICS" in sql:
            rows = [("orders", "PRIMARY", 1, "id"),
                    ("orders", "idx_status", 1, "status"),
                    ("users", "PRIMARY", 1, "id")]
        else:
            rows = []
        return [r for r in rows if r[0].lower() in wanted]


def test_empty_schema_is_falsy():
    assert not Schema()


def test_has_index_on_and_column_type():
    s = Schema(tables={"orders": TableSchema(
        name="orders",
        columns={"status": "varchar"},
        indexes=[["status"], ["id"]])})
    assert s.has_index_on("orders", "status")
    assert not s.has_index_on("orders", "missing")
    assert s.column_type("orders", "status") == "varchar"
    assert s.column_type("orders", "nope") is None


def test_has_index_on_uses_leftmost_column_only():
    # 复合索引 (a, b)：单独用 b 无法走该索引
    s = Schema(tables={"t": TableSchema(name="t", indexes=[["a", "b"]])})
    assert s.has_index_on("t", "a")
    assert not s.has_index_on("t", "b")


def test_has_table_distinguishes_unknown_table():
    assert not Schema().has_table("orders")
    s = Schema(tables={"orders": TableSchema(name="orders")})
    assert s.has_table("orders")
    assert not s.has_table("users")


def test_provider_without_connector_returns_empty():
    sp = SchemaProvider(None)
    assert sp.load(["orders"]) == Schema()


def test_provider_reads_information_schema():
    sp = SchemaProvider(FakeConnector())
    schema = sp.load(["orders"])
    assert schema.has_index_on("orders", "status")
    assert schema.column_type("orders", "status") == "varchar"


def test_provider_caches_after_first_load():
    fake = FakeConnector()
    sp = SchemaProvider(fake)
    sp.load(["orders"])
    n = len(fake.calls)
    sp.load(["orders"])
    assert len(fake.calls) == n  # 第二次不再查库


def test_provider_accumulates_across_different_tables():
    """复用 provider 时，第二次换表不能返回陈旧 schema。"""
    sp = SchemaProvider(FakeConnector())
    sp.load(["orders"])
    schema = sp.load(["users"])
    assert schema.has_table("orders")
    assert schema.has_table("users")


def test_provider_empty_tables_does_not_pollute_cache():
    """tables 为空时不得把空结果写进缓存。"""
    sp = SchemaProvider(FakeConnector())
    sp.load([])
    assert sp.load(["orders"]).has_table("orders")


def test_provider_swallows_query_error():
    class Boom(FakeConnector):
        def query(self, sql, params=()):
            raise RuntimeError("db down")
    sp = SchemaProvider(Boom())
    assert sp.load(["orders"]) == Schema()
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_schema.py -q -o addopts=""`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

在 `sql_coach/db/connector.py` 的 `execute` 方法之后新增（不改动任何现有方法）：

```python
    def query(self, sql: str, params=None) -> list[tuple]:
        """执行只读查询并返回所有行；未连接时记录警告并返回空列表。"""
        if not self.is_connected():
            logger.warning("数据库未连接，query 返回空结果")
            return []
        with self._conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()
```

在 `sql_coach/db/mock.py` 的 `execute` 之后新增：

```python
    def query(self, sql: str, params=None) -> list[tuple]:
        """模拟连接器无真实数据，返回空列表。"""
        return []
```

追加到 `tests/test_db_connector.py`：

```python
def test_query_returns_empty_when_not_connected():
    from sql_coach.db.connector import DBConnector
    from sql_coach.models import DBConfig
    conn = DBConnector(DBConfig("h", 3306, "u", "p", "d"))
    assert conn.query("SELECT 1") == []


def test_mock_connector_query_returns_empty():
    from sql_coach.db.mock import MockConnector
    assert MockConnector().query("SELECT 1") == []
```

创建 `sql_coach/local/schema.py`：

```python
"""数据库 schema 读取（供本地规则校验），连不上库时降级为空 schema。"""
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TableSchema:
    name: str
    columns: dict[str, str] = field(default_factory=dict)
    indexes: list[list[str]] = field(default_factory=list)


@dataclass
class Schema:
    tables: dict[str, TableSchema] = field(default_factory=dict)

    def has_table(self, table: str) -> bool:
        """该表是否已从数据库读到（用于区分"已校验"与"未校验"）。"""
        return table.lower() in self.tables

    def has_index_on(self, table: str, column: str) -> bool:
        """该列是否为某个索引的最左列（MySQL 最左前缀语义）。"""
        t = self.tables.get(table.lower())
        if t is None:
            return False
        col = column.lower()
        return any(idx and idx[0].lower() == col for idx in t.indexes)

    def column_type(self, table: str, column: str) -> Optional[str]:
        t = self.tables.get(table.lower())
        if t is None:
            return None
        return t.columns.get(column.lower())

    def __bool__(self) -> bool:
        return bool(self.tables)


class SchemaProvider:
    """从 information_schema 读取表结构与索引，按表累积缓存。

    注意：provider 会被 SQLCoach 复用（CLI 交互模式一次会话分析多条 SQL），
    因此缓存必须按表维度累积，不能"第一次查了谁就一直返回谁"。
    """

    def __init__(self, connector=None):
        self.connector = connector
        self._tables: dict[str, TableSchema] = {}
        self._attempted: set[str] = set()

    def load(self, tables: list[str]) -> Schema:
        if self.connector is None or not self._is_connected():
            return Schema()
        wanted = [t for t in tables if t and t.lower() not in self._attempted]
        if wanted:
            try:
                fetched = self._read(wanted)
            except Exception as e:  # noqa: BLE001 - 降级不阻断
                logger.warning("读取 schema 失败，降级为空 schema: %s", e)
                return Schema(tables=dict(self._tables))
            self._merge(fetched)
            self._attempted.update(t.lower() for t in wanted)
        return Schema(tables=dict(self._tables))

    def _merge(self, schema: Schema) -> None:
        for name, ts in schema.tables.items():
            existing = self._tables.get(name)
            if existing is None:
                self._tables[name] = ts
                continue
            existing.columns.update(ts.columns)
            for idx in ts.indexes:
                if idx not in existing.indexes:
                    existing.indexes.append(idx)

    def _is_connected(self) -> bool:
        checker = getattr(self.connector, "is_connected", None)
        return bool(checker()) if callable(checker) else False

    def _read(self, tables: list[str]) -> Schema:
        schema = Schema()
        if not tables:
            return schema
        lowered = [t.lower() for t in tables]
        placeholders = ",".join(["%s"] * len(lowered))

        for tname, cname, dtype in self.connector.query(
            "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS "
            f"WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) IN ({placeholders})",
            tuple(lowered),
        ):
            ts = schema.tables.setdefault(tname.lower(), TableSchema(name=tname))
            ts.columns[cname.lower()] = (dtype or "").lower()

        grouped: dict[tuple[str, str], list[tuple[int, str]]] = {}
        for tname, iname, seq, cname in self.connector.query(
            "SELECT TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX, COLUMN_NAME "
            "FROM information_schema.STATISTICS "
            f"WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) IN ({placeholders}) "
            "ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX",
            tuple(lowered),
        ):
            grouped.setdefault((tname.lower(), iname), []).append((seq, cname))
        for (tname, _iname), cols in grouped.items():
            ts = schema.tables.setdefault(tname, TableSchema(name=tname))
            ts.indexes.append([c for _, c in sorted(cols)])
        return schema
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_schema.py tests/test_db_connector.py -q -o addopts=""`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sql_coach/local/schema.py sql_coach/db/connector.py sql_coach/db/mock.py tests/test_schema.py
git commit -m "feat(local): 新增 schema 读取与只读 query 方法"
```

---

## Task 4: 规则抽象基类

**Files:**
- Create: `sql_coach/local/rules/__init__.py`
- Create: `sql_coach/local/rules/base.py`
- Test: `tests/test_local_rules.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_local_rules.py`：

```python
"""本地规则测试。"""
from sql_coach.models import SQLInfo
from sql_coach.local.schema import Schema, TableSchema
from sql_coach.local.rules.base import Rule, RuleContext


def make_info(sql, sql_type="SELECT", tables=(), columns=(), where=(), order_by=()):
    return SQLInfo(raw_sql=sql, sql_type=sql_type, tables=list(tables),
                   columns=list(columns), where_conditions=list(where),
                   join_tables=[], order_by=list(order_by))


def test_rule_base_defaults_are_noop():
    class Noop(Rule):
        name = "noop"
    ctx = RuleContext(sql_info=make_info("SELECT 1"), schema=Schema())
    assert Noop().check(ctx) == []
    assert Noop().rewrite(ctx) is None
    assert Noop().ddls(ctx) == []
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_local_rules.py -q -o addopts=""`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

创建 `sql_coach/local/rules/__init__.py`（空文件）。

创建 `sql_coach/local/rules/base.py`：

```python
"""本地优化规则的抽象基类与上下文。"""
from abc import ABC
from dataclasses import dataclass
from typing import Optional

from ...models import SQLInfo, Problem
from ..schema import Schema


@dataclass
class RuleContext:
    sql_info: SQLInfo
    schema: Schema


class Rule(ABC):
    """一条本地优化规则。risk: safe（仅建议）/ rewrite（会改写 SQL）。"""

    name: str = ""
    risk: str = "safe"

    def check(self, ctx: RuleContext) -> list[Problem]:
        return []

    def rewrite(self, ctx: RuleContext) -> Optional[str]:
        return None

    def ddls(self, ctx: RuleContext) -> list[str]:
        return []
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_local_rules.py -q -o addopts=""`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sql_coach/local/rules/__init__.py sql_coach/local/rules/base.py tests/test_local_rules.py
git commit -m "feat(local): 新增规则抽象基类"
```

---

## Task 5: 安全规则组（缺索引 / 前导通配 / 隐式转换 / 无 LIMIT / 深分页 / OR / 子查询）

**Files:**
- Create: `sql_coach/local/rules/missing_index.py`
- Create: `sql_coach/local/rules/leading_wildcard.py`
- Create: `sql_coach/local/rules/implicit_cast.py`
- Create: `sql_coach/local/rules/no_limit.py`
- Create: `sql_coach/local/rules/deep_pagination.py`
- Create: `sql_coach/local/rules/or_condition.py`
- Create: `sql_coach/local/rules/subquery_to_join.py`
- Test: `tests/test_local_rules.py`（追加）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_local_rules.py` 末尾追加：

```python
from sql_coach.local.rules.missing_index import MissingIndexRule
from sql_coach.local.rules.leading_wildcard import LeadingWildcardRule
from sql_coach.local.rules.implicit_cast import ImplicitCastRule
from sql_coach.local.rules.no_limit import NoLimitRule
from sql_coach.local.rules.deep_pagination import DeepPaginationRule
from sql_coach.local.rules.or_condition import OrConditionRule
from sql_coach.local.rules.subquery_to_join import SubqueryToJoinRule


def _ctx(sql, tables=(), columns=(), where=(), order_by=(), schema=None):
    return RuleContext(sql_info=make_info(sql, tables=tables, columns=columns,
                                          where=where, order_by=order_by),
                       schema=schema or Schema())


def test_missing_index_without_schema_flags_suspected():
    ctx = _ctx("SELECT * FROM orders WHERE status='pending'",
               tables=["orders"], where=["status='pending'"])
    problems = MissingIndexRule().check(ctx)
    assert len(problems) == 1
    assert "疑似" in problems[0].description
    assert MissingIndexRule().ddls(ctx) == ["CREATE INDEX idx_orders_status ON orders(status);"]


def test_missing_index_with_schema_skips_existing_index():
    schema = Schema(tables={"orders": TableSchema(name="orders", indexes=[["status"]])})
    ctx = _ctx("SELECT * FROM orders WHERE status='pending'",
               tables=["orders"], where=["status='pending'"], schema=schema)
    assert MissingIndexRule().check(ctx) == []
    assert MissingIndexRule().ddls(ctx) == []


def test_leading_wildcard():
    ctx = _ctx("SELECT id FROM users WHERE name LIKE '%abc'", tables=["users"], columns=["id"])
    assert len(LeadingWildcardRule().check(ctx)) == 1
    ctx_ok = _ctx("SELECT id FROM users WHERE name LIKE 'abc%'", tables=["users"], columns=["id"])
    assert LeadingWildcardRule().check(ctx_ok) == []


def test_implicit_cast_only_when_schema_known():
    schema = Schema(tables={"users": TableSchema(name="users", columns={"phone": "varchar"})})
    ctx = _ctx("SELECT * FROM users WHERE phone=13800000000",
               tables=["users"], where=["phone=13800000000"], schema=schema)
    assert len(ImplicitCastRule().check(ctx)) == 1
    # 无 schema 时不误报
    ctx2 = _ctx("SELECT * FROM users WHERE phone=13800000000",
                tables=["users"], where=["phone=13800000000"])
    assert ImplicitCastRule().check(ctx2) == []


def test_no_limit_requires_no_where():
    ctx = _ctx("SELECT * FROM orders", tables=["orders"], columns=["*"])
    assert len(NoLimitRule().check(ctx)) == 1
    ctx_ok = _ctx("SELECT * FROM orders WHERE status='x'", tables=["orders"],
                  columns=["*"], where=["status='x'"])
    assert NoLimitRule().check(ctx_ok) == []


def test_deep_pagination_threshold():
    ctx = _ctx("SELECT * FROM orders LIMIT 100000, 20", tables=["orders"], columns=["*"])
    assert len(DeepPaginationRule().check(ctx)) == 1
    ctx_ok = _ctx("SELECT * FROM orders LIMIT 10, 20", tables=["orders"], columns=["*"])
    assert DeepPaginationRule().check(ctx_ok) == []


def test_or_condition():
    ctx = _ctx("SELECT * FROM orders WHERE a=1 OR b=2", tables=["orders"],
               columns=["*"], where=["a=1", "b=2"])
    assert len(OrConditionRule().check(ctx)) == 1


def test_subquery_to_join():
    ctx = _ctx("SELECT * FROM users WHERE id IN (SELECT user_id FROM orders)",
               tables=["users"], columns=["*"])
    assert len(SubqueryToJoinRule().check(ctx)) == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_local_rules.py -q -o addopts=""`
Expected: FAIL（`ModuleNotFoundError: ... missing_index`）

- [ ] **Step 3: 实现各规则**

`sql_coach/local/rules/missing_index.py`：

```python
"""缺索引规则：WHERE 条件列缺索引时建议建索引。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_OP_SPLIT = re.compile(
    r"\s*(?:=|>=|<=|<>|!=|>|<|\bLIKE\b|\bIN\b|\bBETWEEN\b)", re.IGNORECASE)
_IDENT = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)?$")


class MissingIndexRule(Rule):
    name = "missing_index"
    risk = "safe"

    def check(self, ctx: RuleContext) -> list[Problem]:
        table = self._table(ctx)
        if not table:
            return []
        verified = ctx.schema.has_table(table)
        out = []
        for col in self._columns(ctx):
            desc = (f"WHERE 条件列 {col} 缺少索引" if verified
                    else f"WHERE 条件列 {col} 疑似缺少索引（未连接数据库校验）")
            out.append(Problem(severity="critical", table=table, description=desc,
                               suggestion=f"在 {table}({col}) 上创建索引"))
        return out

    def ddls(self, ctx: RuleContext) -> list[str]:
        table = self._table(ctx)
        if not table:
            return []
        return [f"CREATE INDEX idx_{table}_{col} ON {table}({col});"
                for col in self._columns(ctx)]

    def _table(self, ctx: RuleContext):
        return ctx.sql_info.tables[0] if ctx.sql_info.tables else ""

    def _columns(self, ctx: RuleContext) -> list[str]:
        table = self._table(ctx)
        out, seen = [], set()
        for cond in ctx.sql_info.where_conditions:
            col = self._column(cond)
            if not col or col in seen:
                continue
            if ctx.schema and ctx.schema.has_index_on(table, col):
                continue
            seen.add(col)
            out.append(col)
        return out

    @staticmethod
    def _column(cond: str):
        left = _OP_SPLIT.split(cond, maxsplit=1)[0].strip().strip("` ")
        if not _IDENT.match(left):
            return None
        return left.split(".")[-1]
```

`sql_coach/local/rules/leading_wildcard.py`：

```python
"""前导通配规则：LIKE '%x' 无法使用索引。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_PAT = re.compile(r"\bLIKE\s+'%", re.IGNORECASE)


class LeadingWildcardRule(Rule):
    name = "leading_wildcard"
    risk = "safe"

    def check(self, ctx: RuleContext) -> list[Problem]:
        if not _PAT.search(ctx.sql_info.raw_sql or ""):
            return []
        table = ctx.sql_info.tables[0] if ctx.sql_info.tables else ""
        return [Problem(severity="warning", table=table,
                        description="LIKE 以 % 开头，无法使用索引",
                        suggestion="改为后缀匹配，或使用全文索引 / 反向列")]
```

`sql_coach/local/rules/implicit_cast.py`：

```python
"""隐式类型转换规则：字符串列与数字比较（需 schema 已知列类型）。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_PAT = re.compile(r"([A-Za-z_]\w*)\s*=\s*(\d+)")
_STR_TYPES = ("varchar", "char", "text", "tinytext", "mediumtext", "longtext")


class ImplicitCastRule(Rule):
    name = "implicit_cast"
    risk = "safe"

    def check(self, ctx: RuleContext) -> list[Problem]:
        if not ctx.sql_info.tables:
            return []
        table = ctx.sql_info.tables[0]
        if not ctx.schema.has_table(table):
            return []
        out = []
        for cond in ctx.sql_info.where_conditions:
            m = _PAT.search(cond)
            if not m:
                continue
            col = m.group(1)
            ctype = ctx.schema.column_type(table, col)
            if ctype and ctype in _STR_TYPES:
                out.append(Problem(severity="warning", table=table,
                                   description=f"字符串列 {col} 与数字比较，可能触发隐式类型转换",
                                   suggestion=f"为 {col} 的比较值加引号，避免索引失效"))
        return out
```

`sql_coach/local/rules/no_limit.py`：

```python
"""无 LIMIT 规则：无 WHERE 且无 LIMIT 的查询可能返回大量数据。"""
from ...models import Problem
from .base import Rule, RuleContext


class NoLimitRule(Rule):
    name = "no_limit"
    risk = "safe"

    def check(self, ctx: RuleContext) -> list[Problem]:
        info = ctx.sql_info
        if info.sql_type != "SELECT" or not info.tables or info.where_conditions:
            return []
        if "LIMIT" in (info.raw_sql or "").upper():
            return []
        return [Problem(severity="info", table=info.tables[0],
                        description="查询无 WHERE 且无 LIMIT，可能返回大量数据",
                        suggestion="确认是否需要全量返回；如只需部分数据请加 LIMIT")]
```

`sql_coach/local/rules/deep_pagination.py`：

```python
"""深分页规则：LIMIT offset,n 中 offset 过大。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_PAT = re.compile(r"\bLIMIT\s+(\d+)\s*,\s*(\d+)", re.IGNORECASE)
_OFFSET_THRESHOLD = 1000


class DeepPaginationRule(Rule):
    name = "deep_pagination"
    risk = "safe"  # 自动改写需主键信息，本期仅建议

    def check(self, ctx: RuleContext) -> list[Problem]:
        m = _PAT.search(ctx.sql_info.raw_sql or "")
        if not m or int(m.group(1)) < _OFFSET_THRESHOLD:
            return []
        table = ctx.sql_info.tables[0] if ctx.sql_info.tables else ""
        return [Problem(severity="warning", table=table,
                        description=f"深分页 LIMIT {m.group(1)}, {m.group(2)}，offset 越大越慢",
                        suggestion="改用基于主键/游标的续页，或延迟关联（先用覆盖索引取主键再 JOIN）")]
```

`sql_coach/local/rules/or_condition.py`：

```python
"""OR 条件规则：WHERE 含 OR 可能无法有效使用索引。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_PAT = re.compile(r"\bOR\b", re.IGNORECASE)


class OrConditionRule(Rule):
    name = "or_condition"
    risk = "safe"  # OR->UNION 存在语义风险，本期仅建议

    def check(self, ctx: RuleContext) -> list[Problem]:
        sql = ctx.sql_info.raw_sql or ""
        if not _PAT.search(sql) or len(ctx.sql_info.where_conditions) < 2:
            return []
        table = ctx.sql_info.tables[0] if ctx.sql_info.tables else ""
        return [Problem(severity="warning", table=table,
                        description="WHERE 中使用 OR，可能无法有效使用索引",
                        suggestion="若两侧列都有索引，可改写为 UNION ALL")]
```

`sql_coach/local/rules/subquery_to_join.py`：

```python
"""子查询规则：IN (SELECT ...) 建议改写为 JOIN / EXISTS。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_PAT = re.compile(r"\bIN\s*\(\s*SELECT\b", re.IGNORECASE)


class SubqueryToJoinRule(Rule):
    name = "subquery_to_join"
    risk = "safe"  # JOIN 改写可能产生重复行，本期仅建议

    def check(self, ctx: RuleContext) -> list[Problem]:
        if not _PAT.search(ctx.sql_info.raw_sql or ""):
            return []
        table = ctx.sql_info.tables[0] if ctx.sql_info.tables else ""
        return [Problem(severity="warning", table=table,
                        description="使用 IN (SELECT ...) 子查询，可能执行效率较低",
                        suggestion="改写为 JOIN 或 EXISTS（注意去重语义）")]
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_local_rules.py -q -o addopts=""`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sql_coach/local/rules/ tests/test_local_rules.py
git commit -m "feat(local): 新增安全规则组（7 条）"
```

---

## Task 6: 改写规则（SELECT * 展开 / 函数包裹列）

**Files:**
- Create: `sql_coach/local/rules/select_star.py`
- Create: `sql_coach/local/rules/function_on_column.py`
- Test: `tests/test_local_rules.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
from sql_coach.local.rules.select_star import SelectStarRule
from sql_coach.local.rules.function_on_column import FunctionOnColumnRule


def test_select_star_check_and_rewrite_with_schema():
    schema = Schema(tables={"orders": TableSchema(
        name="orders", columns={"id": "bigint", "status": "varchar", "amount": "decimal"})})
    ctx = _ctx("SELECT * FROM orders WHERE status='x'",
               tables=["orders"], columns=["*"], where=["status='x'"], schema=schema)
    rule = SelectStarRule()
    assert len(rule.check(ctx)) == 1
    assert rule.rewrite(ctx) == "SELECT id, status, amount FROM orders WHERE status='x'"


def test_select_star_no_rewrite_without_schema():
    ctx = _ctx("SELECT * FROM orders", tables=["orders"], columns=["*"])
    rule = SelectStarRule()
    assert len(rule.check(ctx)) == 1
    assert rule.rewrite(ctx) is None


def test_function_on_column_check_and_rewrite():
    sql = "SELECT id FROM orders WHERE DATE(created_at)='2026-01-01'"
    ctx = _ctx(sql, tables=["orders"], columns=["id"], where=["DATE(created_at)='2026-01-01'"])
    rule = FunctionOnColumnRule()
    assert len(rule.check(ctx)) == 1
    assert rule.rewrite(ctx) == (
        "SELECT id FROM orders WHERE (created_at >= '2026-01-01 00:00:00' "
        "AND created_at < DATE_ADD('2026-01-01', INTERVAL 1 DAY))")


def test_function_on_column_no_rewrite_for_other_functions():
    sql = "SELECT id FROM orders WHERE UPPER(name)='ABC'"
    ctx = _ctx(sql, tables=["orders"], columns=["id"], where=["UPPER(name)='ABC'"])
    assert FunctionOnColumnRule().rewrite(ctx) is None
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_local_rules.py -q -o addopts=""`
Expected: FAIL（`ModuleNotFoundError: ... select_star`）

- [ ] **Step 3: 实现**

`sql_coach/local/rules/select_star.py`：

```python
"""SELECT * 规则：有 schema 时展开为显式列，否则仅建议。"""
import re

from ...models import Problem
from .base import Rule, RuleContext


class SelectStarRule(Rule):
    name = "select_star"
    risk = "rewrite"

    def check(self, ctx: RuleContext) -> list[Problem]:
        info = ctx.sql_info
        if info.sql_type == "SELECT" and info.columns == ["*"] and info.tables:
            return [Problem(severity="warning", table=info.tables[0],
                            description="使用了 SELECT *，会读取全部列",
                            suggestion="只查询需要的列，减少数据传输与回表成本")]
        return []

    def rewrite(self, ctx: RuleContext) -> str | None:
        info = ctx.sql_info
        if info.columns != ["*"] or not info.tables or not ctx.schema:
            return None
        table = info.tables[0]
        ts = ctx.schema.tables.get(table.lower())
        if ts is None or not ts.columns:
            return None
        cols = ", ".join(ts.columns.keys())
        return re.sub(r"(?i)\bSELECT\s+\*", f"SELECT {cols}", info.raw_sql, count=1)
```

`sql_coach/local/rules/function_on_column.py`：

```python
"""函数包裹索引列规则：DATE(col)='...' 会使索引失效，可安全改写为范围条件。"""
import re

from ...models import Problem
from .base import Rule, RuleContext

_CHECK_PAT = re.compile(
    r"\b(DATE|YEAR|MONTH|DAY|UPPER|LOWER|SUBSTRING|SUBSTR|CAST)\s*\(\s*"
    r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\)",
    re.IGNORECASE)
_DATE_EQ_PAT = re.compile(
    r"\bDATE\s*\(\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\)\s*=\s*'(\d{4}-\d{2}-\d{2})'",
    re.IGNORECASE)


class FunctionOnColumnRule(Rule):
    name = "function_on_column"
    risk = "rewrite"

    def check(self, ctx: RuleContext) -> list[Problem]:
        out = []
        for cond in ctx.sql_info.where_conditions:
            m = _CHECK_PAT.search(cond)
            if m:
                table = ctx.sql_info.tables[0] if ctx.sql_info.tables else ""
                out.append(Problem(
                    severity="warning", table=table,
                    description=f"条件对列使用了函数 {m.group(1)}({m.group(2)})，索引会失效",
                    suggestion=f"改写为对 {m.group(2)} 的范围条件，使其可用索引"))
        return out

    def rewrite(self, ctx: RuleContext) -> str | None:
        sql = ctx.sql_info.raw_sql or ""
        if not sql:
            return None

        def repl(m):
            col, day = m.group(1), m.group(2)
            return (f"({col} >= '{day} 00:00:00' "
                    f"AND {col} < DATE_ADD('{day}', INTERVAL 1 DAY))")

        new_sql, n = _DATE_EQ_PAT.subn(repl, sql)
        return new_sql if n else None
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_local_rules.py -q -o addopts=""`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sql_coach/local/rules/select_star.py sql_coach/local/rules/function_on_column.py tests/test_local_rules.py
git commit -m "feat(local): 新增改写规则（SELECT * 展开 / 日期函数范围化）"
```

---

## Task 7: 本地优化引擎

**Files:**
- Create: `sql_coach/local/engine.py`
- Test: `tests/test_local_optimizer.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_local_optimizer.py`：

```python
"""本地优化引擎测试。"""
from sql_coach.models import SQLInfo
from sql_coach.local.schema import Schema, TableSchema
from sql_coach.local.engine import LocalOptimizer
from sql_coach.local.rules.base import Rule
from sql_coach.local.rules.select_star import SelectStarRule


def make_info(sql, tables=(), columns=(), where=()):
    return SQLInfo(raw_sql=sql, sql_type="SELECT", tables=list(tables),
                   columns=list(columns), where_conditions=list(where),
                   join_tables=[], order_by=[])


def test_optimizer_aggregates_problems_and_ddls():
    info = make_info("SELECT * FROM orders WHERE status='pending'",
                     tables=["orders"], columns=["*"], where=["status='pending'"])
    result = LocalOptimizer().optimize(info, Schema())
    descs = [p.description for p in result.problems]
    assert any("SELECT *" in d for d in descs)
    assert any("status" in d for d in descs)
    assert result.index_ddls == ["CREATE INDEX idx_orders_status ON orders(status);"]
    assert "本地规则引擎" in result.explanation


def test_optimizer_rewrites_select_star_with_schema():
    schema = Schema(tables={"orders": TableSchema(
        name="orders", columns={"id": "bigint", "status": "varchar"})})
    info = make_info("SELECT * FROM orders WHERE status='x'",
                     tables=["orders"], columns=["*"], where=["status='x'"])
    result = LocalOptimizer().optimize(info, schema)
    assert result.optimized_sql == "SELECT id, status FROM orders WHERE status='x'"


def test_optimizer_isolates_rule_exception():
    class Boom(Rule):
        name = "boom"

        def check(self, ctx):
            raise RuntimeError("boom")

    info = make_info("SELECT * FROM orders", tables=["orders"], columns=["*"])
    result = LocalOptimizer(rules=[Boom(), SelectStarRule()]).optimize(info, Schema())
    assert any("SELECT *" in p.description for p in result.problems)


def test_optimizer_no_hit_keeps_original_sql():
    info = make_info("SELECT id FROM orders WHERE id=1",
                     tables=["orders"], columns=["id"], where=["id=1"])
    result = LocalOptimizer(rules=[SelectStarRule()]).optimize(info, Schema())
    assert result.optimized_sql == "SELECT id FROM orders WHERE id=1"
    assert result.problems == []
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_local_optimizer.py -q -o addopts=""`
Expected: FAIL（`ModuleNotFoundError: ... engine`）

- [ ] **Step 3: 实现**

创建 `sql_coach/local/engine.py`：

```python
"""本地规则引擎：汇总所有规则，产出与 AI 一致的 AnalysisResult。"""
import logging

from ..models import SQLInfo, AnalysisResult
from .schema import Schema
from .rules.base import Rule, RuleContext
from .rules.missing_index import MissingIndexRule
from .rules.select_star import SelectStarRule
from .rules.leading_wildcard import LeadingWildcardRule
from .rules.function_on_column import FunctionOnColumnRule
from .rules.implicit_cast import ImplicitCastRule
from .rules.no_limit import NoLimitRule
from .rules.deep_pagination import DeepPaginationRule
from .rules.or_condition import OrConditionRule
from .rules.subquery_to_join import SubqueryToJoinRule

logger = logging.getLogger(__name__)

DEFAULT_RULES = [
    MissingIndexRule(), SelectStarRule(), LeadingWildcardRule(),
    FunctionOnColumnRule(), ImplicitCastRule(), NoLimitRule(),
    DeepPaginationRule(), OrConditionRule(), SubqueryToJoinRule(),
]


class LocalOptimizer:
    """遍历规则，汇总 problems / index_ddls / optimized_sql。"""

    def __init__(self, rules: list[Rule] | None = None):
        self.rules = list(rules) if rules is not None else list(DEFAULT_RULES)

    def optimize(self, sql_info: SQLInfo, schema: Schema) -> AnalysisResult:
        ctx = RuleContext(sql_info=sql_info, schema=schema)
        problems, ddls, hit = [], [], []
        optimized = sql_info.raw_sql

        for rule in self.rules:
            found = self._safe(lambda: rule.check(ctx), rule.name, "check", [])
            if found:
                problems.extend(found)
                hit.append(rule.name)
            new_sql = self._safe(lambda: rule.rewrite(ctx), rule.name, "rewrite", None)
            if new_sql:
                optimized = new_sql
                if rule.name not in hit:
                    hit.append(rule.name)
            ddls.extend(self._safe(lambda: rule.ddls(ctx), rule.name, "ddls", []))

        return AnalysisResult(
            problems=problems,
            optimized_sql=optimized,
            index_ddls=ddls,
            explanation=self._explain(hit, sql_info, schema),
        )

    @staticmethod
    def _safe(fn, rule_name, phase, default):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - 单条规则异常不影响整体
            logger.warning("规则 %s 的 %s 阶段异常: %s", rule_name, phase, e)
            return default

    @staticmethod
    def _explain(hit: list[str], sql_info: SQLInfo, schema: Schema) -> str:
        if not hit:
            return "本地规则引擎：未发现明显问题。"
        table = sql_info.tables[0] if sql_info.tables else ""
        verified = bool(table) and schema.has_table(table)
        note = "" if verified else "（未连接数据库，索引相关结论未校验）"
        return "本地规则引擎命中规则: " + ", ".join(hit) + note
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_local_optimizer.py -q -o addopts=""`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sql_coach/local/engine.py tests/test_local_optimizer.py
git commit -m "feat(local): 新增本地规则引擎"
```

---

## Task 8: 优化器分流

**Files:**
- Create: `sql_coach/optimizer.py`
- Test: `tests/test_optimizer_routing.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_optimizer_routing.py`：

```python
"""优化器分流测试。"""
from sql_coach.models import Config, DBConfig, Complexity
from sql_coach.optimizer import select_optimizer


class FakeAI:
    def name(self):
        return "deepseek"

    def analyze(self, sql_info, explain_result, on_chunk=None):
        raise AssertionError("不应被调用")


def make_config(mode):
    return Config(db=DBConfig(host="h", port=3306, user="u", password="p", database="d"),
                  model="deepseek", deepseek_api_key="k", openai_api_key="",
                  ollama_url="http://x", benchmark_runs=3, mock=False, optimizer_mode=mode)


def test_mode_local_never_creates_ai():
    called = {"n": 0}

    def factory():
        called["n"] += 1
        return FakeAI()

    opt, name = select_optimizer(make_config("local"), Complexity("complex", 20), factory)
    assert name == "local"
    assert called["n"] == 0


def test_mode_ai_uses_ai_engine():
    opt, name = select_optimizer(make_config("ai"), Complexity("simple", 0), lambda: FakeAI())
    assert name == "deepseek"


def test_auto_routes_simple_to_local():
    opt, name = select_optimizer(make_config("auto"), Complexity("simple", 0), lambda: FakeAI())
    assert name == "local"


def test_auto_routes_medium_to_local():
    opt, name = select_optimizer(make_config("auto"), Complexity("medium", 5), lambda: FakeAI())
    assert name == "local"


def test_auto_routes_complex_to_ai():
    opt, name = select_optimizer(make_config("auto"), Complexity("complex", 12), lambda: FakeAI())
    assert name == "deepseek"
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_optimizer_routing.py -q -o addopts=""`
Expected: FAIL（`ModuleNotFoundError: sql_coach.optimizer`）

- [ ] **Step 3: 实现**

创建 `sql_coach/optimizer.py`：

```python
"""优化器分流：本地规则引擎 vs AI 引擎，产出同一种 AnalysisResult。"""
from typing import Callable, Optional

from .models import Config, SQLInfo, ExplainResult, AnalysisResult, Complexity
from .local.engine import LocalOptimizer
from .local.schema import Schema


class AIOptimizerAdapter:
    """把现有 AIEngine 适配成统一 Optimizer 接口。"""

    def __init__(self, engine):
        self.engine = engine

    def name(self) -> str:
        return self.engine.name()

    def optimize(self, sql_info: SQLInfo, explain_result: Optional[ExplainResult],
                 schema: Schema, on_chunk: Optional[Callable[[str], None]] = None) -> AnalysisResult:
        return self.engine.analyze(sql_info, explain_result, on_chunk=on_chunk)


class LocalOptimizerAdapter:
    """把 LocalOptimizer 适配成统一 Optimizer 接口。"""

    def __init__(self, engine: Optional[LocalOptimizer] = None):
        self.engine = engine or LocalOptimizer()

    def name(self) -> str:
        return "local"

    def optimize(self, sql_info: SQLInfo, explain_result: Optional[ExplainResult],
                 schema: Schema, on_chunk: Optional[Callable[[str], None]] = None) -> AnalysisResult:
        return self.engine.optimize(sql_info, schema)


def select_optimizer(config: Config, complexity: Optional[Complexity],
                     ai_factory: Callable[[], object]):
    """返回 (optimizer, engine_name)。

    ai_factory 是零参可调用对象，只在真正需要 AI 时才被调用，
    这样纯本地模式下不会创建 AI 客户端（也就不需要 API Key）。
    """
    mode = (getattr(config, "optimizer_mode", "auto") or "auto").lower()
    if mode == "local":
        return LocalOptimizerAdapter(), "local"
    if mode == "ai":
        engine = ai_factory()
        return AIOptimizerAdapter(engine), engine.name()
    # auto
    if complexity is not None and complexity.level in ("simple", "medium"):
        return LocalOptimizerAdapter(), "local"
    engine = ai_factory()
    return AIOptimizerAdapter(engine), engine.name()
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_optimizer_routing.py -q -o addopts=""`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sql_coach/optimizer.py tests/test_optimizer_routing.py
git commit -m "feat(optimizer): 新增本地/AI 分流路由"
```

---

## Task 9: 集成到 SQLCoach.analyze()

**Files:**
- Modify: `sql_coach/coach.py`
- Test: `tests/test_coach.py`（追加）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_coach.py` 末尾追加：

```python
def test_coach_routes_simple_sql_to_local():
    """auto 模式下简单 SQL 走本地引擎，不创建 AI 客户端。"""
    from sql_coach.models import Config, DBConfig
    from sql_coach.coach import SQLCoach
    from unittest.mock import patch

    db = DBConfig(host="h", port=3306, user="u", password="p", database="d")
    config = Config(db=db, model="deepseek", deepseek_api_key="", openai_api_key="",
                    ollama_url="http://x", benchmark_runs=3, mock=False, optimizer_mode="auto")
    with patch("sql_coach.coach.DBConnector") as db_cls, \
         patch("sql_coach.coach.create_ai_engine") as ai_factory:
        mock_db = db_cls.return_value
        mock_db.is_connected.return_value = False
        coach = SQLCoach(config, use_cache=False)
        report = coach.analyze("SELECT * FROM orders WHERE status='pending'")
        assert report.engine_used == "local"
        assert report.complexity is not None
        assert ai_factory.call_count == 0


def test_coach_routes_complex_sql_to_ai():
    from sql_coach.models import Config, DBConfig
    from sql_coach.coach import SQLCoach
    from sql_coach.models import AnalysisResult
    from unittest.mock import patch, MagicMock

    db = DBConfig(host="h", port=3306, user="u", password="p", database="d")
    config = Config(db=db, model="deepseek", deepseek_api_key="k", openai_api_key="",
                    ollama_url="http://x", benchmark_runs=3, mock=False, optimizer_mode="auto")
    with patch("sql_coach.coach.DBConnector") as db_cls, \
         patch("sql_coach.coach.create_ai_engine") as ai_factory:
        db_cls.return_value.is_connected.return_value = False
        mock_ai = MagicMock()
        mock_ai.name.return_value = "deepseek"
        mock_ai.analyze.return_value = AnalysisResult(
            problems=[], optimized_sql="SELECT 1", index_ddls=[], explanation="ok")
        ai_factory.return_value = mock_ai

        coach = SQLCoach(config, use_cache=False)
        sql = ("SELECT ROW_NUMBER() OVER (ORDER BY a.id) FROM a "
               "JOIN b ON a.id=b.id JOIN c ON b.id=c.id")
        report = coach.analyze(sql)
        assert report.engine_used == "deepseek"
        assert mock_ai.analyze.called
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_coach.py -q -o addopts="" -k "routes"`
Expected: FAIL（`AttributeError: 'Report' object has no attribute 'engine_used'`）

- [ ] **Step 3: 实现**

修改 `sql_coach/coach.py`：

顶部 import 增加：

```python
from .models import (
    Config, SQLInfo, ExplainResult, AnalysisResult, BenchmarkResult, Complexity
)
from .local.complexity import ComplexityScorer
from .local.schema import Schema, SchemaProvider
from .optimizer import select_optimizer
```

`Report` 增加字段：

```python
@dataclass
class Report:
    """Final analysis report."""
    sql_info: SQLInfo
    explain: Optional[ExplainResult]
    analysis: AnalysisResult
    benchmark: Optional[BenchmarkResult]
    engine_used: str = "ai"
    complexity: Optional[Complexity] = None
```

`__init__` 改为（AI 引擎改为惰性创建，schema provider 注入 db）：

```python
    def __init__(self, config: Config, use_cache: bool = True):
        self.config = config
        if config.mock:
            self.db = MockConnector()
        else:
            self.db = DBConnector(config.db)
        self._ai = None
        self.schema_provider = SchemaProvider(self.db)
        if use_cache and not config.mock:
            self.cache = AnalysisCache()
        else:
            self.cache = None

    @property
    def ai(self):
        """惰性创建 AI 引擎：纯本地模式不需要 API Key。"""
        if self._ai is None:
            self._ai = create_ai_engine(self.config.model, self.config)
        return self._ai
```

`analyze` 中替换第 3 步（AI 分析）为评分 + 分流：

```python
        # Step 1.5: 读取 schema（尽力而为，连不上库时为空）
        schema = Schema()
        if not self.config.mock and self.db.is_connected():
            schema = self.schema_provider.load(sql_info.tables)

        # ... Step 2 EXPLAIN 保持不变 ...

        # Step 3: 评分 + 分流（本地规则引擎 / AI）
        complexity = ComplexityScorer(self.config.complexity_threshold).score(sql_info)
        optimizer, engine_name = select_optimizer(
            self.config, complexity, lambda: self.ai)

        if on_stage:
            on_stage("ai", 3, 4, "start")
        t = time.perf_counter()
        analysis = None
        if engine_name != "local" and self.cache:
            analysis = self.cache.get(sql)
        if analysis is not None:
            logger.debug('timing optimize: %.2f ms (cached)', (time.perf_counter() - t) * 1000)
        else:
            analysis = optimizer.optimize(sql_info, explain, schema, on_chunk=on_chunk)
            logger.debug('timing optimize: %.2f ms', (time.perf_counter() - t) * 1000)
            if engine_name != "local" and self.cache:
                self.cache.put(sql, analysis)
        if on_stage:
            on_stage("ai", 3, 4, "done")
```

`return Report(...)` 增加两个字段：

```python
        return Report(
            sql_info=sql_info,
            explain=explain,
            analysis=analysis,
            benchmark=benchmark,
            engine_used=engine_name,
            complexity=complexity,
        )
```

注意：`schema` 变量要在 Step 1.5 定义后、Step 2 之后仍可用，因此把 schema 读取放在 parse 之后、EXPLAIN 之前。

- [ ] **Step 4: 运行确认通过（含全部既有 coach 测试）**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_coach.py -q -o addopts=""`
Expected: PASS（含 `test_coach_analyze_full_flow` 等既有用例）

- [ ] **Step 5: 提交**

```bash
git add sql_coach/coach.py tests/test_coach.py
git commit -m "feat(coach): 集成复杂度评分与本地/AI 分流"
```

---

## Task 10: 启动自检 checks

**Files:**
- Modify: `sql_coach/config.py`（把 `ENV_TEMPLATE` 从 `cli.py` 迁入，供自检复用）
- Create: `sql_coach/diagnostics/__init__.py`
- Create: `sql_coach/diagnostics/checks.py`
- Test: `tests/test_diagnostics.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_diagnostics.py`：

```python
"""启动自检测试。"""
from sql_coach.models import Config, DBConfig
from sql_coach.diagnostics.checks import (
    check_env_file, check_ai, check_runtime, run_all, CheckResult,
)


def make_config(model="deepseek", key="sk-real", mock=False):
    return Config(db=DBConfig(host="localhost", port=3306, user="root", password="", database="test"),
                  model=model, deepseek_api_key=key, openai_api_key="",
                  ollama_url="http://localhost:11434", benchmark_runs=3, mock=mock)


def test_check_env_file_missing(tmp_path):
    missing = str(tmp_path / "nope.env")
    r = check_env_file(missing)
    assert r.status == "warn"
    assert r.auto_fixable is True


def test_check_env_file_exists(tmp_path):
    p = tmp_path / ".env"
    p.write_text("AI_MODEL=deepseek\n", encoding="utf-8")
    assert check_env_file(str(p)).status == "ok"


def test_check_ai_missing_key():
    r = check_ai(make_config(key=""))
    assert r.status == "fail"
    assert "API Key" in r.message or "Key" in r.message


def test_check_ai_placeholder_key():
    r = check_ai(make_config(key="sk-xxx"))
    assert r.status == "fail"


def test_check_ai_ok():
    assert check_ai(make_config(key="sk-abcdef123456")).status == "ok"


def test_check_ai_ollama_ok():
    assert check_ai(make_config(model="ollama")).status == "ok"


def test_check_ai_mock_mode():
    assert check_ai(make_config(mock=True)).status == "warn"


def test_check_runtime_ok():
    assert check_runtime().status == "ok"


def test_run_all_returns_four_results(tmp_path):
    results = run_all(make_config(mock=True), str(tmp_path / ".env"))
    assert len(results) == 4
    assert all(isinstance(r, CheckResult) for r in results)
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_diagnostics.py -q -o addopts=""`
Expected: FAIL（`ModuleNotFoundError: sql_coach.diagnostics`）

- [ ] **Step 3: 实现**

在 `sql_coach/config.py` 顶部加入模板常量（从 `cli.py` 迁移，内容一致）：

```python
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
DEEPSEEK_MODEL=deepseek-chat

# OpenAI
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1

# Ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b

# 优化器分流: auto / local / ai
OPTIMIZER_MODE=auto
# 复杂度阈值（>= 该值走 AI）
COMPLEXITY_THRESHOLD=8

# 通用
BENCHMARK_RUNS=3
LOG_LEVEL=INFO
"""
```

创建 `sql_coach/diagnostics/__init__.py`（空文件）。

创建 `sql_coach/diagnostics/checks.py`：

```python
"""启动环境自检：逐项检查并返回结构化结果。"""
import os
import sys
from dataclasses import dataclass

from ..models import Config


@dataclass
class CheckResult:
    name: str
    status: str        # ok / warn / fail
    message: str
    fix_hint: str = ""
    auto_fixable: bool = False


def check_env_file(env_path: str) -> CheckResult:
    if os.path.exists(env_path):
        return CheckResult("配置文件 .env", "ok", f"已找到 {env_path}")
    return CheckResult("配置文件 .env", "warn", f"未找到 {env_path}",
                       fix_hint="将自动生成模板，请填写数据库与 API Key",
                       auto_fixable=True)


def check_mysql(config: Config) -> CheckResult:
    if config.mock:
        return CheckResult("MySQL 连接", "warn", "当前为模拟模式，跳过数据库连接")
    from ..db.connector import DBConnector
    conn = DBConnector(config.db)
    try:
        ok = conn.connect()
    finally:
        conn.close()
    if ok:
        return CheckResult(
            "MySQL 连接", "ok",
            f"已连接 {config.db.host}:{config.db.port}/{config.db.database}")
    return CheckResult("MySQL 连接", "fail", "无法连接 MySQL（本地算法仍可用）",
                       fix_hint=_mysql_hint())


def _mysql_hint() -> str:
    if sys.platform.startswith("win"):
        return ("安装: winget install Oracle.MySQL    或    "
                "Docker: docker run -d -p 3306:3306 -e MYSQL_ROOT_PASSWORD=yourpass mysql:8")
    if sys.platform == "darwin":
        return "安装: brew install mysql && brew services start mysql"
    return ("安装: sudo apt-get install mysql-server    或    "
            "Docker: docker run -d -p 3306:3306 -e MYSQL_ROOT_PASSWORD=yourpass mysql:8")


def check_ai(config: Config) -> CheckResult:
    if config.mock:
        return CheckResult("AI 配置", "warn", "当前为模拟模式，不调用 AI")
    if config.model == "ollama":
        return CheckResult("AI 配置", "ok", f"Ollama 本地模型: {config.ollama_url}")
    key = config.deepseek_api_key if config.model == "deepseek" else config.openai_api_key
    if not key or not key.strip() or key.strip() == "sk-xxx":
        return CheckResult("AI 配置", "fail",
                           f"{config.model} 未配置有效 API Key（复杂 SQL 需要）",
                           fix_hint="在 .env 填写对应 API Key，或在设置里改为本地模式")
    return CheckResult("AI 配置", "ok", f"{config.model} API Key 已配置")


def check_runtime() -> CheckResult:
    v = sys.version_info
    if (v.major, v.minor) < (3, 10):
        return CheckResult("运行环境", "fail", f"Python {v.major}.{v.minor} 过低，需 3.10+")
    mode = "打包运行" if getattr(sys, "frozen", False) else "源码运行"
    return CheckResult("运行环境", "ok", f"Python {v.major}.{v.minor}.{v.micro}（{mode}）")


def run_all(config: Config, env_path: str = ".env") -> list[CheckResult]:
    return [check_env_file(env_path), check_mysql(config), check_ai(config), check_runtime()]
```

同时修改 `sql_coach/cli.py`：删除本文件里的 `ENV_TEMPLATE` 定义，改为 `from .config import ENV_TEMPLATE, load_config`。

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_diagnostics.py tests/test_cli.py -q -o addopts=""`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sql_coach/config.py sql_coach/cli.py sql_coach/diagnostics/ tests/test_diagnostics.py
git commit -m "feat(diagnostics): 新增启动环境自检 checks"
```

---

## Task 11: 分层修复与结果汇总

**Files:**
- Create: `sql_coach/diagnostics/installer.py`
- Create: `sql_coach/diagnostics/report.py`
- Test: `tests/test_installer.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_installer.py`：

```python
"""分层修复测试。"""
from sql_coach.diagnostics.checks import CheckResult
from sql_coach.diagnostics.installer import apply_auto_fixes
from sql_coach.diagnostics.report import format_results


def test_apply_auto_fixes_creates_env(tmp_path):
    env_path = tmp_path / ".env"
    results = [CheckResult("配置文件 .env", "warn", "缺失", auto_fixable=True)]
    outcomes = apply_auto_fixes(results, str(env_path))
    assert env_path.exists()
    assert any(o.applied for o in outcomes)
    assert "OPTIMIZER_MODE" in env_path.read_text(encoding="utf-8")


def test_apply_auto_fixes_skips_non_autofixable(tmp_path):
    env_path = tmp_path / ".env"
    results = [CheckResult("MySQL 连接", "fail", "连不上", fix_hint="winget ...",
                           auto_fixable=False)]
    outcomes = apply_auto_fixes(results, str(env_path))
    assert outcomes == []
    assert not env_path.exists()


def test_format_results_contains_status_and_hint():
    results = [
        CheckResult("配置文件 .env", "ok", "已找到"),
        CheckResult("MySQL 连接", "fail", "连不上", fix_hint="winget install Oracle.MySQL"),
    ]
    text = format_results(results)
    assert "配置文件 .env" in text
    assert "winget install Oracle.MySQL" in text
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_installer.py -q -o addopts=""`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

创建 `sql_coach/diagnostics/installer.py`：

```python
"""分层修复：能安全自动做的自动做，系统级软件只给指引。"""
import os
from dataclasses import dataclass

from ..config import ENV_TEMPLATE
from .checks import CheckResult


@dataclass
class FixOutcome:
    name: str
    applied: bool
    message: str


def apply_auto_fixes(results: list[CheckResult], env_path: str = ".env") -> list[FixOutcome]:
    """只处理 auto_fixable 的项；系统级软件一律不动。"""
    outcomes = []
    for r in results:
        if r.status == "ok" or not r.auto_fixable:
            continue
        if r.name.startswith("配置文件"):
            outcomes.append(_create_env_file(env_path))
    return outcomes


def _create_env_file(env_path: str) -> FixOutcome:
    if os.path.exists(env_path):
        return FixOutcome("配置文件 .env", False, "已存在，跳过")
    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(ENV_TEMPLATE)
        return FixOutcome("配置文件 .env", True, f"已生成模板: {env_path}")
    except OSError as e:
        return FixOutcome("配置文件 .env", False, f"生成失败: {e}")


def copy_hint(hint: str) -> bool:
    """把修复指引复制到剪贴板，失败返回 False。"""
    try:
        import pyperclip
        pyperclip.copy(hint)
        return True
    except Exception:  # noqa: BLE001
        return False
```

创建 `sql_coach/diagnostics/report.py`：

```python
"""自检结果汇总（纯文本，供 CLI 使用）。"""
from .checks import CheckResult

_ICONS = {"ok": "✓", "warn": "!", "fail": "✗"}


def format_results(results: list[CheckResult]) -> str:
    lines = ["环境自检结果:"]
    for r in results:
        lines.append(f"  [{_ICONS.get(r.status, '?')}] {r.name}: {r.message}")
        if r.fix_hint:
            lines.append(f"        → {r.fix_hint}")
    return "\n".join(lines)
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_installer.py -q -o addopts=""`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sql_coach/diagnostics/installer.py sql_coach/diagnostics/report.py tests/test_installer.py
git commit -m "feat(diagnostics): 新增分层修复与结果汇总"
```

---

## Task 12: CLI 新增 --engine 与 doctor

**Files:**
- Modify: `sql_coach/cli.py`
- Test: `tests/test_cli.py`（追加）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_cli.py` 末尾追加：

```python
def test_cli_has_doctor_command():
    from click.testing import CliRunner
    from sql_coach.cli import main
    result = CliRunner().invoke(main, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "自检" in result.output or "doctor" in result.output.lower()


def test_cli_analyze_has_engine_option():
    from click.testing import CliRunner
    from sql_coach.cli import main
    result = CliRunner().invoke(main, ["analyze", "--help"])
    assert "--engine" in result.output
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_cli.py -q -o addopts="" -k "doctor or engine_option"`
Expected: FAIL（`--engine` 不在 help 中 / `doctor` 命令不存在）

- [ ] **Step 3: 实现**

在 `sql_coach/cli.py` 的 `analyze` 命令上增加选项（放在 `--no-cache` 之后）：

```python
@click.option("--engine", "-e", default=None,
              type=click.Choice(["auto", "local", "ai"]),
              help="优化引擎: auto/local/ai")
def analyze(sql, file, model, mock, no_cache, engine):
```

在 `analyze` 函数体里，`config = load_config(mock=mock)` 之后追加：

```python
    if engine:
        config.optimizer_mode = engine
```

在打印报告之后、`_interactive_choice` 之前追加引擎信息行：

```python
    level = report.complexity.level if report.complexity else "-"
    score = report.complexity.score if report.complexity else "-"
    console.print(f"[dim]优化引擎: {report.engine_used} | 复杂度: {level} (score {score})[/dim]")
```

新增 `doctor` 命令（放在 `cache` group 之前）：

```python
@main.command()
@click.option("--fix", is_flag=True, help="自动修复可安全修复的项（如生成 .env 模板）")
def doctor(fix):
    """环境自检：检查 .env / MySQL / AI 配置 / 运行环境。"""
    from .diagnostics.checks import run_all
    from .diagnostics.installer import apply_auto_fixes
    from .diagnostics.report import format_results

    config = load_config()
    env_path = ".env"
    results = run_all(config, env_path)
    if fix:
        for o in apply_auto_fixes(results, env_path):
            console.print(f"[cyan]{o.message}[/cyan]")
        results = run_all(config, env_path)
    console.print(format_results(results))
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_cli.py -q -o addopts=""`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sql_coach/cli.py tests/test_cli.py
git commit -m "feat(cli): 新增 --engine 选项与 doctor 自检命令"
```

---

## Task 13: 交互模式展示引擎与复杂度

**Files:**
- Modify: `sql_coach/interactive.py`
- Test: `tests/test_cli.py`（追加，复用 interactive 的 analyze_one）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_cli.py` 末尾追加：

```python
def test_interactive_analyze_one_shows_engine(capsys):
    from unittest.mock import MagicMock
    from sql_coach.interactive import analyze_one
    from sql_coach.models import Config, DBConfig, AnalysisResult, SQLInfo, Complexity
    from sql_coach.coach import Report

    config = Config(db=DBConfig("h", 3306, "u", "p", "d"), model="deepseek",
                    deepseek_api_key="k", openai_api_key="", ollama_url="http://x",
                    benchmark_runs=3, mock=True)
    coach = MagicMock()
    coach.analyze.return_value = Report(
        sql_info=SQLInfo(raw_sql="SELECT 1", sql_type="SELECT", tables=[], columns=[],
                         where_conditions=[], join_tables=[], order_by=[]),
        explain=None,
        analysis=AnalysisResult(problems=[], optimized_sql="SELECT 1",
                                index_ddls=[], explanation="ok"),
        benchmark=None,
        engine_used="local",
        complexity=Complexity(level="simple", score=0, reasons=[]),
    )
    analyze_one(coach, "SELECT 1")
    out = capsys.readouterr().out
    assert "local" in out
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_cli.py -q -o addopts="" -k "shows_engine"`
Expected: FAIL（输出中无 `local`）

- [ ] **Step 3: 实现**

在 `sql_coach/interactive.py` 的 `analyze_one` 里，`console.print(format_report(...))` 之后、`# 摘要` 之前追加：

```python
    level = report.complexity.level if report.complexity else "-"
    console.print(f"[dim]优化引擎: {report.engine_used} | 复杂度: {level}[/dim]")
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_cli.py -q -o addopts=""`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sql_coach/interactive.py tests/test_cli.py
git commit -m "feat(cli): 交互模式展示优化引擎与复杂度"
```

---

## Task 14: 设置对话框（新增分流配置 + 修复丢字段 bug）

**Files:**
- Modify: `gui/widgets/settings_dialog.py`
- Test: `tests/test_settings_dialog.py`（追加）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_settings_dialog.py` 末尾追加：

```python
def test_save_preserves_unknown_keys_and_comments(tmp_path):
    """保存时不应丢弃模板里的其他键与注释。"""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# 注释行\nDB_HOST=localhost\nDEEPSEEK_BASE_URL=https://api.deepseek.com\n"
        "DEEPSEEK_MODEL=deepseek-chat\nLOG_LEVEL=INFO\n", encoding="utf-8")
    from PySide6.QtWidgets import QApplication
    from gui.widgets.settings_dialog import SettingsDialog
    app = QApplication.instance() or QApplication([])
    dlg = SettingsDialog(env_path=str(env_path))
    dlg.host_edit.setText("127.0.0.1")
    dlg._save_to_env()
    text = env_path.read_text(encoding="utf-8")
    assert "# 注释行" in text
    assert "DEEPSEEK_BASE_URL=https://api.deepseek.com" in text
    assert "LOG_LEVEL=INFO" in text
    assert "DB_HOST=127.0.0.1" in text


def test_save_writes_optimizer_fields(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("DB_HOST=localhost\n", encoding="utf-8")
    from PySide6.QtWidgets import QApplication
    from gui.widgets.settings_dialog import SettingsDialog
    app = QApplication.instance() or QApplication([])
    dlg = SettingsDialog(env_path=str(env_path))
    dlg._save_to_env()
    text = env_path.read_text(encoding="utf-8")
    assert "OPTIMIZER_MODE=" in text
    assert "COMPLEXITY_THRESHOLD=" in text
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_settings_dialog.py -q -o addopts="" -k "preserves or optimizer_fields"`
Expected: FAIL（`OPTIMIZER_MODE` 未写入 / 注释被清空）

- [ ] **Step 3: 实现**

修改 `gui/widgets/settings_dialog.py`：

a) `_ENV_KEYS` 增加两个键：

```python
_ENV_KEYS = [
    "DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME",
    "AI_MODEL", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
    "OLLAMA_URL", "OPTIMIZER_MODE", "COMPLEXITY_THRESHOLD",
    "BENCHMARK_RUNS",
]
```

b) 在 import 增加 `QComboBox`：

```python
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QVBoxLayout, QWidget,
)
```

c) 在"通用"分组里，`benchmark_runs_edit` 之前插入两个控件：

```python
        self.optimizer_mode_combo = QComboBox()
        self.optimizer_mode_combo.addItems(["auto", "local", "ai"])
        common_form.addRow("优化器分流:", self.optimizer_mode_combo)
        self.threshold_edit = QLineEdit()
        common_form.addRow("复杂度阈值:", self.threshold_edit)
```

d) `_load_from_env` 末尾追加：

```python
        mode = _get_env("OPTIMIZER_MODE", "auto").lower()
        idx = self.optimizer_mode_combo.findText(mode)
        self.optimizer_mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.threshold_edit.setText(_get_env("COMPLEXITY_THRESHOLD", "8"))
```

e) `get_config_dict` 的返回字典追加：

```python
            "OPTIMIZER_MODE": self.optimizer_mode_combo.currentText(),
            "COMPLEXITY_THRESHOLD": self.threshold_edit.text() or "8",
```

f) 用"就地更新、保留未知键与注释"的实现替换 `_save_to_env`：

```python
    def _save_to_env(self) -> None:
        """就地更新 .env：只覆盖已知键，保留注释与其他键。"""
        config = self.get_config_dict()
        existing_lines: list[str] = []
        if os.path.exists(self.env_path):
            with open(self.env_path, "r", encoding="utf-8") as f:
                existing_lines = f.read().splitlines()

        written: set[str] = set()
        out: list[str] = []
        for line in existing_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                out.append(line)
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in config:
                out.append(f"{key}={config[key]}")
                written.add(key)
            else:
                out.append(line)
        for key in _ENV_KEYS:
            if key not in written and key in config:
                out.append(f"{key}={config[key]}")

        with open(self.env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_settings_dialog.py -q -o addopts=""`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add gui/widgets/settings_dialog.py tests/test_settings_dialog.py
git commit -m "fix(gui): 设置保存不再丢字段，并新增分流配置项"
```

---

## Task 15: 报告区显示引擎与复杂度徽章

**Files:**
- Modify: `gui/widgets/report_view.py`
- Test: `tests/test_report_view.py`（追加）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_report_view.py` 末尾追加：

```python
def test_report_view_shows_engine_badge():
    from PySide6.QtWidgets import QApplication, QLabel
    from sql_coach.coach import Report
    from sql_coach.models import SQLInfo, AnalysisResult, Complexity
    from gui.widgets.report_view import ReportView

    app = QApplication.instance() or QApplication([])
    view = ReportView()
    report = Report(
        sql_info=SQLInfo(raw_sql="SELECT 1", sql_type="SELECT", tables=[], columns=[],
                         where_conditions=[], join_tables=[], order_by=[]),
        explain=None,
        analysis=AnalysisResult(problems=[], optimized_sql="SELECT 1",
                                index_ddls=[], explanation="ok"),
        benchmark=None,
        engine_used="local",
        complexity=Complexity(level="simple", score=0, reasons=[]),
    )
    view.set_report(report)
    texts = [w.text() for w in view.findChildren(QLabel)]
    assert any("本地" in t for t in texts)
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_report_view.py -q -o addopts="" -k "engine_badge"`
Expected: FAIL（无包含"本地"的标签）

- [ ] **Step 3: 实现**

修改 `gui/widgets/report_view.py`：在 `set_report` 的 `_clear_layout()` 之后、`# 原始 SQL` 之前插入徽章：

```python
        # 引擎 / 复杂度徽章
        self._layout.addWidget(self._engine_badge(report))
```

并新增方法：

```python
    def _engine_badge(self, report) -> QLabel:
        engine = "本地规则" if report.engine_used == "local" else report.engine_used
        level = "-"
        if report.complexity is not None:
            level = {"simple": "简单", "medium": "中等", "complex": "复杂"}.get(
                report.complexity.level, report.complexity.level)
            level = f"{level} ({report.complexity.score})"
        label = QLabel(f"优化引擎：{engine}    复杂度：{level}")
        label.setStyleSheet(
            "color: #1e66f5; font-weight: bold; padding: 4px 0;")
        return label
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_report_view.py -q -o addopts=""`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add gui/widgets/report_view.py tests/test_report_view.py
git commit -m "feat(gui): 报告区展示优化引擎与复杂度徽章"
```

---

## Task 16: 自检对话框 + 启动接入

**Files:**
- Create: `gui/widgets/diagnostics_dialog.py`
- Modify: `gui/app.py`
- Test: `tests/test_diagnostics_dialog.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_diagnostics_dialog.py`：

```python
"""自检对话框测试。"""
from PySide6.QtWidgets import QApplication, QLabel

from sql_coach.diagnostics.checks import CheckResult
from gui.widgets.diagnostics_dialog import DiagnosticsDialog


def _app():
    return QApplication.instance() or QApplication([])


def test_dialog_lists_results():
    _app()
    results = [
        CheckResult("配置文件 .env", "ok", "已找到"),
        CheckResult("MySQL 连接", "fail", "连不上", fix_hint="winget install Oracle.MySQL"),
    ]
    dlg = DiagnosticsDialog(results, env_path=".env")
    texts = " ".join(w.text() for w in dlg.findChildren(QLabel))
    assert "MySQL 连接" in texts
    assert "winget install Oracle.MySQL" in texts


def test_dialog_autofix_button_only_when_needed():
    _app()
    no_fix = DiagnosticsDialog([CheckResult("运行环境", "ok", "ok")], env_path=".env")
    assert no_fix.fix_button.isEnabled() is False
    with_fix = DiagnosticsDialog(
        [CheckResult("配置文件 .env", "warn", "缺失", auto_fixable=True)], env_path=".env")
    assert with_fix.fix_button.isEnabled() is True
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_diagnostics_dialog.py -q -o addopts=""`
Expected: FAIL（`ModuleNotFoundError: gui.widgets.diagnostics_dialog`）

- [ ] **Step 3: 实现**

创建 `gui/widgets/diagnostics_dialog.py`：

```python
# gui/widgets/diagnostics_dialog.py
"""环境自检对话框。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from sql_coach.diagnostics.checks import CheckResult, run_all
from sql_coach.diagnostics.installer import apply_auto_fixes, copy_hint
from sql_coach.diagnostics.report import format_results

_ICONS = {"ok": "✓", "warn": "!", "fail": "✗"}
_COLORS = {"ok": "#40a02b", "warn": "#df8e1d", "fail": "#d20f39"}

SKIP_MARKER = Path.home() / ".sql-coach" / ".skip_diagnostics"


class DiagnosticsDialog(QDialog):
    """展示自检结果，提供"自动修复"与"复制命令"。"""

    def __init__(self, results: list[CheckResult], env_path: str = ".env",
                 config=None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.results = results
        self.env_path = env_path
        self.config = config
        self.setWindowTitle("环境自检")
        self.resize(620, 460)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("启动环境自检")
        f = title.font(); f.setBold(True); f.setPointSize(12); title.setFont(f)
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self._inner_layout = QVBoxLayout(inner)
        self._inner_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        self._render()

        btn_row = QHBoxLayout()
        self.fix_button = QPushButton("🔧 自动修复可修复项")
        self.fix_button.setEnabled(any(r.auto_fixable and r.status != "ok"
                                       for r in self.results))
        self.fix_button.clicked.connect(self._on_fix)
        btn_row.addWidget(self.fix_button)

        self.copy_button = QPushButton("📋 复制安装命令")
        self.copy_button.clicked.connect(self._on_copy)
        btn_row.addWidget(self.copy_button)

        btn_row.addStretch(1)
        self.dont_ask = QCheckBox("不再提示")
        btn_row.addWidget(self.dont_ask)
        skip = QPushButton("跳过")
        skip.clicked.connect(self._on_skip)
        btn_row.addWidget(skip)
        layout.addLayout(btn_row)

    def _render(self) -> None:
        while self._inner_layout.count():
            item = self._inner_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for r in self.results:
            head = QLabel(f"{_ICONS.get(r.status, '?')}  {r.name}: {r.message}")
            head.setStyleSheet(f"color: {_COLORS.get(r.status, '#888')}; font-weight: bold;")
            head.setWordWrap(True)
            self._inner_layout.addWidget(head)
            if r.fix_hint:
                hint = QLabel(f"    → {r.fix_hint}")
                hint.setStyleSheet("color: #666;")
                hint.setWordWrap(True)
                hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
                self._inner_layout.addWidget(hint)

    def _on_fix(self) -> None:
        apply_auto_fixes(self.results, self.env_path)
        if self.config is not None:
            self.results = run_all(self.config, self.env_path)
        else:
            self.results = [CheckResult(r.name, "ok", r.message) if r.auto_fixable
                            else r for r in self.results]
        self.fix_button.setEnabled(False)
        self._render()

    def _on_copy(self) -> None:
        hints = "\n".join(r.fix_hint for r in self.results if r.fix_hint)
        if hints and copy_hint(hints):
            self.copy_button.setText("✅ 已复制")

    def _on_skip(self) -> None:
        if self.dont_ask.isChecked():
            try:
                SKIP_MARKER.parent.mkdir(parents=True, exist_ok=True)
                SKIP_MARKER.touch()
            except OSError:
                pass
        self.reject()

    def summary_text(self) -> str:
        return format_results(self.results)
```

修改 `gui/app.py`：在 `window = MainWindow(...)` 之前插入自检（跳过标记存在时不弹；仅当存在非 ok 项时弹）：

```python
    from pathlib import Path
    from sql_coach.diagnostics.checks import run_all
    from gui.widgets.diagnostics_dialog import DiagnosticsDialog, SKIP_MARKER

    if not SKIP_MARKER.exists():
        results = run_all(config, env_path)
        if any(r.status != "ok" for r in results):
            DiagnosticsDialog(results, env_path=env_path, config=config).exec()
```

并在 `tests/test_diagnostics_dialog.py` 追加：

```python
def test_dialog_skip_writes_marker(tmp_path, monkeypatch):
    _app()
    from gui.widgets import diagnostics_dialog as mod
    monkeypatch.setattr(mod, "SKIP_MARKER", tmp_path / ".skip_diagnostics")
    dlg = DiagnosticsDialog([CheckResult("运行环境", "ok", "ok")], env_path=".env")
    dlg.dont_ask.setChecked(True)
    dlg._on_skip()
    assert (tmp_path / ".skip_diagnostics").exists()
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_diagnostics_dialog.py tests/test_app_entry.py -q -o addopts=""`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add gui/widgets/diagnostics_dialog.py gui/app.py tests/test_diagnostics_dialog.py
git commit -m "feat(gui): 新增环境自检对话框并在启动时接入"
```

---

## Task 17: 单文件 onefile 打包与 CI

**Files:**
- Create: `sql-coach-onefile.spec`
- Modify: `.github/workflows/build-gui.yml`
- Modify: `.env.example`

- [ ] **Step 1: 创建 onefile spec**

创建 `sql-coach-onefile.spec`：

```python
# sql-coach-onefile.spec
# -*- mode: python ; coding: utf-8 -*-
"""SQL Coach GUI 单文件打包配置 (onefile)。"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('.env.example', '.')],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'matplotlib.backends.backend_qtagg',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'IPython', 'jedi', 'prompt_toolkit',
        'pytest', '_pytest', 'tkinter',
        'unittest', 'pydoc_data', 'test',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

- [ ] **Step 2: 更新 CI 构建 onefile（并保留 onedir 备选）**

把 `.github/workflows/build-gui.yml` 中 `jobs.build` 的 `steps` 整体替换为下面内容
（`matrix`、`Setup Linux display libraries`、`Setup Python` 等保持不变，这里给出替换后的完整 steps）：

```yaml
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

      - name: Setup Linux display libraries
        if: matrix.os == 'ubuntu-latest'
        run: |
          sudo apt-get update -y
          sudo apt-get install -y libxcb-xinerama0 libxkbcommon-x11-0 libegl1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0

      - name: Build with PyInstaller (onefile)
        run: pyinstaller sql-coach-onefile.spec --clean --noconfirm

      - name: Build with PyInstaller (onedir, fallback)
        run: pyinstaller sql-coach.spec --clean --noconfirm --distpath dist-onedir

      - name: Package (Windows)
        if: matrix.os == 'windows-latest'
        shell: pwsh
        run: |
          Compress-Archive -Path dist/sql-coach-gui.exe -DestinationPath dist/sql-coach-gui-windows.zip
          Compress-Archive -Path dist-onedir/sql-coach-gui -DestinationPath dist/sql-coach-gui-windows-onedir.zip

      - name: Package (macOS)
        if: matrix.os == 'macos-latest'
        run: |
          cd dist && tar -czvf sql-coach-gui-macos.tar.gz sql-coach-gui && cd ..
          cd dist-onedir && tar -czvf ../dist/sql-coach-gui-macos-onedir.tar.gz sql-coach-gui && cd ..

      - name: Package (Linux)
        if: matrix.os == 'ubuntu-latest'
        run: |
          cd dist && tar -czvf sql-coach-gui-linux.tar.gz sql-coach-gui && cd ..
          cd dist-onedir && tar -czvf ../dist/sql-coach-gui-linux-onedir.tar.gz sql-coach-gui && cd ..

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: build-${{ matrix.os }}
          path: |
            dist/*.zip
            dist/*.tar.gz

      - name: Release
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          files: |
            dist/*.zip
            dist/*.tar.gz
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

同时把 `matrix.include` 中的 `asset_name` 字段删除（改为通配后不再需要）：

```yaml
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: windows-latest
          - os: macos-latest
          - os: ubuntu-latest
```

- [ ] **Step 3: 更新 .env.example**

修改 `.env.example`，在 `# 通用` 之前插入：

```ini
# 优化器分流: auto / local / ai
OPTIMIZER_MODE=auto
# 复杂度阈值（>= 该值走 AI）
COMPLEXITY_THRESHOLD=8
```

- [ ] **Step 4: 本地验证 spec 可解析（不实际打包，避免耗时）**

Run:
```bash
./.venv/Scripts/python.exe -c "import ast, pathlib; ast.parse(pathlib.Path('sql-coach-onefile.spec').read_text(encoding='utf-8')); print('spec OK')"
```
Expected: `spec OK`

- [ ] **Step 5: 提交**

```bash
git add sql-coach-onefile.spec .github/workflows/build-gui.yml .env.example
git commit -m "build: 新增单文件 onefile 打包与 CI 产物"
```

---

## Task 18: 全量回归与文档更新

**Files:**
- Modify: `README.md`
- Modify: `USAGE.md`

- [ ] **Step 1: 跑全量测试**

Run:
```bash
./.venv/Scripts/python.exe -m pytest tests/ -q -o addopts=""
```
Expected: 全部通过（原有 134 + 新增用例）。任何失败都必须修复后再继续。

- [ ] **Step 2: 更新 README**

在 `README.md` 的"特性"列表中追加：

```markdown
- 本地规则引擎：简单/中等 SQL 毫秒级优化，复杂 SQL 才调用 AI（自动分流）
- 启动环境自检：自动检测 .env / MySQL / AI 配置，能安全修复的自动修复
```

在"技术栈"后追加"优化分流"小节，说明 `OPTIMIZER_MODE` 与 `COMPLEXITY_THRESHOLD` 两个配置项。

- [ ] **Step 3: 更新 USAGE.md**

在"三种使用模式"之后追加一节：

```markdown
## 优化引擎分流

SQL Coach 会自动判断 SQL 复杂度：

- **简单 / 中等** → 本地规则引擎（毫秒级，不联网）
- **复杂** → AI 大模型

可在 `.env` 中控制：

```ini
OPTIMIZER_MODE=auto     # auto / local / ai
COMPLEXITY_THRESHOLD=8  # 分数 >= 该值走 AI
```

也可在命令行临时指定：

```bash
sql-coach analyze --engine local "SELECT * FROM orders WHERE status='pending'"
```

## 环境自检

```bash
sql-coach doctor          # 检查 .env / MySQL / AI 配置 / 运行环境
sql-coach doctor --fix    # 自动修复可安全修复的项（如生成 .env 模板）
```
```

- [ ] **Step 4: 提交**

```bash
git add README.md USAGE.md
git commit -m "docs: 补充本地分流与启动自检说明"
```

---

## 完成标准

- `pytest tests/ -q -o addopts=""` 全绿
- 简单 SQL（如 `SELECT * FROM orders WHERE status='pending'`）在 `OPTIMIZER_MODE=auto` 下 `Report.engine_used == "local"` 且不创建 AI 客户端
- 复杂 SQL（3 表 + 窗口函数）走 AI
- `sql-coach doctor` 能列出 4 项检查结果；`--fix` 能生成 `.env` 模板
- `sql-coach-onefile.spec` 可解析，CI 同时产出单文件与 onedir 两种产物
- `ai/`、`engine/`、`report/`、`cache.py` 无改动；`db/` 仅新增只读 `query()`
