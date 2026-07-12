# tests/test_db_connector.py
import time
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