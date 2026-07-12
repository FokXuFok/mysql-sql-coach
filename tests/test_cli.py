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
