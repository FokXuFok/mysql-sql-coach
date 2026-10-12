# tests/test_cli.py
import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from sql_coach.cli import main


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


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
