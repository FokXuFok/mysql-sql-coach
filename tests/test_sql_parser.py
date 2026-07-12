# tests/test_sql_parser.py
from sql_coach.engine.sql_parser import parse, SQLInfo


def test_parse_simple_select():
    info = parse("SELECT * FROM orders")
    assert info.sql_type == "SELECT"
    assert "orders" in info.tables
    assert "*" in info.columns


def test_parse_select_with_where():
    info = parse("SELECT id, name FROM users WHERE id = 1")
    assert info.sql_type == "SELECT"
    assert "users" in info.tables
    assert "id" in info.columns
    assert any("id" in c for c in info.where_conditions)


def test_parse_select_with_join():
    info = parse(
        "SELECT o.id, u.name FROM orders o "
        "JOIN users u ON o.user_id = u.id"
    )
    assert "orders" in info.tables
    assert "users" in info.tables or "users" in info.join_tables


def test_parse_select_with_order_by():
    info = parse("SELECT * FROM orders ORDER BY created_at DESC")
    assert len(info.order_by) > 0


def test_parse_update():
    info = parse("UPDATE orders SET status = 1 WHERE id = 1")
    assert info.sql_type == "UPDATE"
    assert "orders" in info.tables


def test_parse_delete():
    info = parse("DELETE FROM orders WHERE id = 1")
    assert info.sql_type == "DELETE"
    assert "orders" in info.tables


def test_parse_invalid_sql():
    info = parse("not a sql")
    assert info.raw_sql == "not a sql"
    assert info.sql_type == "UNKNOWN"


def test_parse_complex_query():
    sql = """
    SELECT o.id, o.amount, u.name
    FROM orders o
    JOIN users u ON o.user_id = u.id
    WHERE o.status = 'pending' AND u.city = '北京'
    ORDER BY o.created_at DESC
    """
    info = parse(sql)
    assert info.sql_type == "SELECT"
    assert len(info.tables) >= 1
    assert len(info.columns) >= 2
