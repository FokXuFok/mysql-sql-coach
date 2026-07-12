# tests/test_db_connector.py
from unittest.mock import MagicMock, patch

import pytest

from sql_coach.db.connector import DBConnector
from sql_coach.models import DBConfig


@pytest.fixture
def db_config():
    return DBConfig(host="localhost", port=3306, user="root",
                    password="test", database="test")


def test_db_connector_init(db_config):
    conn = DBConnector(db_config)
    assert conn.config == db_config
    assert conn._conn is None


def test_db_connector_connect_failure(db_config):
    """Test that connect returns False on connection error."""
    conn = DBConnector(db_config)
    with patch("sql_coach.db.connector.pymysql.connect",
               side_effect=Exception("Connection refused")):
        result = conn.connect()
    assert result is False
    assert conn._conn is None


def test_db_connector_connect_success(db_config):
    """Test successful connection."""
    conn = DBConnector(db_config)
    mock_conn = MagicMock()
    with patch("sql_coach.db.connector.pymysql.connect", return_value=mock_conn):
        result = conn.connect()
    assert result is True
    assert conn._conn is mock_conn


def test_db_connector_close(db_config):
    conn = DBConnector(db_config)
    mock_conn = MagicMock()
    conn._conn = mock_conn
    conn.close()
    assert mock_conn.close.called
    assert conn._conn is None


def test_db_connector_benchmark(db_config):
    """Test benchmark executes SQL multiple times."""
    conn = DBConnector(db_config)
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    conn._conn = mock_conn

    elapsed = conn.benchmark("SELECT 1", runs=3)
    assert isinstance(elapsed, float)
    assert elapsed >= 0
    assert mock_cursor.execute.call_count == 3


def test_db_connector_execute(db_config):
    """Test DDL execution."""
    conn = DBConnector(db_config)
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    conn._conn = mock_conn

    conn.execute("CREATE INDEX idx_test ON t(col)")
    mock_cursor.execute.assert_called_with("CREATE INDEX idx_test ON t(col)")
    assert mock_conn.commit.called


def test_db_connector_is_connected_when_not_connected(db_config):
    """Test is_connected returns False when no connection."""
    conn = DBConnector(db_config)
    assert conn.is_connected() is False


def test_db_connector_is_connected_when_connected(db_config):
    """Test is_connected returns True when connected."""
    conn = DBConnector(db_config)
    mock_conn = MagicMock()
    mock_conn.open = True
    conn._conn = mock_conn
    assert conn.is_connected() is True


def test_db_connector_explain_not_connected(db_config):
    """Test explain returns error result when not connected."""
    conn = DBConnector(db_config)
    result = conn.explain("SELECT * FROM t")
    assert result.rows == []
    assert result.is_full_scan is False
    assert "数据库未连接" in result.problems[0]


def test_db_connector_explain_delegates_to_run_explain(db_config):
    """Test explain delegates to run_explain when connected."""
    from sql_coach.models import ExplainResult
    conn = DBConnector(db_config)
    mock_conn = MagicMock()
    mock_conn.open = True
    conn._conn = mock_conn

    expected_result = ExplainResult(
        rows=[], is_full_scan=False, missing_indexes=[], problems=[]
    )
    with patch("sql_coach.db.connector._run_explain", return_value=expected_result):
        result = conn.explain("SELECT * FROM t")

    assert result is expected_result


def test_db_connector_benchmark_not_connected(db_config):
    """Test benchmark returns 0.0 when not connected."""
    conn = DBConnector(db_config)
    elapsed = conn.benchmark("SELECT 1", runs=3)
    assert elapsed == 0.0


def test_db_connector_execute_not_connected_raises(db_config):
    """Test execute raises RuntimeError when not connected."""
    conn = DBConnector(db_config)
    with pytest.raises(RuntimeError):
        conn.execute("CREATE INDEX idx ON t(c)")


from sql_coach.db.mock import MockConnector


def test_mock_connector_always_connected():
    conn = MockConnector()
    assert conn.is_connected() is True


def test_mock_connector_explain_returns_empty():
    conn = MockConnector()
    result = conn.explain("SELECT * FROM t")
    assert result.rows == []
    assert result.is_full_scan is False


def test_mock_connector_benchmark_returns_zero():
    conn = MockConnector()
    elapsed = conn.benchmark("SELECT 1")
    assert elapsed == 0.0


def test_mock_connector_close_no_error():
    conn = MockConnector()
    conn.close()  # should not raise


def test_mock_connector_execute_no_error():
    conn = MockConnector()
    conn.execute("CREATE INDEX idx ON t(c)")  # should not raise