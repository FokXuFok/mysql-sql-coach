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
        if r.key == "env_file":
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
