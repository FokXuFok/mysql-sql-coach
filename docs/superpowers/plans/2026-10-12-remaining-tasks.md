# 剩余任务交接 · 本地算法分流功能

> 生成时间：2026-10-12 00:25（**2026-10-12 中午更新：P0/P1/P2 已全部完成**）
> 分支：已合并到 `master`（原特性分支 `feat/local-optimizer-bootstrap` 保留）
> 关联文档：`docs/superpowers/specs/2026-10-11-local-optimizer-and-bootstrap-design.md`（设计）
> 　　　　　`docs/superpowers/plans/2026-10-11-local-optimizer-and-bootstrap.md`（实施计划）

---

## 一、当前状态

| 项 | 状态 |
|----|------|
| 计划 Task 0–18 | ✅ **全部实现并提交** |
| P0 / P1 / P2 后续项 | ✅ **全部完成**（见第三、四节） |
| 分支 | ✅ 已 `--no-ff` 合并到 `master`（merge commit `eabb44d`） |
| 全量测试 | ✅ `235 passed`（master 原基线 129） |
| 每个任务的审查 | ✅ 均过"规格符合性 + 代码质量"两阶段审查 |
| 工作区 | 干净（`.wheels/`、`.workbuddy-ai/`、打包目录已 gitignore） |
| 远程 | ⚠️ 领先 `origin/master` 若干提交，**尚未 push**（对外操作，待确认） |

### 已实现的核心能力

- **本地规则引擎**：`sql_coach/local/`（复杂度评分、schema 读取、9 条规则、`LocalOptimizer`）
- **自动分流**：`sql_coach/optimizer.py` 的 `select_optimizer`，`SQLCoach.analyze()` 已集成
  - 简单/中等 → 本地（毫秒级，不需要 API Key）；复杂 → AI
  - 可用 `OPTIMIZER_MODE=auto|local|ai` 或 CLI `--engine` 强制
- **启动自检**：`sql_coach/diagnostics/`（4 项检查 + 分层修复）；CLI `sql-coach doctor [--fix]`；GUI 启动对话框
- **单文件打包**：`sql-coach-onefile.spec` + CI 改为 onefile 主产物 / onedir 备选

### 已验证的行为（冒烟测试实测）

```
[简单] engine=local  level=simple  score=0   problems=2  ddls=1
[复杂] engine=ai     level=complex score=11
[强制 local] engine=local        [强制 ai] engine=ai
改写叠加: SELECT id, created_at FROM orders WHERE (created_at >= '2026-01-01 00:00:00'
          AND created_at < DATE_ADD('2026-01-01', INTERVAL 1 DAY))
```

---

## 二、⚠️ 环境注意事项（新会话必读）

这几条是踩过的坑，不记住会浪费时间：

1. **pip 默认镜像不可用**
   本机 pip 配置的清华镜像经代理不可用（报 `Could not find a version ... from versions: none`）。
   必须显式指定 pypi.org：
   ```bash
   ./.venv/Scripts/python.exe -m pip install --index-url https://pypi.org/simple <包名>
   ```

2. **PySide6 大 wheel 会被代理截断**
   直接 `pip install PySide6` 会因 `IncompleteRead` 失败。已用可续传脚本下载到 `.wheels/`：
   ```bash
   ./.venv/Scripts/python.exe .wheels/_fetch.py      # 断点续传（必要时重跑）
   ./.venv/Scripts/python.exe -m pip install --no-index --no-deps \
       .wheels/shiboken6-*.whl .wheels/pyside6_essentials-*.whl .wheels/pyside6_addons-*.whl
   ```
   注意：**不要装 `pyside6` 元包**（它会要求 `PySide6-WebEngine`，本项目不需要）。
   `.wheels/` 已下载好，环境已就绪，通常无需重装。

3. **测试命令**
   ```bash
   ./.venv/Scripts/python.exe -m pytest tests/ -q -o addopts=""
   ```
   `-o addopts=""` 用于关掉 pyproject 里默认的覆盖率输出。
   GUI 测试如遇平台插件问题：加 `QT_QPA_PLATFORM=offscreen`。

4. **Python 解释器**：统一用 `./.venv/Scripts/python.exe`（不要用系统 python）。

---

## 三、剩余任务

> **2026-10-12 更新：P0-1 ~ P0-3、P1-1 ~ P1-3 已全部完成。**
> P0-1 `81e811c`（本地引擎失败降级 AI）、P0-2 `cd5358f`（gitignore）、P0-3 `92063c5`（spec 第 17 节）、
> P1-1 CI YAML 校验通过、P1-2 已 `--no-ff` 合并到 master `eabb44d`、P1-3 打包成功
> （`dist-onefile/sql-coach-gui.exe`，83MB 单文件）。
> 以下原始描述保留作记录。

### P0 — 合并前应当完成

#### P0-1　本地引擎整体失败时降级到 AI（**未实现，spec §12 明确要求**）

- **现状**：`LocalOptimizer._safe` 只隔离**单条规则**的异常（`sql_coach/local/engine.py`）；
  若引擎级异常抛出，`coach.py` 的 `analyze()` 没有 try/except 兜底，会直接向上抛。
- **位置**：`sql_coach/coach.py`，`analyze()` 中 `analysis = optimizer.optimize(...)` 那一处。
- **改法**：
  ```python
  try:
      analysis = optimizer.optimize(sql_info, explain, schema, on_chunk=on_chunk)
  except Exception as e:
      if engine_name == "local":
          logger.warning("本地规则引擎失败，降级到 AI: %s", e)
          ai_engine = self.ai
          optimizer = AIOptimizerAdapter(ai_engine)
          engine_name = ai_engine.name()
          analysis = optimizer.optimize(sql_info, explain, schema, on_chunk=on_chunk)
      else:
          raise
  ```
  顶部 import 改为 `from .optimizer import select_optimizer, AIOptimizerAdapter`。
- **测试**：新增 `tests/test_coach.py::test_coach_falls_back_to_ai_when_local_engine_fails`
  （patch `sql_coach.optimizer.LocalOptimizerAdapter` 让其 `optimize` 抛异常，
  断言最终 `report.engine_used == "deepseek"` 且 AI 被调用）。
  ⚠️ 注意 patch 的目标是 `sql_coach.optimizer.LocalOptimizerAdapter`（不是 `sql_coach.coach.*`）。

#### P0-2　`.gitignore` 补两个目录

- **现状**：`.wheels/`（约 125MB 的 wheel 缓存）与 `.workbuddy-ai/` 处于"未跟踪但未被忽略"状态，
  `git status` 持续提示；一旦有人 `git add -A` 会把 125MB 二进制提交进历史。
- **改法**：在 `.gitignore` 追加：
  ```
  # 依赖 wheel 缓存
  .wheels/

  # WorkBuddy 项目数据
  .workbuddy-ai/
  ```

#### P0-3　回填 spec 的"实现差异说明"（内容已备好，未落盘）

终审指出 spec / plan / 代码存在多处漂移。建议在
`docs/superpowers/specs/2026-10-11-local-optimizer-and-bootstrap-design.md` 末尾追加一节
`## 17. 实现说明（与设计的差异）`，内容包括：

1. **接口落定**：`Rule` 方法签名最终为 `check(self, ctx: RuleContext)`（非 `check(self, sql_info, schema)`）；
   分流入口为 `select_optimizer(config, complexity, ai_factory)`。
2. **相关子查询**：设计曾列 +5，实现阶段因正则启发式双向不可靠而**移除**（只保留子查询 +3）。
3. **复杂度评分**：`多列分组（≥2 列）+1` 与 `嵌套函数表达式 +2` **未实现**。
4. **自动改写收敛为 2 条**（`select_star` / `function_on_column`），并说明三条实现期补强的守卫
   （多表不展开 `SELECT *`、多表跳过 `MissingIndexRule`、多条改写叠加）。
5. **启动自检缩减**：运行环境只查 Python 版本（未查 VC++ 运行库/字体）；
   AI 检查只判 Key 存在性（未做轻量试连）；分层修复只实现"生成 `.env` 模板"，
   "源码模式自动 pip install 依赖"**未实现**；类名为 `apply_auto_fixes`（非 `AutoFixer`）。
6. **测试清单例外**：§16 把 `tests/` 现有文件列为不改动，实际**追加了**用例（既有用例未改）。
   master 测试基线实为 **129**（非设计稿所称 134）。

### P1 — 收口

#### P1-1　校验 CI YAML 语法（未做）

`pyyaml` 未安装且当时无网络。明天可：
```bash
./.venv/Scripts/python.exe -m pip install --index-url https://pypi.org/simple pyyaml
./.venv/Scripts/python.exe -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('.github/workflows/build-gui.yml').read_text(encoding='utf-8')); print('YAML OK')"
```
（该文件是照计划逐字改写的，已人工核对缩进，但未经机器解析。）

#### P1-2　合并分支

功能已完成且测试全绿。可用 `finishing-a-development-branch` 流程合并 `feat/local-optimizer-bootstrap` → `master`，
或先开 PR 审阅。

#### P1-3　（可选）实际打包一次 onefile exe 验证

`sql-coach-onefile.spec` 只做过 `ast.parse` 语法校验，**未真正构建过**。
可执行：`pyinstaller sql-coach-onefile.spec --clean --noconfirm`（需先装 pyinstaller）。

### P2 — 遗留质量项 ✅ **已全部完成**（2026-10-12）

| 编号 | 问题 | 修复提交 |
|------|------|---------|
| I2 | 连库失败弹**模态** `QMessageBox` → 改为非模态 `show()` + 引用保持，启动路径不再阻塞 | `276c8d5` |
| M2 | 评分未统计"多列 `GROUP BY`" → 补 `+1`（按**顶层逗号**计数，函数内逗号不虚高） | `b430f59`、`dbfd396` |
| M3 | 评分未识别"嵌套函数表达式" → 补 `+2`（排除 `IN/EXISTS` 等关键字伪函数） | `b430f59`、`dbfd396` |
| M4 | 运行环境自检只查 Python 版本 → 补依赖存在性检查（用 `find_spec`，**不真正 import**，避免拖慢启动） | `1770425`、`285bfe4` |
| M5 | `check_ai` 无轻量试连 → 加 `probe` 参数（**默认 False 不联网**；Ollama 才试连），CLI `doctor --probe` 可选启用 | `1770425` |
| M6 | 用 `name.startswith("配置文件")` 判断修复分支 → 改用机器可读 `CheckResult.key` | `1770425`、`285bfe4` |
| M7 | `copy_hint` 失败无提示 → 按钮文案显示"❌ 复制失败，请手动选择命令" | `276c8d5` |
| M8 | `config is None` 时乐观标 ok → 改为只对 `applied=True` 的项标 ok | `276c8d5` |
| M9 | 本地模式仍显示"AI"字样 → 修 `formatter.py`（加可选 `engine_used` 参数）、`cli.py`、`interactive.py`、`report_view.py`、`main_window.py` 状态栏 | `e7a3957`、`c3dc9b1` |
| M10 | `_explain` 的"未校验"提示过度触发 → 仅命中 `missing_index` 且未校验时才追加 | `b430f59` |
| M11 | `NoLimitRule` 用子串判断 `LIMIT` → 改词边界正则 `\bLIMIT\b` | `b430f59` |

> **说明**：M9 首轮只改了 GUI 与提示文案，审查发现 CLI/交互模式实际输出由
> `sql_coach/report/formatter.py` 渲染（硬编码 `🤖 AI 解释:`），故补做 `c3dc9b1`——
> 给 `format_report()` 增加**可选参数** `engine_used: str = "ai"`（默认行为不变，属对
> "`report/` 不改动"的纯增量例外）。
>
> 全量测试：**235 passed**（P2 开工前为 200），进程正常退出。

---

## 四、继续开发的推荐顺序

> **2026-10-12 更新：以下 1–5 步已全部完成，6（P2）亦已完成。**
> 当前无未完成的既定任务；后续可选方向见文末"下一步可选"。

原推荐顺序（保留作记录）：

1. 先做 **P0-1**（功能缺口，有 spec 依据）→ 跑全量测试
2. **P0-2**（.gitignore）→ 顺手清理 `git status`
3. **P0-3**（spec 差异说明）→ 文档收口
4. **P1-1 / P1-3**（校验 YAML、试打包）
5. **P1-2**（合并分支）
6. P2 视需要处理

---

## 下一步可选（均非阻塞）

1. **`git push`** 到 `origin/master`（对外操作，需你确认）
2. 用真实 MySQL（`docker/` 里的测试库，10 万行 orders）跑一次端到端，
   看本地引擎的索引建议 + benchmark 提速在真实数据上的表现
3. 实机试跑 `dist-onefile/sql-coach-gui.exe`，验证 onefile 启动与自检对话框
4. 若要把本地规则覆盖面做大：可继续加规则（如 `NOT IN`、`IS NULL`、`UNION` 去重、
   隐式排序等），并考虑给 `MissingIndexRule` 支持多表（需借助 schema 反查列归属）

## 五、快速自检命令

```bash
# 全量测试
./.venv/Scripts/python.exe -m pytest tests/ -q -o addopts=""

# 分流是否生效（预期：简单→local，复杂→ai）
./.venv/Scripts/python.exe -c "
from sql_coach.models import Config, DBConfig
from sql_coach.coach import SQLCoach
c = Config(db=DBConfig('localhost',3306,'root','','test'), model='deepseek',
           deepseek_api_key='', openai_api_key='', ollama_url='http://localhost:11434',
           benchmark_runs=1, mock=True, optimizer_mode='auto')
for sql in ['SELECT * FROM orders WHERE status=\'pending\'',
            'SELECT ROW_NUMBER() OVER (ORDER BY a.id) FROM a JOIN b ON a.id=b.id JOIN c ON b.id=c.id']:
    r = SQLCoach(c).analyze(sql)
    print(r.engine_used, r.complexity.level, r.complexity.score)
"
```

---

## 五、本轮追加（2026-10-12 下午）

### 5.1 push
已推送 `master` 到 `origin`（`6d8c77a..dd7242d`，随后含本轮新提交）。
注意：本机 git 的 `credential.helper=helper-selector` 在非交互环境下会挂起，
推送时用 `gh auth token` 做一次性凭据注入（需先用 `-c credential.helper=` 清空原 helper 列表）：
```bash
export GH_TOKEN=$(gh auth token)
git -c credential.helper= -c credential.helper='!f() { echo username=x-access-token; echo "password=$GH_TOKEN"; }; f' push origin master
```

### 5.2 真实 MySQL 端到端 + 索引收益实测（`test` 库，orders 10 万行）
工具输出正确：`EXPLAIN type=ALL rows=100070`、识别"status 缺索引"、给出
`CREATE INDEX idx_orders_status ON orders(status);`。

**但实测暴露一个重要事实——索引收益取决于选择性：**

| 谓词 | 命中行数 | 选择性 | 建索引前 | 建索引后 | 提速 |
|------|---------|--------|---------|---------|------|
| `status='pending'` | 33,225 | 33.2% | 243.5 ms | 244.0 ms | **1.0x** |
| `amount>999.5` | 50 | 0.05% | 36.7 ms | 0.7 ms | **54.4x** |

低选择性时 MySQL 即便用了索引（`type=ref`）也要回表 3.3 万次，成本≈全表扫描。
README 宣称的"50-100x"只在**高选择性**谓词上成立。
（实测后已删除所建索引，测试库恢复"故意无索引"的初始状态。）

### 5.3 重打包并试跑 exe
- 重新构建 `dist-onefile/sql-coach-gui.exe`（83MB，含本轮全部修复）。
- **exe 同目录无 `.env`** → 按设计降级到模拟模式，进程正常存活、不崩溃（stderr 提示
  `Access denied ... (using password: NO)`，符合预期）。
- **放入 `.env` 后** → 启动成功且 **stderr 无任何连接错误**，说明真实连库正常。
  （验证用的 `.env` 副本已删除，未留在产物目录。）

### 5.4 扩展本地规则（9 条 → 13 条）
新增 4 条（全部 `risk="safe"`，只建议不改写）：
- `negation.py` 否定条件（`!=`/`<>`/`NOT IN`/`NOT LIKE`/`NOT EXISTS`）无法有效用索引
- `order_by_rand.py` `ORDER BY RAND()` 全表随机排序
- `union_dedup.py` `UNION` 去重开销（排除 `UNION ALL`）
- `redundant_distinct.py` `SELECT DISTINCT` 与 `GROUP BY` 同层冗余

审查实测发现并修复了 2 类**用户可见误报**：
1. 字符串字面量/注释内的关键字被误判（如 `note='a!=b'`、`-- a != 1`）
   → 新增 `sql_coach/local/rules/_text.py`（`strip_comments` / `strip_literals` / `clean`），
   4 条新规则匹配前先 `clean()`；**未**动 `leading_wildcard`/`function_on_column`（它们需要匹配字面量内容）。
2. `RedundantDistinctRule` 跨层子查询误报（DISTINCT 与 GROUP BY 分处内外层）
   → 含 `(SELECT` 时保守返回空（宁可漏报不误报）。

全量测试：**253 passed**。

### 5.5 发现的产品改进点（尚未做，供后续参考）
1. **管线内 benchmark 对"建议索引"类问题恒为 ~1.0x**：它比较的是"原 SQL vs 改写后 SQL"，
   而索引建议的价值在"建索引前后"。建议：当 `index_ddls` 非空时，可提供
   "建索引→复测→回滚"的实测模式（或至少在报告里说明该数字不含索引收益）。
2. **索引建议不考虑选择性**：如上表，33% 选择性的列上建索引几乎无效。
   建议在生成 DDL 时附提示（如"该条件选择性可能较低，索引收益有限"），
   或提供基于 `SELECT COUNT(*)` 的选择性估算。
3. **`SELECT *` 展开的列顺序不是表原始顺序**：`SchemaProvider` 读 `information_schema.COLUMNS`
   未加 `ORDER BY ORDINAL_POSITION`，导致改写后列序可能变化（语义等价，但不美观）。
4. 既有 `or_condition` / `no_limit` / `leading_wildcard` 等规则仍有"字面量/注释盲区"，
   可考虑统一接入 `_text.clean`（注意 `leading_wildcard` 需保留字面量匹配）。
