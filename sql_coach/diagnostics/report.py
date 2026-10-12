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
