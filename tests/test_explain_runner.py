# tests/test_explain_runner.py
import json
from unittest.mock import MagicMock

from sql_coach.engine.explain_runner import run_explain, parse_explain_json, ExplainResult


def test_parse_explain_json_simple():
    """Test parsing a simple EXPLAIN JSON output."""
    explain_json = {
        "query_block": {
            "select_id": 1,
            "table": {
                "table_name": "orders",
                "access_type": "ALL",
                "rows_examined_per_scan": 420000,
                "attached_condition": "(`orders`.`status` = 'pending')",
                "using_filesort": False,
                "using_temporary_table": False,
            }
        }
    }
    result = parse_explain_json(json.dumps(explain_json))
    assert isinstance(result, ExplainResult)
    assert len(result.rows) == 1
    assert result.rows[0].table == "orders"
    assert result.rows[0].type == "ALL"
    assert result.rows[0].rows == 420000
    assert result.is_full_scan is True
    assert "orders" in result.missing_indexes


def test_parse_explain_json_with_index():
    """Test parsing EXPLAIN with index used."""
    explain_json = {
        "query_block": {
            "select_id": 1,
            "table": {
                "table_name": "users",
                "access_type": "ref",
                "key": "idx_email",
                "rows_examined_per_scan": 1,
                "attached_condition": None,
            }
        }
    }
    result = parse_explain_json(json.dumps(explain_json))
    assert result.rows[0].type == "ref"
    assert result.rows[0].key == "idx_email"
    assert result.is_full_scan is False
    assert len(result.missing_indexes) == 0


def test_parse_explain_json_join():
    """Test parsing EXPLAIN with JOIN."""
    explain_json = {
        "query_block": {
            "select_id": 1,
            "nested_loop": [
                {"table": {"table_name": "orders", "access_type": "ALL",
                           "rows_examined_per_scan": 1000}},
                {"table": {"table_name": "users", "access_type": "eq_ref",
                           "key": "PRIMARY", "rows_examined_per_scan": 1}},
            ]
        }
    }
    result = parse_explain_json(json.dumps(explain_json))
    assert len(result.rows) == 2
    assert result.rows[0].table == "orders"
    assert result.rows[1].table == "users"
    assert result.is_full_scan is True


def test_run_explain_with_mock_connection():
    """Test run_explain with a mock connection."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    explain_json = {
        "query_block": {
            "select_id": 1,
            "table": {
                "table_name": "orders",
                "access_type": "ALL",
                "rows_examined_per_scan": 500000,
            }
        }
    }
    mock_cursor.fetchone.return_value = (json.dumps(explain_json),)

    result = run_explain(mock_conn, "SELECT * FROM orders")
    assert result.is_full_scan is True
    assert mock_cursor.execute.called


def test_parse_explain_with_filesort():
    """Test detecting Using filesort in Extra."""
    explain_json = {
        "query_block": {
            "select_id": 1,
            "ordering_operation": {
                "using_filesort": True,
                "table": {
                    "table_name": "orders",
                    "access_type": "ref",
                    "key": "idx_status",
                    "rows_examined_per_scan": 100,
                }
            }
        }
    }
    result = parse_explain_json(json.dumps(explain_json))
    assert "filesort" in result.rows[0].extra.lower()


def test_parse_explain_orderby_with_join():
    """Test EXPLAIN with ORDER BY and JOIN (nested in ordering_operation)."""
    explain_json = {
        "query_block": {
            "select_id": 1,
            "ordering_operation": {
                "using_filesort": True,
                "nested_loop": [
                    {"table": {"table_name": "orders", "access_type": "ALL",
                               "rows_examined_per_scan": 1000}},
                    {"table": {"table_name": "users", "access_type": "eq_ref",
                               "key": "PRIMARY", "rows_examined_per_scan": 1}},
                ]
            }
        }
    }
    result = parse_explain_json(json.dumps(explain_json))
    assert len(result.rows) == 2
    assert result.rows[0].table == "orders"
    assert result.rows[1].table == "users"
    assert result.is_full_scan is True


def test_parse_explain_malformed_json():
    """Test handling of malformed JSON."""
    result = parse_explain_json("not valid json")
    assert len(result.rows) == 0
    assert "无法解析" in result.problems[0]


def test_parse_explain_empty_string():
    """Test handling of empty string."""
    result = parse_explain_json("")
    assert len(result.rows) == 0


def test_run_explain_connection_error():
    """Test run_explain handles connection errors gracefully."""
    mock_conn = MagicMock()
    mock_conn.cursor.side_effect = Exception("Connection lost")
    result = run_explain(mock_conn, "SELECT 1")
    assert len(result.rows) == 0
    assert any("EXPLAIN" in p for p in result.problems)

