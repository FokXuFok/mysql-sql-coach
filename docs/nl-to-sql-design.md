# SQL Coach 自然语言转 SQL 模式设计文档

> 日期: 2026-10-12
> 状态: 设计中，待评审
> 关联: 在 `2026-10-11-local-optimizer-and-bootstrap-design.md`（本地规则引擎）基础上扩展

---

## 1. 概述

当前 SQL Coach 是"SQL 优化"模式：用户输入 SQL → 系统分析执行计划 → 输出优化建议、改写 SQL 和索引 DDL。本次新增"自然语言转 SQL"（NL-to-SQL）模式：用户输入自然语言描述（如"查询销售额最高的10个客户"），系统自动生成 SQL 语句、执行查询、展示结果。

### 目标

- 新增 NL-to-SQL 模式，**纯本地算法实现**，不调用 AI 大模型
- 利用现有 `SchemaProvider` 的表结构信息辅助实体映射
- 复用现有 `DBConnector` 执行生成的 SQL
- GUI 新增模式切换，CLI 新增子命令
- 生成的 SQL 经过现有本地规则引擎的校验

### 非目标

- 不做通用自然语言理解（NLU），仅覆盖**基于 schema 的结构化查询场景**
- 不做多表 JOIN 的复杂语义推断（后续演进方向）
- 不调用任何 AI/LLM 接口（关键约束）
- 不改动现有优化模式的功能逻辑

### 与现有模式的关系

```
现有模式（优化）:   SQL 输入 → 解析 → EXPLAIN → 优化分流 → 改写 SQL + 索引 DDL
新模式（NL→SQL）:  自然语言输入 → 分词 → 实体映射 → SQL 生成 → 执行查询 → 结果展示
                                               ↓
                                     生成的 SQL 可选送入"优化模式"二次优化
```

两种模式共享：`DBConnector`（执行 SQL）、`SchemaProvider`（表结构）、`LocalOptimizer`（可选校验）、GUI 框架（模式切换）。

---

## 2. 技术方案选型

### 2.1 自然语言解析方案

| 方案 | 描述 | 优点 | 缺点 | 选型 |
|------|------|------|------|------|
| jieba 分词 + 规则匹配 | jieba 分词后用正则/关键词词典做意图识别和实体提取 | 轻量、快速、纯本地、依赖少 | 无法处理复杂语义 | **选型** |
| rasa-nlu 本地模式 | 训练 NLU 模型做意图分类和实体抽取 | 准确率较高、可训练 | 需要训练数据、依赖重、启动慢 | 不选 |
| 纯正则 | 不分词，直接用正则匹配 | 零依赖 | 中文无空格分词，正则复杂度爆炸 | 不选 |

**jieba 选型理由**：
- 纯 Python 实现，无编译依赖，打包到 exe 无体积问题
- 项目已有 `sqlparse`（SQL 解析）和 `pymysql`（数据库），jieba 体量相当
- 支持自定义词典，可加载 schema 中的表名/列名作为词库，提高分词准确度
- 项目目标用户是开发者/DBA，自然语言输入以"结构化描述"为主，不需要通用 NLU

### 2.2 SQL 生成方案

| 方案 | 描述 | 优点 | 缺点 | 选型 |
|------|------|------|------|------|
| 模板法 + 参数填充 | 预定义 SQL 模板，按意图选择模板并填充参数 | 简单、可控、生成的 SQL 保证语法正确 | 灵活性有限 | **选型（核心）** |
| sqlparse 反向生成 | 用 sqlparse 的 AST 反向构造 SQL | 理论上灵活 | sqlparse 主要用于解析而非生成，API 不支持 | 不选 |
| sqlglot AST 构建 | 用 sqlglot 构建 SQL AST 再渲染 | 强大、可跨方言 | 额外依赖、学习曲线 | 后续演进备选 |

**模板法选型理由**：
- SQL Coach 的 NL→SQL 场景相对结构化（SELECT 查询为主），模板法足够覆盖
- 生成的 SQL 语法保证正确，不会产生"语法错误的 AI 幻觉"
- 与现有 `LocalOptimizer` 的规则风格一致（规则匹配 + 改写）
- 后续可通过 sqlglot 增强复杂查询的生成能力

### 2.3 开源库依赖

| 库 | 用途 | 体积 | 是否需安装 |
|----|------|------|-----------|
| jieba | 中文分词 | ~15MB（含词典） | 是，加入 `pyproject.toml` |
| sqlparse | SQL 解析（已有） | ~1MB | 否（已依赖） |
| pymysql | 数据库连接（已有） | ~1MB | 否（已依赖） |

jieba 的词典文件可裁剪：只保留核心词典 + 自定义 schema 词典，打包后体积增量约 5MB。

---

## 3. 架构设计

### 3.1 新增模块目录结构

```
sql_coach/
├── nl/                         # 自然语言处理模块（新增）
│   ├── __init__.py
│   ├── tokenizer.py            # jieba 分词 + 自定义词典加载
│   ├── intent.py               # 意图识别（查询/统计/排序/限制）
│   ├── extractor.py            # 实体提取（表名、列名、条件、聚合、排序、LIMIT）
│   ├── parser.py               # NLParser 主类：分词 → 意图 → 实体 → NLQuery
│   └── dictionary.py           # 词典管理（从 schema 动态生成自定义词库）
├── nl_to_sql/                  # SQL 生成模块（新增）
│   ├── __init__.py
│   ├── builder.py              # SQLBuilder 主类：NLQuery → SQL 字符串
│   ├── templates.py            # SQL 模板库
│   └── mapper.py               # 实体到 SQL 片段的映射器
├── models.py                   # 新增 NLQuery、NLQueryResult 数据模型
├── coach.py                    # 新增 generate_sql() 方法
├── cli.py                      # 新增 nl2sql 子命令
├── interactive.py              # 交互模式新增 NL 入口
└── ...

gui/
├── widgets/
│   ├── nl_input_widget.py      # 自然语言输入区（新增）
│   ├── sql_display_widget.py   # SQL 展示区（新增）
│   └── query_result_widget.py # 查询结果表格（新增）
├── workers/
│   └── nl_worker.py            # NL→SQL 后台线程（新增）
└── main_window.py              # 新增模式切换
```

### 3.2 模块依赖关系

```
用户输入自然语言
    │
    ▼
NLParser (sql_coach/nl/parser.py)
    ├── tokenizer.py        jieba 分词 + schema 词典
    ├── intent.py           意图识别
    ├── extractor.py        实体提取
    └── dictionary.py       词典管理 ← SchemaProvider (复用 local/schema.py)
    │
    ▼
NLQuery (数据模型)
    │
    ▼
SQLBuilder (sql_coach/nl_to_sql/builder.py)
    ├── templates.py        SQL 模板
    └── mapper.py           实体映射
    │
    ▼
SQL 字符串
    │
    ├── 可选 → LocalOptimizer.optimize()  校验/优化生成的 SQL
    │
    ▼
DBConnector.query()  执行 SQL（复用现有）
    │
    ▼
QueryResult (行数据 + 列名)
```

### 3.3 与现有模块的集成方式

#### 与 SchemaProvider 集成

`SchemaProvider`（`sql_coach/local/schema.py`）已实现从 `information_schema` 读取表结构和索引，按表累积缓存。NL 模式复用同一实例：

```python
# sql_coach/coach.py 新增
class SQLCoach:
    def __init__(self, config: Config, use_cache: bool = True):
        ...
        self.schema_provider = SchemaProvider(self.db)  # 已有
        self._nl_parser: Optional[NLParser] = None        # 惰性创建

    @property
    def nl_parser(self) -> NLParser:
        if self._nl_parser is None:
            schema = self.schema_provider.load_all()  # 新增方法
            self._nl_parser = NLParser(schema)
        return self._nl_parser
```

`SchemaProvider` 新增 `load_all()` 方法，读取当前数据库所有表的结构（用于构建 NL 词典）。

#### 与 DBConnector 集成

`DBConnector.query(sql, params)` 已返回 `list[tuple]`，可直接复用。需要额外获取列名：

```python
# DBConnector 新增方法
def query_with_columns(self, sql: str, params=None) -> tuple[list[str], list[tuple]]:
    """执行查询，返回 (列名列表, 行数据列表)。"""
    with self._conn.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
    return columns, rows
```

#### 与 LocalOptimizer 集成

生成的 SQL 可选送入 `LocalOptimizer` 做校验（检测 `SELECT *`、缺失索引等），但**不改写**生成的 SQL（避免改变用户意图）：

```python
# 在 SQLCoach.generate_sql() 中
if verify:
    sql_info = parse_sql(generated_sql)
    analysis = LocalOptimizer().optimize(sql_info, schema)
    # 仅取 problems 作为提示，不使用 optimized_sql
```

#### 与 CLI 集成

```python
# sql_coach/cli.py 新增子命令
@main.command()
@click.argument("query")
@click.option("--execute/--no-execute", default=True, help="是否执行生成的 SQL")
def nl2sql(query, execute):
    """自然语言转 SQL。"""
    ...
```

#### 与 GUI 集成

`MainWindow` 新增模式切换（工具栏下拉或 Tab），根据模式选择 `SqlInputWidget`（优化模式）或 `NlInputWidget`（NL 模式），右侧展示区切换为 `ReportView` 或 `QueryResultWidget`。

---

## 4. 核心模块设计

### 4.1 数据模型（sql_coach/models.py 新增）

```python
@dataclass
class NLEntity:
    """从自然语言中提取的一个实体。"""
    type: str       # table / column / condition / aggregate / order / limit / value
    raw: str        # 原始文本
    mapped: str     # 映射后的 SQL 片段（如表名、列名）
    alias: str = "" # 别名（如"销售额" → SUM(amount)）


@dataclass
class NLQuery:
    """自然语言解析结果。"""
    intent: str                    # select / aggregate / count
    tables: list[str]              # 识别到的表名
    columns: list[str]             # 显式列名（"查询name和age" → ["name", "age"]）
    conditions: list[NLEntity]     # WHERE 条件
    aggregates: list[NLEntity]     # 聚合函数（"销售额" → SUM(amount)）
    order_by: list[NLEntity]      # 排序（"最高的" → ORDER BY ... DESC）
    group_by: list[str]           # 分组列
    limit: Optional[int] = None    # LIMIT 值
    raw_text: str = ""              # 原始自然语言


@dataclass
class NLQueryResult:
    """NL→SQL 模式的最终输出。"""
    nl_query: NLQuery               # 解析结果
    generated_sql: str               # 生成的 SQL
    columns: list[str] = field(default_factory=list)  # 结果列名
    rows: list[tuple] = field(default_factory=list)   # 结果行数据
    warnings: list[str] = field(default_factory=list) # 警告信息
    executed: bool = False           # 是否执行了查询
    error: str = ""                  # 执行错误
```

### 4.2 词典管理（sql_coach/nl/dictionary.py）

从 schema 动态构建 jieba 自定义词典，将表名、列名、列的中文注释作为词条：

```python
class SchemaDictionary:
    """从数据库 schema 构建 jieba 自定义词典。"""

    def __init__(self, schema: Schema):
        self._synonyms: dict[str, str] = {}  # 中文别名 → 数据库标识
        self._build(schema)

    def _build(self, schema: Schema) -> None:
        """遍历 schema 的表和列，构建同义词映射。"""
        for table_name, table_schema in schema.tables.items():
            self._add_synonym(table_name, table_name)
            for col_name in table_schema.columns:
                self._add_synonym(col_name, col_name)
                # 从列名推断中文别名（如 status → 状态, name → 名称）

    def _add_synonym(self, alias: str, canonical: str) -> None:
        self._synonyms[alias.lower()] = canonical

    def resolve(self, word: str) -> Optional[str]:
        """将分词结果映射到数据库标识符。"""
        return self._synonyms.get(word.lower())

    def jieba_words(self) -> list[str]:
        """返回需要在 jieba 加载的自定义词列表。"""
        return list(self._synonyms.keys())
```

### 4.3 分词器（sql_coach/nl/tokenizer.py）

```python
import jieba

class Tokenizer:
    """jieba 分词器，加载 schema 自定义词典。"""

    def __init__(self, dictionary: Optional[SchemaDictionary] = None):
        self._dictionary = dictionary
        if dictionary:
            for word in dictionary.jieba_words():
                jieba.add_word(word)

    def tokenize(self, text: str) -> list[str]:
        """分词，返回词列表。"""
        return [w.strip() for w in jieba.cut(text) if w.strip()]
```

### 4.4 意图识别（sql_coach/nl/intent.py）

基于关键词匹配识别查询意图：

```python
INTENT_KEYWORDS = {
    "aggregate": ["最高", "最低", "平均", "总和", "总数", "统计", "多少", "销售额", "数量"],
    "count":     ["多少条", "几条", "数量", "计数"],
    "select":    ["查询", "查找", "找", "列出", "显示", "获取", "看看"],
}


class IntentRecognizer:
    """基于关键词的意图识别。"""

    def recognize(self, tokens: list[str]) -> str:
        """返回意图：select / aggregate / count。"""
        text = "".join(tokens)
        for intent, keywords in INTENT_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return intent
        return "select"  # 默认
```

### 4.5 实体提取（sql_coach/nl/extractor.py）

从分词结果中提取结构化实体：

```python
class EntityExtractor:
    """从分词结果提取表名、列名、条件、聚合、排序、LIMIT。"""

    ORDER_KEYWORDS = {
        "最高": "DESC", "最大": "DESC", "最近": "DESC", "倒序": "DESC",
        "最低": "ASC", "最小": "ASC", "最早": "ASC", "正序": "ASC",
    }
    LIMIT_PAT = re.compile(r"(\d+)\s*(条|个|行|记录)")
    AGGREGATE_MAP = {
        "销售额": "SUM", "总计": "SUM", "平均": "AVG", "均值": "AVG",
        "数量": "COUNT", "总数": "COUNT", "最高": "MAX", "最低": "MIN",
    }

    def __init__(self, dictionary: SchemaDictionary):
        self._dict = dictionary

    def extract(self, tokens: list[str], intent: str) -> NLQuery:
        """提取所有实体，返回 NLQuery。"""
        text = "".join(tokens)
        tables, columns, conditions = [], [], []
        aggregates, order_by, group_by = [], [], []
        limit = None

        # 1. 表名/列名：遍历 tokens，用词典解析
        for token in tokens:
            resolved = self._dict.resolve(token)
            if resolved and self._is_table(resolved):
                tables.append(resolved)
            elif resolved:
                columns.append(resolved)

        # 2. 聚合函数
        for keyword, func in self.AGGREGATE_MAP.items():
            if keyword in text:
                # 找到聚合的目标列
                target_col = self._find_nearest_column(tokens, keyword)
                aggregates.append(NLEntity(
                    type="aggregate", raw=keyword,
                    mapped=f"{func}({target_col})"))

        # 3. 排序
        for keyword, direction in self.ORDER_KEYWORDS.items():
            if keyword in text:
                sort_col = self._find_sort_column(tokens, keyword, columns, aggregates)
                order_by.append(NLEntity(
                    type="order", raw=keyword,
                    mapped=f"{sort_col} {direction}"))
                break  # 只取第一个排序意图

        # 4. LIMIT
        m = self.LIMIT_PAT.search(text)
        if m:
            limit = int(m.group(1))

        # 5. WHERE 条件（从文本中提取 "列名 操作符 值" 模式）
        conditions = self._extract_conditions(tokens, text)

        return NLQuery(
            intent=intent, tables=tables, columns=columns,
            conditions=conditions, aggregates=aggregates,
            order_by=order_by, group_by=group_by,
            limit=limit, raw_text=text,
        )
```

### 4.6 NLParser 主类（sql_coach/nl/parser.py）

```python
class NLParser:
    """自然语言解析器：分词 → 意图识别 → 实体提取。"""

    def __init__(self, schema: Schema):
        self._dict = SchemaDictionary(schema)
        self._tokenizer = Tokenizer(self._dict)
        self._intent = IntentRecognizer()
        self._extractor = EntityExtractor(self._dict)

    def parse(self, text: str) -> NLQuery:
        """解析自然语言文本，返回 NLQuery。"""
        tokens = self._tokenizer.tokenize(text)
        intent = self._intent.recognize(tokens)
        return self._extractor.extract(tokens, intent)
```

**示例**：

```python
parser = NLParser(schema)
query = parser.parse("查询销售额最高的10个客户")
# query.intent      -> "aggregate"
# query.tables      -> ["customers"]
# query.aggregates  -> [NLEntity(type="aggregate", raw="销售额", mapped="SUM(amount)")]
# query.order_by    -> [NLEntity(type="order", raw="最高", mapped="SUM(amount) DESC")]
# query.limit       -> 10
```

### 4.7 SQL 生成器（sql_coach/nl_to_sql/builder.py）

```python
class SQLBuilder:
    """根据 NLQuery 构建 SQL 字符串。"""

    def build(self, nl_query: NLQuery) -> str:
        """生成 SQL。"""
        intent = nl_query.intent

        if intent == "count":
            return self._build_count(nl_query)
        elif intent == "aggregate":
            return self._build_aggregate(nl_query)
        else:
            return self._build_select(nl_query)

    def _build_select(self, q: NLQuery) -> str:
        cols = ", ".join(q.columns) if q.columns else "*"
        table = q.tables[0] if q.tables else "unknown_table"
        sql = f"SELECT {cols} FROM {table}"
        sql += self._build_where(q)
        sql += self._build_order(q)
        sql += self._build_limit(q)
        return sql + ";"

    def _build_aggregate(self, q: NLQuery) -> str:
        agg_cols = [a.mapped for a in q.aggregates]
        plain_cols = q.columns
        select_parts = plain_cols + agg_cols if plain_cols else agg_cols
        cols = ", ".join(select_parts) if select_parts else "*"
        table = q.tables[0] if q.tables else "unknown_table"
        sql = f"SELECT {cols} FROM {table}"
        sql += self._build_where(q)
        # 聚合通常需要 GROUP BY
        if q.group_by:
            sql += " GROUP BY " + ", ".join(q.group_by)
        elif plain_cols:
            sql += " GROUP BY " + ", ".join(plain_cols)
        sql += self._build_order(q)
        sql += self._build_limit(q)
        return sql + ";"

    def _build_count(self, q: NLQuery) -> str:
        table = q.tables[0] if q.tables else "unknown_table"
        sql = f"SELECT COUNT(*) AS cnt FROM {table}"
        sql += self._build_where(q)
        return sql + ";"

    def _build_where(self, q: NLQuery) -> str:
        if not q.conditions:
            return ""
        parts = [c.mapped for c in q.conditions]
        return " WHERE " + " AND ".join(parts)

    def _build_order(self, q: NLQuery) -> str:
        if not q.order_by:
            return ""
        return " ORDER BY " + ", ".join(o.mapped for o in q.order_by)

    def _build_limit(self, q: NLQuery) -> str:
        if q.limit is None:
            return ""
        return f" LIMIT {q.limit}"
```

**生成示例**：

| 自然语言 | 生成的 SQL |
|---------|-----------|
| 查询销售额最高的10个客户 | `SELECT customer_name, SUM(amount) FROM customers GROUP BY customer_name ORDER BY SUM(amount) DESC LIMIT 10;` |
| 查找status为pending的订单 | `SELECT * FROM orders WHERE status = 'pending';` |
| 统计每个城市的用户数量 | `SELECT city, COUNT(*) FROM users GROUP BY city;` |
| 查询最近10条订单 | `SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;` |

### 4.8 SQLCoach 集成

```python
# sql_coach/coach.py 新增
class SQLCoach:
    def generate_sql(
        self,
        text: str,
        execute: bool = True,
        verify: bool = True,
    ) -> NLQueryResult:
        """自然语言转 SQL。

        Args:
            text: 自然语言描述。
            execute: 是否执行生成的 SQL。
            verify: 是否用本地规则引擎校验生成的 SQL。
        """
        # 1. 读取 schema
        if not self.config.mock and self.db.is_connected():
            schema = self.schema_provider.load_all()
        else:
            schema = Schema()

        # 2. 解析自然语言
        parser = NLParser(schema)
        nl_query = parser.parse(text)

        # 3. 生成 SQL
        builder = SQLBuilder()
        sql = builder.build(nl_query)

        # 4. 校验（可选）
        warnings = []
        if verify and schema:
            sql_info = parse_sql(sql)
            analysis = LocalOptimizer().optimize(sql_info, schema)
            warnings = [p.description for p in analysis.problems]

        # 5. 执行查询
        columns, rows = [], []
        executed = False
        error = ""
        if execute and not self.config.mock and self.db.is_connected():
            try:
                columns, rows = self.db.query_with_columns(sql)
                executed = True
            except Exception as e:
                error = str(e)

        return NLQueryResult(
            nl_query=nl_query,
            generated_sql=sql,
            columns=columns,
            rows=rows,
            warnings=warnings,
            executed=executed,
            error=error,
        )
```

---

## 5. 数据流设计

### 5.1 完整流程

```
用户输入: "查询销售额最高的10个客户"
    │
    ▼
┌──────────────────────────────────┐
│ SchemaProvider.load_all()       │  读取数据库所有表结构
│ → Schema(tables, columns, ...)  │  构建 SchemaDictionary
└──────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────┐
│ Tokenizer.tokenize(text)         │  jieba 分词 + schema 词典
│ → ["查询", "销售额", "最高",    │
│    "的", "10", "个", "客户"]    │
└──────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────┐
│ IntentRecognizer.recognize()    │  关键词匹配
│ → intent = "aggregate"          │  ("最高" → aggregate)
└──────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────┐
│ EntityExtractor.extract()        │  实体提取
│ → tables: ["customers"]         │  ("客户" → customers 表)
│ → aggregates: [SUM(amount)]      │  ("销售额" → SUM(amount))
│ → order_by: [SUM(amount) DESC]  │  ("最高" → DESC)
│ → limit: 10                      │  ("10个" → LIMIT 10)
│ → NLQuery                        │
└──────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────┐
│ SQLBuilder.build(nl_query)      │  模板填充
│ → "SELECT customer_name,        │
│     SUM(amount) FROM customers  │
│     GROUP BY customer_name      │
│     ORDER BY SUM(amount) DESC   │
│     LIMIT 10;"                  │
└──────────────────────────────────┘
    │
    ├── verify=True ──→ LocalOptimizer.optimize() → warnings
    │
    ▼
┌──────────────────────────────────┐
│ DBConnector.query_with_columns()│  执行 SQL
│ → columns: ["customer_name",    │
│             "SUM(amount)"]       │
│ → rows: [("张三", 99999), ...]  │
└──────────────────────────────────┘
    │
    ▼
NLQueryResult {
    generated_sql: "SELECT ...",
    columns: [...],
    rows: [...],
    warnings: [...],
    executed: True,
}
```

### 5.2 错误处理流程

```
schema 读取失败 → 降级为空 schema，仍可生成基础 SQL（无法映射表名列名）
表名识别失败 → 使用 "unknown_table"，在 warnings 中提示
SQL 执行失败 → error 记录错误信息，generated_sql 仍展示给用户
jieba 分词异常 → 降级为简单空格分词
```

---

## 6. GUI 交互设计

### 6.1 模式切换

在 `MainWindow` 工具栏新增模式切换控件：

```
┌─────────────────────────────────────────────────────────┐
│ [优化模式 ▼] [🔍 分析] [🗑 清空] [💾 导出] [🕘 历史] [⚙] │
├──────────────────┬──────────────────────────────────────┤
│                  │                                      │
│  模式 1: 优化    │  ReportView (现有)                   │
│  SqlInputWidget  │  EXPLAIN 表格 + 问题列表 + 性能对比  │
│  (SQL 输入)      │                                      │
│                  │                                      │
├──────────────────┼──────────────────────────────────────┤
│  模式 2: NL→SQL  │  SqlDisplayWidget + QueryResultWidget│
│  NlInputWidget   │  ┌──────────────────────────────┐    │
│  (自然语言输入)   │  │ 生成的 SQL:                  │    │
│                  │  │ SELECT ... LIMIT 10;         │    │
│                  │  │ [📋 复制] [🔍 送入优化]       │    │
│                  │  ├──────────────────────────────┤    │
│                  │  │ 查询结果 (10 行)              │    │
│                  │  │ ┌────┬───────┬────────────┐  │    │
│                  │  │ │ id │ name  │ SUM(amount)│  │    │
│                  │  │ ├────┼───────┼────────────┤  │    │
│                  │  │ │ 1  │ 张三  │ 99999      │  │    │
│                  │  │ │ 2  │ 李四  │ 88888      │  │    │
│                  │  │ └────┴───────┴────────────┘  │    │
│                  │  └──────────────────────────────┘    │
└──────────────────┴──────────────────────────────────────┘
```

### 6.2 新增 GUI 组件

#### NlInputWidget

```python
class NlInputWidget(QWidget):
    """自然语言输入区。"""
    generate_requested = Signal(str)  # 发射自然语言文本

    # 布局: 标题 + QPlainTextEdit + "生成 SQL" 按钮
    # placeholder: "用自然语言描述你想查询的数据 ..."
    # 示例提示: "查询销售额最高的10个客户"
```

#### SqlDisplayWidget

```python
class SqlDisplayWidget(QWidget):
    """SQL 展示区。"""
    # 布局: 标题 + 只读 QPlainTextEdit (等宽字体) + 按钮行
    # 按钮: [📋 复制 SQL] [🔍 送入优化模式]
```

#### QueryResultWidget

```python
class QueryResultWidget(QWidget):
    """查询结果表格。"""
    # 布局: 标题(行数) + QTableWidget
    # 支持大数据量时分页（初版可不做，仅设置行数上限如 1000）
```

#### NlWorker

```python
class NlWorker(QThread):
    """NL→SQL 后台线程。"""
    finished = Signal(NLQueryResult)
    error = Signal(str)

    def __init__(self, text: str, config: Config, parent=None): ...
    def run(self):
        coach = SQLCoach(self.config, use_cache=False)
        coach.connect()
        result = coach.generate_sql(self.text, execute=True, verify=True)
        coach.close()
        self.finished.emit(result)
```

### 6.3 模式联动

"送入优化模式"按钮：将生成的 SQL 填入 `SqlInputWidget` 的编辑器，切换到优化模式，用户可对生成的 SQL 执行优化分析。

---

## 7. 开发任务拆解

### Task 0: 安装 jieba 依赖

- **目标**: 在 `pyproject.toml` 中添加 jieba 依赖，验证可正常 import
- **涉及文件**: `pyproject.toml`
- **预估难度**: 低

### Task 1: 数据模型

- **目标**: 在 `models.py` 中新增 `NLEntity`、`NLQuery`、`NLQueryResult` 三个 dataclass
- **涉及文件**: `sql_coach/models.py`
- **预估难度**: 低
- **验证**: `from sql_coach.models import NLQuery, NLQueryResult` 可正常导入

### Task 2: SchemaProvider.load_all()

- **目标**: 在 `SchemaProvider` 中新增 `load_all()` 方法，读取当前数据库所有表的结构
- **涉及文件**: `sql_coach/local/schema.py`
- **预估难度**: 低
- **验证**: 连库后调用 `load_all()` 返回非空 Schema
- **注意**: 表数量过多时需限制（如最多 100 张表），避免查询卡顿

### Task 3: 词典管理

- **目标**: 实现 `SchemaDictionary`，从 schema 构建同义词映射
- **涉及文件**: `sql_coach/nl/dictionary.py`（新建）、`sql_coach/nl/__init__.py`（新建）
- **预估难度**: 中
- **验证**: 给定 schema，`resolve("客户")` 返回 `"customers"`

### Task 4: 分词器

- **目标**: 实现 `Tokenizer`，加载 jieba + 自定义词典
- **涉及文件**: `sql_coach/nl/tokenizer.py`（新建）
- **预估难度**: 低
- **验证**: `tokenize("查询销售额最高的10个客户")` 正确分词

### Task 5: 意图识别

- **目标**: 实现 `IntentRecognizer`，基于关键词识别 select/aggregate/count
- **涉及文件**: `sql_coach/nl/intent.py`（新建）
- **预估难度**: 低
- **验证**: 三个意图各测 3 条用例

### Task 6: 实体提取

- **目标**: 实现 `EntityExtractor`，提取表名、列名、条件、聚合、排序、LIMIT
- **涉及文件**: `sql_coach/nl/extractor.py`（新建）
- **预估难度**: 高（核心逻辑，需处理多种自然语言表述）
- **验证**: 10 条测试用例覆盖各实体类型

### Task 7: NLParser 主类

- **目标**: 实现 `NLParser`，串联分词 → 意图 → 实体提取
- **涉及文件**: `sql_coach/nl/parser.py`（新建）
- **预估难度**: 低
- **验证**: `parser.parse("查询...")` 返回完整 `NLQuery`

### Task 8: SQL 模板库

- **目标**: 实现 `templates.py`，定义 select/aggregate/count 三种 SQL 模板
- **涉及文件**: `sql_coach/nl_to_sql/templates.py`（新建）、`sql_coach/nl_to_sql/__init__.py`（新建）
- **预估难度**: 中
- **验证**: 模板填充后生成的 SQL 语法正确

### Task 9: 实体映射器

- **目标**: 实现 `mapper.py`，将 `NLEntity` 映射为 SQL 片段
- **涉及文件**: `sql_coach/nl_to_sql/mapper.py`（新建）
- **预估难度**: 中
- **验证**: 各实体类型的映射结果正确

### Task 10: SQLBuilder

- **目标**: 实现 `SQLBuilder.build()`，组装完整 SQL
- **涉及文件**: `sql_coach/nl_to_sql/builder.py`（新建）
- **预估难度**: 中
- **验证**: 10 条用例，生成的 SQL 可被 `sqlparse` 正确解析

### Task 11: SQLCoach.generate_sql()

- **目标**: 在 `SQLCoach` 中新增 `generate_sql()` 方法，串联全流程
- **涉及文件**: `sql_coach/coach.py`、`sql_coach/db/connector.py`（新增 `query_with_columns`）
- **预估难度**: 中
- **验证**: 连库后端到端测试

### Task 12: CLI 子命令

- **目标**: 在 `cli.py` 中新增 `nl2sql` 子命令
- **涉及文件**: `sql_coach/cli.py`
- **预估难度**: 低
- **验证**: `sql-coach nl2sql "查询10条订单"`

### Task 13: 交互模式集成

- **目标**: 在 `interactive.py` 中新增 NL 模式入口
- **涉及文件**: `sql_coach/interactive.py`
- **预估难度**: 低

### Task 14: GUI 新增组件

- **目标**: 实现 `NlInputWidget`、`SqlDisplayWidget`、`QueryResultWidget`
- **涉及文件**: `gui/widgets/nl_input_widget.py`、`gui/widgets/sql_display_widget.py`、`gui/widgets/query_result_widget.py`（新建）
- **预估难度**: 中
- **验证**: 各组件可独立创建和交互

### Task 15: GUI 模式切换

- **目标**: 在 `MainWindow` 中新增模式切换，组装新组件
- **涉及文件**: `gui/main_window.py`、`gui/workers/nl_worker.py`（新建）
- **预估难度**: 中
- **验证**: 模式切换正常，NL 模式端到端可用

### Task 16: 单元测试

- **目标**: 为所有新增模块编写单元测试
- **涉及文件**: `tests/test_nl_parser.py`、`tests/test_sql_builder.py`、`tests/test_schema_dictionary.py`、`tests/test_nl_coach.py`（新建）
- **预估难度**: 中
- **验证**: 全量测试通过（目标 +50 条用例，总计 ~380 passed）

---

## 8. 测试策略

### 8.1 单元测试

| 测试文件 | 覆盖模块 | 测试要点 |
|---------|---------|---------|
| `test_schema_dictionary.py` | `SchemaDictionary` | 表名/列名映射、大小写、中文别名推断 |
| `test_tokenizer.py` | `Tokenizer` | jieba 分词正确性、自定义词典加载 |
| `test_intent.py` | `IntentRecognizer` | 三种意图的关键词识别 |
| `test_extractor.py` | `EntityExtractor` | 表名/列名/条件/聚合/排序/LIMIT 提取 |
| `test_nl_parser.py` | `NLParser` | 端到端解析，输入文本 → NLQuery |
| `test_sql_builder.py` | `SQLBuilder` | 三种模板的 SQL 生成、语法正确性 |
| `test_nl_coach.py` | `SQLCoach.generate_sql` | 端到端，含 mock 模式 |

### 8.2 测试用例设计

```python
# test_nl_parser.py
@pytest.mark.parametrize("text,expected_intent,expected_tables,expected_limit", [
    ("查询销售额最高的10个客户", "aggregate", ["customers"], 10),
    ("查找status为pending的订单", "select", ["orders"], None),
    ("统计每个城市的用户数量", "aggregate", ["users"], None),
    ("查询最近10条订单", "select", ["orders"], 10),
    ("有多少条status为paid的订单", "count", ["orders"], None),
])
def test_parse(text, expected_intent, expected_tables, expected_limit):
    parser = NLParser(test_schema)
    result = parser.parse(text)
    assert result.intent == expected_intent
    assert result.tables == expected_tables
    assert result.limit == expected_limit
```

### 8.3 集成测试

```python
# test_nl_coach.py
def test_generate_sql_mock(mock_config):
    """mock 模式下生成 SQL（不执行查询）。"""
    coach = SQLCoach(mock_config)
    result = coach.generate_sql("查询10条订单", execute=False)
    assert "SELECT" in result.generated_sql.upper()
    assert "LIMIT 10" in result.generated_sql.upper()

def test_generate_sql_with_db(db_config):
    """连库模式下生成并执行 SQL。"""
    coach = SQLCoach(db_config)
    coach.connect()
    result = coach.generate_sql("查询10条订单", execute=True)
    assert result.executed
    assert len(result.columns) > 0
    coach.close()
```

---

## 9. 风险与挑战

### 9.1 中文自然语言解析的难点

| 难点 | 影响 | 应对 |
|------|------|------|
| 表名/列名的中文表述多样（"客户" vs "顾客" vs "用户"） | 词典映射可能遗漏 | 内置常见同义词 + schema 列名推断 |
| 条件表达式多样（"大于18"、"超过18"、"18岁以上"） | WHERE 条件提取困难 | 正则 + 关键词规则覆盖常见模式 |
| 聚合函数与列名的关联（"每个城市的销售额" → city 分组 + SUM(amount)） | GROUP BY 推断困难 | 基于"每个/每种/各类"关键词识别分组列 |
| 隐式 JOIN（"查询订单的客户名称"） | 需要 JOIN 但无法自动推断关联 | 非目标，后续演进；当前仅支持单表 |
| 多义性（"最高"可指 MAX 也可指 ORDER BY DESC LIMIT 1） | 意图识别歧义 | 优先匹配 aggregate 意图，降级为 select + ORDER BY |

### 9.2 SQL 生成准确性保障

| 保障措施 | 说明 |
|---------|------|
| 模板法 | 生成的 SQL 结构固定，不会产生语法错误 |
| schema 校验 | 生成的表名/列名必须在 schema 中存在 |
| LocalOptimizer 校验 | 检测 SELECT *、缺失索引等问题 |
| SQL 语法验证 | 用 `sqlparse.parse()` 验证生成的 SQL 可被正确解析 |
| 用户确认 | GUI 展示生成的 SQL，用户可编辑后再执行 |
| 执行错误捕获 | SQL 执行失败时展示错误信息，不崩溃 |

### 9.3 性能风险

| 风险 | 应对 |
|------|------|
| `load_all()` 查询大量表结构慢 | 限制最多 100 张表；结果缓存 |
| jieba 首次加载慢 | 惰性创建 NLParser；首次使用后常驻 |
| 查询结果过大 | `QueryResultWidget` 设置行数上限 1000；提示用户加 LIMIT |

---

## 10. 后续演进方向

### 10.1 短期（下一迭代）

- **多表 JOIN**：利用 schema 的外键信息推断表关联关系，支持"查询订单和客户信息"等 JOIN 查询
- **条件增强**：支持 `BETWEEN`、`IN`、`LIKE`、`OR` 等复杂条件
- **中文同义词库**：内置常见的数据库术语同义词（"金额" → amount/price/total 等）
- **HAVING 支持**：支持"销售额超过1万的客户"

### 10.2 中期

- **sqlglot AST 构建**：用 sqlglot 替换模板法，支持更复杂的 SQL 结构（子查询、窗口函数、CTE）
- **学习用户习惯**：记录用户编辑过的 SQL，用于改进映射规则
- **多方言支持**：PostgreSQL、SQLite 等其他数据库
- **语音输入**：集成语音转文本

### 10.3 长期

- **AI 辅助模式**：本地算法无法处理时，可选调用 AI 增强（作为降级/增强而非主路径）
- **自然语言交互**：支持"把这个查询按月分组"等追加指令，增量修改已生成的 SQL
- **语义理解**：从列注释/表注释中学习业务语义（如"销售额" = `SUM(order_total)`）
