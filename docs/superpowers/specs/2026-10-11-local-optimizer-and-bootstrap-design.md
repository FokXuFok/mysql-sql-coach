# SQL Coach 本地算法分流 + 启动自检设计文档

> 日期: 2026-10-11
> 状态: 已批准，待实施
> 关联: 在 `2026-07-17-gui-desktop-design.md`（桌面 GUI）基础上扩展

## 1. 概述

当前 SQL Coach 的优化建议**全部依赖 AI 大模型**：每条 SQL 都要把 SQL + EXPLAIN 结果发给大模型，
等待数秒才返回。对大量结构简单、模式固定的 SQL 而言，这是不必要的等待与成本。

本次改动的目标：**引入本地规则引擎**，简单 / 中等复杂度的 SQL 直接由本地算法在毫秒级给出优化建议与改写，
只有复杂 SQL 才调用 AI；同时把分发形态改为**单文件 exe**，并在启动时**自动检测运行环境**，
能安全自动修复的直接修复，其余给出明确指引。

### 目标

- 新增本地规则引擎，覆盖核心安全规则 + 安全改写，产出与 AI 一致的 `AnalysisResult`
- 按 SQL 结构自动评分分流（简单/中等→本地，复杂→AI），支持用户在设置里调整阈值或强制指定
- 打包为**单文件 onefile exe**，下载后双击即用
- 启动时自动检测：`.env` 配置、MySQL 连接、AI 配置与连通性、运行环境依赖
- 分层修复：能安全自动做的自动做，系统级软件（MySQL 等）只检测 + 引导，绝不静默改系统
- 保持现有 `ai/`、`db/`、`engine/`、`report/` 代码零回归

### 非目标

- 不做 SQL 语法高亮
- 不做本地算法覆盖全部 MySQL 优化规则（本期只做核心 + 安全改写）
- 不做系统级软件的静默自动安装
- 不引入新的数据库后端（仅 MySQL）
- 不改动现有 AI 引擎的对外接口

## 2. 背景与现状

现有分析流水线（`sql_coach/coach.py` 的 `SQLCoach.analyze()`）：

```
解析 SQL (sql_parser) → EXPLAIN (DBConnector) → AI 分析 (AIEngine) → 性能对比 (benchmark) → Report
```

- 第 3 步 `AIEngine.analyze()` 是**唯一的优化建议来源**，无论 SQL 多简单都要走网络 + 大模型
- `AIEngine` 抽象基类（`ai/base.py`）已定义 `analyze(sql_info, explain_result, on_chunk) -> AnalysisResult`
- `AnalysisResult`（`models.py`）已包含 `problems / optimized_sql / index_ddls / explanation`，是本地引擎可以直接复用的契约
- 已有 mock 模式、SQLite 缓存、GUI 后台线程等基础设施可复用

## 3. 架构

### 3.1 模块依赖关系（改动后）

```
main.py (智能入口)
    │
    ├── frozen / --gui → gui/app.py
    │                       ├── diagnostics 自检对话框 (首次启动)
    │                       └── gui/main_window.py
    │                             ├── widgets/... (报告区新增 引擎/复杂度 徽章)
    │                             └── workers/analyze_worker.py → SQLCoach
    │
    └── 否则 → sql_coach/interactive.py

SQLCoach.analyze()  ← sql_coach/coach.py
    ├── engine/sql_parser.py         (不变)
    ├── local/schema.py              (新增, 可选读 information_schema)
    ├── local/complexity.py          (新增, 复杂度评分)
    ├── optimizer.py                 (新增, 分流路由)
    │       ├── local/engine.py      (新增, 本地规则引擎)
    │       └── ai/*                 (不变, 复杂 SQL 走这里)
    ├── db/*                         (不变)
    └── report/*                     (不变)
```

### 3.2 设计原则

1. **契约统一**：本地引擎与 AI 引擎产出同一种 `AnalysisResult`，上层（GUI/CLI/Report）无需区分
2. **分流集中**：所有"本地 or AI"的决策只在 `optimizer.py` 一处，可独立单测
3. **核心零改动**：`ai/`、`db/`、`engine/`、`report/` 不修改；`coach.py`、`models.py` 只做最小增量
4. **可降级**：本地引擎异常、schema 读取失败、自检失败，全部降级而非崩溃
5. **安全优先**：任何会改动用户系统的操作，默认只检测 + 引导，自动修复仅限"纯应用内、可逆"的动作

## 4. 复杂度评分

`sql_coach/local/complexity.py` 的 `ComplexityScorer` 对 `SQLInfo`（含原始 SQL）做**纯结构分析**，不调 AI。

### 4.1 评分特征

| 特征 | 分值 |
|------|------|
| 表数量 = 1（单表） | 0 |
| 表数量 = 2 | 2 |
| 表数量 ≥ 3 | 4 |
| 每个子查询 / 派生表 | +3 |
| CTE（`WITH`） | +3 |
| `UNION` / `UNION ALL` | +2 |
| 聚合函数 / `GROUP BY` / `HAVING` | +2 |
| 窗口函数（`OVER`） | +5 |
| 相关子查询 | +5 |
| `CASE WHEN` / 嵌套函数表达式 | +2 |
| 多 `OR` 条件（≥2） | +1 |
| 无 `WHERE` 的全表查询 | +2 |
| 多列排序 / 分组（≥2 列） | +1 |

### 4.2 等级划分

| 总分 | 等级 | 走向 |
|------|------|------|
| ≤ 3 | simple | 本地 |
| 4 – 8 | medium | 本地 |
| ≥ 9 | complex | AI |

阈值可通过 `.env` 的 `COMPLEXITY_THRESHOLD`（默认 8）调整；`medium` 上界即该阈值。

### 4.3 输出

```python
@dataclass
class Complexity:
    level: str          # simple / medium / complex
    score: int
    reasons: list[str]  # 命中的评分特征，用于展示与调试
```

## 5. 本地规则引擎

### 5.1 规则抽象

`sql_coach/local/rules/base.py`：

```python
class Rule(ABC):
    name: str
    risk: str  # "safe"（仅建议） / "rewrite"（会改写 SQL）

    @abstractmethod
    def check(self, sql_info: SQLInfo, schema: Schema) -> list[Problem]: ...

    def rewrite(self, sql_info: SQLInfo, schema: Schema) -> Optional[str]:
        """返回改写后的 SQL；不改写返回 None。"""
        return None

    def ddls(self, sql_info: SQLInfo, schema: Schema) -> list[str]:
        """返回索引 DDL；无返回空列表。"""
        return []
```

### 5.2 本期规则清单

| 规则 | 文件 | risk | 说明 |
|------|------|------|------|
| 缺索引 | `missing_index.py` | safe | WHERE/JOIN/ORDER BY/GROUP BY 列缺索引 → `CREATE INDEX` |
| SELECT * | `select_star.py` | safe | 建议列出必要列，减少数据传输 |
| 前导通配 | `leading_wildcard.py` | safe | `LIKE '%x'` 无法走索引 |
| 函数包裹索引列 | `function_on_column.py` | rewrite | `WHERE DATE(col)=...` → 范围条件 |
| 隐式类型转换 | `implicit_cast.py` | safe | 字符串列与数字比较 |
| 无 LIMIT | `no_limit.py` | safe | 大表无 LIMIT 的查询 |
| 深分页 | `deep_pagination.py` | rewrite | `LIMIT offset,n` → 延迟关联/游标 |
| OR 条件 | `or_condition.py` | rewrite | `OR` → `UNION` |
| 子查询转 JOIN | `subquery_to_join.py` | rewrite | `IN (SELECT ...)` → `JOIN` / `EXISTS` |

### 5.3 LocalOptimizer

`sql_coach/local/engine.py`：

- 遍历所有启用规则，收集 `problems`、`ddls`
- 依次应用 `rewrite` 规则，产出最终 `optimized_sql`（若无改写则为原始 SQL）
- `explanation` 用中文汇总"命中了哪些规则"，并注明"由本地规则引擎生成"
- 任何规则抛异常 → 捕获并跳过该规则，不影响其他规则与整体产出

### 5.4 Schema 校验

`sql_coach/local/schema.py` 的 `SchemaProvider`：

- 连库时查询 `information_schema.STATISTICS`（现有索引）与 `COLUMNS`（列类型），结果**带缓存**
- 返回 `Schema`（表 → 列类型 / 索引列表）
- 连不上库时返回空 `Schema`，规则降级为"疑似缺索引"，结论标注"未连接数据库，未校验现有索引"
- 有 schema 时，"缺索引"规则跳过已存在的索引，只报真实缺失

## 6. 分流路由

`sql_coach/optimizer.py` 的 `OptimizerRouter` 是**唯一的分流决策点**：

```python
def select(config, sql_info, schema) -> tuple[Optimizer, str]:
    """返回 (优化器实例, engine_name)。"""
```

决策逻辑：

1. `config.optimizer_mode == "local"` → 本地引擎
2. `config.optimizer_mode == "ai"` → AI 引擎
3. `config.optimizer_mode == "auto"`（默认）→ 用 `ComplexityScorer` 评分：
   - simple / medium → 本地引擎
   - complex → AI 引擎

`Optimizer` 是本地引擎与 AI 引擎的统一接口（两者都满足 `optimize(sql_info, explain, schema, on_chunk) -> AnalysisResult`）。

- `LocalOptimizer` 直接实现该接口
- `AIOptimizerAdapter`（同放在 `optimizer.py`）包住现有 `AIEngine.analyze()`，把调用透传出去，**不改动 `ai/` 任何代码**

## 7. 启动自检与分层安装

`sql_coach/diagnostics/`：

### 7.1 检查项

`checks.py`，每项返回：

```python
@dataclass
class CheckResult:
    name: str            # 检查项名
    status: str          # ok / warn / fail
    message: str         # 说明
    fix_hint: str        # 修复指引（命令 / 链接）
    auto_fixable: bool   # 是否可安全自动修复
```

| 检查项 | 缺失时处理 | auto_fixable |
|--------|-----------|--------------|
| `.env` 配置文件 | **自动**生成模板并引导填写 | 是 |
| MySQL 连接 | 弹窗给出平台命令（`winget install Oracle.MySQL` 或 Docker 一行）+ 复制按钮 | 否 |
| AI 配置 / 连通性 | 检查 Key 存在与格式；可选轻量试连；缺失只提示 | 否 |
| 运行环境 | Python 版本 / VC++ 运行库 / 中文字体；仅兵兵检查提示 | 否 |

### 7.2 分层安装

`installer.py` 的 `AutoFixer`：

- **可安全自动修复**：生成 `.env` 模板；**仅源码运行模式**下 `pip install` 缺失的依赖包（安装到项目 venv）
- **打包 exe 模式**：Python 依赖已内置，该检查项直接判定为 `ok`（"已内置"），不做任何安装
- **不可自动**：MySQL 等系统级软件，仅生成"一键命令"文本 + 下载链接，由用户确认执行
- **绝对不做**：静默安装系统软件、提权、修改系统服务

### 7.3 触发方式

- GUI：首次启动弹"环境自检"对话框，列出各项状态 + 修复按钮；提供"跳过 / 不再提示"
- CLI：`sql-coach doctor` 子命令手动触发
- 任何检查失败**不阻断启动**——本地模式无 MySQL 也能用

## 8. 数据模型改动

`models.py`（最小增量）：

- `Report` 增加 `engine_used: str`（`"local"` 或 AI 引擎名）、`complexity: Optional[Complexity]`
- `Config` 增加 `optimizer_mode: str`（默认 `"auto"`）、`complexity_threshold: int`（默认 8）
- 新增 `Complexity` dataclass

## 9. GUI 改动

- `app.py`：启动后先跑 diagnostics，按需弹自检对话框
- `widgets/report_view.py`：报告顶部显示"优化引擎：本地规则 / DeepSeek"标签 + 复杂度徽章
- `widgets/settings_dialog.py`：新增"分流模式（auto/local/ai）"与"复杂度阈值"两项；**顺带修复**现有 `_save_to_env` 只回写 `_ENV_KEYS` 导致丢字段（`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`OLLAMA_MODEL`、`LOG_LEVEL` 及注释）的 bug
- 新增 `widgets/diagnostics_dialog.py`：环境自检对话框

## 10. CLI 改动

- `cli.py`：`analyze` 增加 `--engine auto|local|ai`；新增 `doctor` 子命令
- `interactive.py`：报告里显示引擎来源与复杂度

## 11. 配置新增

`.env` 新增：

```ini
# 优化器分流: auto / local / ai
OPTIMIZER_MODE=auto
# 复杂度阈值（>= 该值走 AI）
COMPLEXITY_THRESHOLD=8
```

## 12. 错误处理

| 场景 | 处理 |
|------|------|
| 本地规则抛异常 | 捕获跳过该规则；本地引擎整体失败则自动降级到 AI |
| schema 读取失败 | 按"无 schema"降级，规则给出保守结论 |
| 自检失败 | 记录状态，允许继续启动 |
| 无 MySQL | 本地模式仍可用；benchmark 跳过 |
| AI 不可用（复杂 SQL） | 沿用现有 3 次重试 + 失败兜底 |

## 13. 测试策略

| 测试文件 | 范围 |
|----------|------|
| `test_complexity.py` | 各等级 SQL 的评分与 reasons |
| `test_local_rules.py` | 每条规则的正例 / 反例 / 边界 |
| `test_local_optimizer.py` | 规则汇总、改写产出、异常隔离 |
| `test_optimizer_routing.py` | auto/local/ai 三种模式的路由决策 |
| `test_schema.py` | information_schema 解析、空 schema 降级、缓存 |
| `test_diagnostics.py` | 各检查项状态判定 |
| `test_installer.py` | AutoFixer 的自动修复与"仅引导"分支 |
| 现有 134 个用例 | 保持不回归 |

## 14. 打包策略

- 新增 `sql-coach-onefile.spec`：`--onefile --windowed`，Windows 产出单个 `sql-coach-gui.exe`
- `.github/workflows/build-gui.yml`：主产物改为单文件 exe；保留 onedir 作为"快速启动"备选 artifact
- onefile 缓解启动慢：设置 `runtime_tmpdir`、关闭 UPX
- `.env.example` 仍打进包内

## 15. 文件结构

### 新增

```
sql-coach/
├── sql_coach/
│   ├── local/
│   │   ├── __init__.py
│   │   ├── complexity.py
│   │   ├── schema.py
│   │   ├── engine.py
│   │   └── rules/
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── missing_index.py
│   │       ├── select_star.py
│   │       ├── leading_wildcard.py
│   │       ├── function_on_column.py
│   │       ├── implicit_cast.py
│   │       ├── no_limit.py
│   │       ├── deep_pagination.py
│   │       ├── or_condition.py
│   │       └── subquery_to_join.py
│   ├── optimizer.py
│   └── diagnostics/
│       ├── __init__.py
│       ├── checks.py
│       ├── installer.py
│       └── report.py
├── gui/widgets/diagnostics_dialog.py
├── sql-coach-onefile.spec
└── tests/test_complexity.py 等 7 个新测试文件
```

### 修改

| 文件 | 改动 |
|------|------|
| `sql_coach/models.py` | `Report`/`Config` 增量字段 + `Complexity` |
| `sql_coach/coach.py` | `analyze()` 增加 schema / 评分 / 分流 |
| `sql_coach/cli.py` | `--engine`、`doctor` 子命令 |
| `sql_coach/interactive.py` | 展示引擎来源与复杂度 |
| `gui/app.py` | 启动自检 |
| `gui/widgets/report_view.py` | 引擎 / 复杂度徽章 |
| `gui/widgets/settings_dialog.py` | 分流配置 + 修复丢字段 bug |
| `.github/workflows/build-gui.yml` | 单文件 exe 产物 |

## 16. 不改动清单

- `sql_coach/ai/*`（含 base / factory / deepseek / openai_adapter / ollama / mock）
- `sql_coach/db/*`
- `sql_coach/engine/*`
- `sql_coach/report/*`
- `sql_coach/cache.py`
- `tests/` 下现有测试文件
