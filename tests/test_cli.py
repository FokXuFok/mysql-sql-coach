# tests/test_cli.py
import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from sql_coach.cli import main


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    # 不硬编码版本号，避免每次升版本都要改测试
    from sql_coach import __version__
    assert __version__ in result.output


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "analyze" in result.output


def test_cli_analyze_help():
    runner = CliRunner()
    result = runner.invoke(main, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "--mock" in result.output
    assert "--model" in result.output


def test_cli_analyze_mock_mode():
    """Test analyze command in mock mode with mocked SQLCoach."""
    runner = CliRunner()

    mock_report = MagicMock()
    mock_report.sql_info.raw_sql = "SELECT * FROM t"
    mock_report.explain = None
    mock_report.analysis.optimized_sql = "SELECT id FROM t"
    mock_report.analysis.index_ddls = []
    mock_report.analysis.problems = []
    mock_report.analysis.explanation = "test"
    mock_report.benchmark = None
    mock_report.index_impact = None

    with patch("sql_coach.cli.SQLCoach") as mock_coach_cls, \
         patch("sql_coach.cli.pyperclip"):
        mock_coach = MagicMock()
        mock_coach.connect.return_value = True
        mock_coach.analyze.return_value = mock_report
        mock_coach_cls.return_value = mock_coach

        result = runner.invoke(main, ["analyze", "SELECT * FROM t", "--mock"],
                               input="2\n")

    assert result.exit_code == 0
    assert mock_coach.analyze.called


def test_cli_config_init():
    """Test config init command creates .env file."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["config", "init"])
        assert result.exit_code == 0
        import os
        assert os.path.exists(".env")


def test_cli_has_doctor_command():
    from click.testing import CliRunner
    from sql_coach.cli import main
    result = CliRunner().invoke(main, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "自检" in result.output or "doctor" in result.output.lower()


def test_cli_doctor_has_probe_option():
    from click.testing import CliRunner
    from sql_coach.cli import main
    result = CliRunner().invoke(main, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "--probe" in result.output


def test_cli_analyze_has_engine_option():
    from click.testing import CliRunner
    from sql_coach.cli import main
    result = CliRunner().invoke(main, ["analyze", "--help"])
    assert "--engine" in result.output


def test_cli_analyze_has_measure_index_option():
    """analyze 命令应暴露 --measure-index 开关。"""
    from click.testing import CliRunner
    from sql_coach.cli import main
    result = CliRunner().invoke(main, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "--measure-index" in result.output


def test_cli_analyze_passes_index_impact():
    """CLI 应把 report.index_impact 传给 format_report。"""
    runner = CliRunner()
    mock_report = MagicMock()
    mock_report.sql_info.raw_sql = "SELECT * FROM t"
    mock_report.explain = None
    mock_report.analysis.optimized_sql = "SELECT id FROM t"
    mock_report.analysis.index_ddls = []
    mock_report.analysis.problems = []
    mock_report.analysis.explanation = "test"
    mock_report.benchmark = None
    mock_report.engine_used = "ai"
    mock_report.complexity = None
    mock_report.index_impact = "SENTINEL"

    with patch("sql_coach.cli.SQLCoach") as mock_coach_cls, \
         patch("sql_coach.cli.pyperclip"), \
         patch("sql_coach.cli.format_report") as mock_fmt:
        mock_fmt.return_value = "报告"
        mock_coach = MagicMock()
        mock_coach.connect.return_value = True
        mock_coach.analyze.return_value = mock_report
        mock_coach_cls.return_value = mock_coach
        result = runner.invoke(main, ["analyze", "SELECT * FROM t", "--mock"],
                               input="2\n")

    assert result.exit_code == 0
    assert mock_fmt.call_args.kwargs.get("index_impact") == "SENTINEL"


def test_cli_analyze_passes_engine_used():
    """M9: CLI 应把 report.engine_used 传给 format_report。"""
    runner = CliRunner()
    mock_report = MagicMock()
    mock_report.sql_info.raw_sql = "SELECT * FROM t"
    mock_report.explain = None
    mock_report.analysis.optimized_sql = "SELECT id FROM t"
    mock_report.analysis.index_ddls = []
    mock_report.analysis.problems = []
    mock_report.analysis.explanation = "test"
    mock_report.benchmark = None
    mock_report.engine_used = "local"
    mock_report.complexity = None

    with patch("sql_coach.cli.SQLCoach") as mock_coach_cls, \
         patch("sql_coach.cli.pyperclip"), \
         patch("sql_coach.cli.format_report") as mock_fmt:
        mock_fmt.return_value = "报告"
        mock_coach = MagicMock()
        mock_coach.connect.return_value = True
        mock_coach.analyze.return_value = mock_report
        mock_coach_cls.return_value = mock_coach
        result = runner.invoke(main, ["analyze", "SELECT * FROM t", "--mock"],
                               input="2\n")

    assert result.exit_code == 0
    assert mock_fmt.call_args.kwargs.get("engine_used") == "local"


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


def test_interactive_analyze_one_passes_engine_used(monkeypatch):
    """M9: 交互模式应把 report.engine_used 传给 format_report。"""
    from unittest.mock import MagicMock, patch
    from sql_coach.interactive import analyze_one
    from sql_coach.models import AnalysisResult, SQLInfo
    from sql_coach.coach import Report

    coach = MagicMock()
    coach.analyze.return_value = Report(
        sql_info=SQLInfo(raw_sql="SELECT 1", sql_type="SELECT", tables=[], columns=[],
                         where_conditions=[], join_tables=[], order_by=[]),
        explain=None,
        analysis=AnalysisResult(problems=[], optimized_sql="SELECT 1",
                                index_ddls=[], explanation="ok"),
        benchmark=None,
        engine_used="local",
        complexity=None,
    )
    with patch("sql_coach.interactive.format_report") as mock_fmt:
        mock_fmt.return_value = "报告"
        analyze_one(coach, "SELECT 1")
    assert mock_fmt.call_args.kwargs.get("engine_used") == "local"


def test_interactive_banner_is_neutral():
    """banner 文案不再硬编码 AI。"""
    import inspect
    from sql_coach import interactive
    src = inspect.getsource(interactive.run_cli)
    assert "AI 慢查询优化教练" not in src
    assert "慢查询优化教练" in src


# --------------------------------------------------------------------- nl2sql 子命令


def _nl_result(**kwargs):
    """构造 NLQueryResult，便于 CLI 测试。"""
    from sql_coach.models import NLQuery, NLQueryResult
    nq = NLQuery(intent="select", tables=["orders"], columns=[], conditions=[],
                 aggregates=[], order_by=[], group_by=[], limit=10,
                 raw_text="查询10条订单")
    base = dict(nl_query=nq, generated_sql="SELECT * FROM orders LIMIT 10;")
    base.update(kwargs)
    return NLQueryResult(**base)


def test_cli_has_nl2sql_command():
    runner = CliRunner()
    result = runner.invoke(main, ["nl2sql", "--help"])
    assert result.exit_code == 0
    assert "--execute" in result.output
    assert "--mock" in result.output


def test_cli_nl2sql_mock_mode():
    runner = CliRunner()
    with patch("sql_coach.cli.SQLCoach") as coach_cls:
        coach = MagicMock()
        coach.connect.return_value = True
        coach.generate_sql.return_value = _nl_result()
        coach_cls.return_value = coach

        result = runner.invoke(main, ["nl2sql", "查询10条订单", "--mock"])

    assert result.exit_code == 0
    assert "SELECT * FROM orders LIMIT 10;" in result.output
    assert "orders" in result.output
    assert coach.generate_sql.called


def test_cli_nl2sql_passes_execute_flag():
    runner = CliRunner()
    with patch("sql_coach.cli.SQLCoach") as coach_cls:
        coach = MagicMock()
        coach.connect.return_value = True
        coach.generate_sql.return_value = _nl_result()
        coach_cls.return_value = coach

        result = runner.invoke(main, ["nl2sql", "查询10条订单", "--no-execute", "--mock"])

    assert result.exit_code == 0
    assert coach.generate_sql.call_args.kwargs.get("execute") is False


def test_cli_nl2sql_prints_result_table():
    runner = CliRunner()
    with patch("sql_coach.cli.SQLCoach") as coach_cls:
        coach = MagicMock()
        coach.connect.return_value = True
        coach.generate_sql.return_value = _nl_result(
            generated_sql="SELECT city, COUNT(*) FROM users GROUP BY city;",
            columns=["city", "cnt"], rows=[("北京", 3), ("上海", 2)], executed=True)
        coach_cls.return_value = coach

        result = runner.invoke(main, ["nl2sql", "统计每个城市的用户数量", "--mock"])

    assert result.exit_code == 0
    assert "北京" in result.output
    assert "cnt" in result.output


def test_cli_nl2sql_caps_rows_at_50():
    runner = CliRunner()
    rows = [(f"name{i}", i) for i in range(55)]
    with patch("sql_coach.cli.SQLCoach") as coach_cls:
        coach = MagicMock()
        coach.connect.return_value = True
        coach.generate_sql.return_value = _nl_result(
            columns=["name", "n"], rows=rows, executed=True)
        coach_cls.return_value = coach

        result = runner.invoke(main, ["nl2sql", "查询所有订单", "--mock"])

    assert result.exit_code == 0
    assert "55" in result.output  # 总数提示


def test_cli_nl2sql_prints_error_without_raising():
    runner = CliRunner()
    with patch("sql_coach.cli.SQLCoach") as coach_cls:
        coach = MagicMock()
        coach.connect.return_value = True
        coach.generate_sql.return_value = _nl_result(
            generated_sql="SELECT * FROM unknown_table;", error="Table 'unknown_table' doesn't exist")
        coach_cls.return_value = coach

        result = runner.invoke(main, ["nl2sql", "查询订单", "--mock"])

    assert result.exit_code == 0
    assert "doesn't exist" in result.output


def test_cli_nl2sql_prints_warnings():
    runner = CliRunner()
    with patch("sql_coach.cli.SQLCoach") as coach_cls:
        coach = MagicMock()
        coach.connect.return_value = True
        coach.generate_sql.return_value = _nl_result(warnings=["未能识别表名"])
        coach_cls.return_value = coach

        result = runner.invoke(main, ["nl2sql", "查询订单", "--mock"])

    assert result.exit_code == 0
    assert "未能识别表名" in result.output


# --------------------------------------------------------------------- 交互模式 NL 入口


def test_interactive_nl_one_prints_sql(capsys):
    from unittest.mock import MagicMock
    from sql_coach.interactive import nl_one
    from sql_coach.models import NLQuery, NLQueryResult

    coach = MagicMock()
    coach.generate_sql.return_value = NLQueryResult(
        nl_query=NLQuery(intent="select", tables=["orders"], columns=[],
                         conditions=[], aggregates=[], order_by=[],
                         group_by=[], limit=10, raw_text="查询10条订单"),
        generated_sql="SELECT * FROM orders LIMIT 10;",
    )
    nl_one(coach, "查询10条订单")
    out = capsys.readouterr().out
    assert "SELECT * FROM orders LIMIT 10;" in out
    assert "orders" in out


def test_interactive_nl_prefix_routes_to_generate_sql():
    from unittest.mock import MagicMock, patch
    from sql_coach import interactive
    from sql_coach.models import Config, DBConfig, NLQuery, NLQueryResult

    config = Config(db=DBConfig("h", 3306, "u", "p", "d"), model="deepseek",
                    deepseek_api_key="", openai_api_key="", ollama_url="http://x",
                    benchmark_runs=3, mock=True)
    coach = MagicMock()
    coach.connect.return_value = True
    coach.generate_sql.return_value = NLQueryResult(
        nl_query=NLQuery(intent="select", tables=["orders"], columns=[],
                         conditions=[], aggregates=[], order_by=[],
                         group_by=[], limit=10, raw_text="查询10条订单"),
        generated_sql="SELECT * FROM orders LIMIT 10;",
    )
    inputs = iter(["/nl 查询10条订单", "q"])
    with patch.object(interactive, "load_config", return_value=config), \
         patch.object(interactive, "SQLCoach", return_value=coach), \
         patch.object(interactive.console, "input",
                      side_effect=lambda *a, **k: next(inputs)):
        interactive.run_cli()

    assert coach.generate_sql.called
    assert coach.generate_sql.call_args[0][0] == "查询10条订单"
