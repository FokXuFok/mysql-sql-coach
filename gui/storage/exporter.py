# gui/storage/exporter.py
"""报告导出 (Markdown / HTML), 不依赖 Qt。"""
from __future__ import annotations

from html import escape

from sql_coach.coach import Report

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>SQL 优化分析报告</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "PingFang SC", sans-serif; margin: 32px; color: #1e1e2e; background: #f9f9f9; }}
  h1 {{ color: #1e66f5; border-bottom: 2px solid #1e66f5; padding-bottom: 8px; }}
  h2 {{ color: #04a5e5; margin-top: 28px; }}
  pre {{ background: #1e1e2e; color: #cdd6f4; padding: 12px 16px; border-radius: 6px; overflow-x: auto; font-family: "JetBrains Mono", Consolas, monospace; }}
  table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
  th {{ background: #1e66f5; color: white; }}
  tr.type-ALL {{ background: #fde2e0; }}
  .problem-critical {{ color: #d20f39; font-weight: bold; }}
  .problem-warning {{ color: #df8e1d; }}
  .problem-info {{ color: #04a5e5; }}
  .benchmark {{ background: white; padding: 12px 16px; border-left: 4px solid #40a02b; border-radius: 4px; }}
  .speedup {{ color: #40a02b; font-weight: bold; font-size: 1.1em; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


class Exporter:
    """报告导出器, 纯 Python。"""

    def to_markdown(self, report: Report) -> str:
        """生成 Markdown 报告。"""
        lines = ["# SQL 优化分析报告", ""]

        # 原始 SQL
        lines.append("## 原始 SQL")
        lines.append("")
        lines.append("```sql")
        lines.append(report.sql_info.raw_sql)
        lines.append("```")
        lines.append("")

        # 执行计划
        if report.explain and report.explain.rows:
            lines.append("## 执行计划")
            lines.append("")
            lines.append("| id | table | type | key | rows | extra |")
            lines.append("|----|-------|------|-----|------|-------|")
            for r in report.explain.rows:
                lines.append(
                    f"| {r.id} | {r.table} | {r.type} | "
                    f"{r.key or 'NULL'} | {r.rows:,} | {r.extra or ''} |"
                )
            lines.append("")

        # 问题列表
        if report.analysis.problems:
            lines.append(f"## 问题列表 ({len(report.analysis.problems)} 项)")
            lines.append("")
            for p in report.analysis.problems:
                lines.append(f"- **[{p.severity}]** `{p.table}`: {p.description}")
                if p.suggestion:
                    lines.append(f"  - 建议: {p.suggestion}")
            lines.append("")

        # 优化后 SQL
        lines.append("## 优化后 SQL")
        lines.append("")
        lines.append("```sql")
        lines.append(report.analysis.optimized_sql)
        lines.append("```")
        lines.append("")

        # 索引建议
        if report.analysis.index_ddls:
            lines.append("## 索引建议")
            lines.append("")
            for ddl in report.analysis.index_ddls:
                lines.append(f"```sql\n{ddl}\n```")
            lines.append("")

        # AI 解释
        if report.analysis.explanation:
            lines.append("## AI 解释")
            lines.append("")
            lines.append(report.analysis.explanation)
            lines.append("")

        # 性能对比
        if report.benchmark:
            b = report.benchmark
            lines.append("## 性能对比")
            lines.append("")
            lines.append("| 指标 | 原始 SQL | 优化 SQL |")
            lines.append("|------|---------|---------|")
            lines.append(f"| 耗时 | {b.original_time:.3f}s | {b.optimized_time:.3f}s |")
            lines.append(f"| 扫描行数 | {b.original_rows:,} | {b.optimized_rows:,} |")
            if b.speedup == float("inf"):
                lines.append("")
                lines.append("**提速: 无限大**")
            else:
                lines.append("")
                lines.append(f"**提速: {b.speedup:.1f}x**")
            lines.append("")

        return "\n".join(lines)

    def to_html(self, report: Report) -> str:
        """生成 HTML 报告 (内联 CSS, 独立文件)。"""
        body = ["<h1>📋 SQL 优化分析报告</h1>"]

        # 原始 SQL
        body.append("<h2>原始 SQL</h2>")
        body.append(f"<pre>{escape(report.sql_info.raw_sql)}</pre>")

        # 执行计划
        if report.explain and report.explain.rows:
            body.append("<h2>执行计划</h2>")
            body.append("<table>")
            body.append("<thead><tr>"
                        "<th>id</th><th>table</th><th>type</th>"
                        "<th>key</th><th>rows</th><th>extra</th>"
                        "</tr></thead>")
            body.append("<tbody>")
            for r in report.explain.rows:
                css = ' class="type-ALL"' if r.type == "ALL" else ""
                body.append(
                    f"<tr{css}><td>{r.id}</td><td>{escape(r.table)}</td>"
                    f"<td>{escape(r.type)}</td>"
                    f"<td>{escape(r.key or 'NULL')}</td>"
                    f"<td>{r.rows:,}</td><td>{escape(r.extra or '')}</td></tr>"
                )
            body.append("</tbody></table>")

        # 问题列表
        if report.analysis.problems:
            body.append(f"<h2>问题列表 ({len(report.analysis.problems)} 项)</h2>")
            body.append("<ul>")
            for p in report.analysis.problems:
                body.append(
                    f'<li><span class="problem-{escape(p.severity)}">'
                    f'[{escape(p.severity)}]</span> '
                    f'<code>{escape(p.table)}</code>: '
                    f'{escape(p.description)}'
                )
                if p.suggestion:
                    body.append(f'<br><em>建议:</em> {escape(p.suggestion)}')
                body.append("</li>")
            body.append("</ul>")

        # 优化后 SQL
        body.append("<h2>优化后 SQL</h2>")
        body.append(f"<pre>{escape(report.analysis.optimized_sql)}</pre>")

        # 索引建议
        if report.analysis.index_ddls:
            body.append("<h2>索引建议</h2>")
            for ddl in report.analysis.index_ddls:
                body.append(f"<pre>{escape(ddl)}</pre>")

        # AI 解释
        if report.analysis.explanation:
            body.append("<h2>AI 解释</h2>")
            body.append(f"<p>{escape(report.analysis.explanation)}</p>")

        # 性能对比
        if report.benchmark:
            b = report.benchmark
            body.append("<h2>性能对比</h2>")
            body.append('<div class="benchmark">')
            body.append("<table>")
            body.append("<thead><tr><th>指标</th><th>原始 SQL</th><th>优化 SQL</th></tr></thead>")
            body.append("<tbody>")
            body.append(
                f"<tr><td>耗时</td><td>{b.original_time:.3f}s</td>"
                f"<td>{b.optimized_time:.3f}s</td></tr>"
            )
            body.append(
                f"<tr><td>扫描行数</td><td>{b.original_rows:,}</td>"
                f"<td>{b.optimized_rows:,}</td></tr>"
            )
            body.append("</tbody></table>")
            if b.speedup == float("inf"):
                body.append('<p class="speedup">提速: 无限大</p>')
            else:
                body.append(f'<p class="speedup">提速: {b.speedup:.1f}x</p>')
            body.append("</div>")

        return _HTML_TEMPLATE.format(body="\n".join(body))

    def save(self, report: Report, path: str, fmt: str) -> None:
        """保存报告到文件, fmt 支持 'markdown' 或 'html'。"""
        if fmt == "markdown":
            content = self.to_markdown(report)
        elif fmt == "html":
            content = self.to_html(report)
        else:
            raise ValueError(f"不支持的导出格式: {fmt} (仅支持 markdown/html)")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
