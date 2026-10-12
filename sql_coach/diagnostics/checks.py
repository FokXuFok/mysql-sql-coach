"""启动环境自检：逐项检查并返回结构化结果。"""
import os
import sys
from dataclasses import dataclass
from importlib.util import find_spec

from ..models import Config


@dataclass
class CheckResult:
    name: str
    status: str        # ok / warn / fail
    message: str
    fix_hint: str = ""
    auto_fixable: bool = False
    key: str = ""      # 机器可读标识（供修复分支等逻辑判断，勿依赖展示名）


def check_env_file(env_path: str) -> CheckResult:
    if os.path.exists(env_path):
        return CheckResult("配置文件 .env", "ok", f"已找到 {env_path}", key="env_file")
    return CheckResult("配置文件 .env", "warn", f"未找到 {env_path}",
                       fix_hint="将自动生成模板，请填写数据库与 API Key",
                       auto_fixable=True, key="env_file")


def check_mysql(config: Config) -> CheckResult:
    if config.mock:
        return CheckResult("MySQL 连接", "warn", "当前为模拟模式，跳过数据库连接", key="mysql")
    from ..db.connector import DBConnector
    conn = DBConnector(config.db)
    try:
        ok = conn.connect()
    finally:
        conn.close()
    if ok:
        return CheckResult(
            "MySQL 连接", "ok",
            f"已连接 {config.db.host}:{config.db.port}/{config.db.database}", key="mysql")
    return CheckResult("MySQL 连接", "fail", "无法连接 MySQL（本地算法仍可用）",
                       fix_hint=_mysql_hint(), key="mysql")


def _mysql_hint() -> str:
    if sys.platform.startswith("win"):
        return ("安装: winget install Oracle.MySQL    或    "
                "Docker: docker run -d -p 3306:3306 -e MYSQL_ROOT_PASSWORD=yourpass mysql:8")
    if sys.platform == "darwin":
        return "安装: brew install mysql && brew services start mysql"
    return ("安装: sudo apt-get install mysql-server    或    "
            "Docker: docker run -d -p 3306:3306 -e MYSQL_ROOT_PASSWORD=yourpass mysql:8")


def check_ai(config: Config, probe: bool = False) -> CheckResult:
    if config.mock:
        return CheckResult("AI 配置", "warn", "当前为模拟模式，不调用 AI", key="ai")
    if config.model == "ollama":
        if probe and not _probe_ollama(config.ollama_url):
            return CheckResult("AI 配置", "fail", "无法连接 Ollama（本地算法仍可用）",
                               fix_hint="确认已执行 ollama serve", key="ai")
        return CheckResult("AI 配置", "ok", f"Ollama 本地模型: {config.ollama_url}", key="ai")
    key = config.deepseek_api_key if config.model == "deepseek" else config.openai_api_key
    if not key or not key.strip() or key.strip() == "sk-xxx":
        return CheckResult("AI 配置", "fail",
                           f"{config.model} 未配置有效 API Key（复杂 SQL 需要）",
                           fix_hint="在 .env 填写对应 API Key，或在设置里改为本地模式", key="ai")
    return CheckResult("AI 配置", "ok", f"{config.model} API Key 已配置", key="ai")


def _probe_ollama(ollama_url: str) -> bool:
    """轻量试连 Ollama；仅在显式 probe 时调用，默认不联网。"""
    try:
        import httpx
        httpx.get(f"{ollama_url}/api/tags", timeout=2.0)
        return True
    except Exception:  # noqa: BLE001 - 试连失败统一视为不可用
        return False


def check_runtime() -> CheckResult:
    v = sys.version_info
    if (v.major, v.minor) < (3, 10):
        return CheckResult("运行环境", "fail", f"Python {v.major}.{v.minor} 过低，需 3.10+",
                           key="runtime")
    mode = "打包运行" if getattr(sys, "frozen", False) else "源码运行"
    base = f"Python {v.major}.{v.minor}.{v.micro}（{mode}）"
    if not getattr(sys, "frozen", False):
        missing = []
        for mod in ("PySide6", "matplotlib"):
            # 只探测是否存在，不真正 import：matplotlib 延迟加载以省启动时间。
            try:
                if find_spec(mod) is None:
                    missing.append(mod)
            except (ImportError, ValueError):
                missing.append(mod)
        if missing:
            return CheckResult("运行环境", "warn",
                               f"{base}；缺少依赖: {', '.join(missing)}",
                               fix_hint=f"pip install {' '.join(missing)}", key="runtime")
    return CheckResult("运行环境", "ok", base, key="runtime")


def run_all(config: Config, env_path: str = ".env", probe: bool = False) -> list[CheckResult]:
    return [check_env_file(env_path), check_mysql(config),
            check_ai(config, probe=probe), check_runtime()]
