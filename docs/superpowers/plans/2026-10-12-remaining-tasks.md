# 剩余任务交接 · 本地算法分流功能

> 生成时间：2026-10-12 00:25
> 分支：`feat/local-optimizer-bootstrap`（**尚未合并到 `master`**）
> 关联文档：`docs/superpowers/specs/2026-10-11-local-optimizer-and-bootstrap-design.md`（设计）
> 　　　　　`docs/superpowers/plans/2026-10-11-local-optimizer-and-bootstrap.md`（实施计划）

---

## 一、当前状态

| 项 | 状态 |
|----|------|
| 计划 Task 0–18 | ✅ **全部实现并提交** |
| 领先 master | 27 个提交 |
| 全量测试 | ✅ `199 passed`（master 基线 129） |
| 每个任务的审查 | ✅ 均过"规格符合性 + 代码质量"两阶段审查 |
| 工作区 | 干净（仅 `.wheels/`、`.workbuddy-ai/` 两个未跟踪目录） |

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

### P2 — 遗留质量项（非阻塞，可延后）

| 编号 | 问题 | 位置 |
|------|------|------|
| I2 | 连库失败时弹**模态** `QMessageBox`，无数据库环境会阻塞启动（**改动前就存在**） | `gui/main_window.py` `_check_db_connection` |
| M2 | 评分未统计"多列 `GROUP BY`" | `local/complexity.py` |
| M3 | 评分未识别"嵌套函数表达式" | `local/complexity.py` |
| M4 | 运行环境自检只查 Python 版本 | `diagnostics/checks.py` |
| M5 | `check_ai` 无轻量试连 | `diagnostics/checks.py` |
| M6 | 用 `name.startswith("配置文件")` 判断修复分支，改名即静默失效 | `diagnostics/installer.py` |
| M7 | `copy_hint` 失败时 UI 无任何提示 | `gui/widgets/diagnostics_dialog.py` |
| M8 | `config is None` 时把所有可修复项乐观标为 ok | `gui/widgets/diagnostics_dialog.py` |
| M9 | 本地模式下仍打印"🤖 AI 分析中" | `sql_coach/cli.py`、`sql_coach/interactive.py` |
| M10 | `_explain` 的"未校验"提示与规则无关时也会追加 | `local/engine.py` |
| M11 | `NoLimitRule` 用子串判断 `LIMIT` | `local/rules/no_limit.py` |

---

## 四、继续开发的推荐顺序

1. 先做 **P0-1**（功能缺口，有 spec 依据）→ 跑全量测试
2. **P0-2**（.gitignore）→ 顺手清理 `git status`
3. **P0-3**（spec 差异说明）→ 文档收口
4. **P1-1 / P1-3**（校验 YAML、试打包）
5. **P1-2**（合并分支）
6. P2 视需要处理

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
