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
