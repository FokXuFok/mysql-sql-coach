"""复杂度评分器测试。"""
from sql_coach.models import SQLInfo
from sql_coach.local.complexity import ComplexityScorer


def make_info(sql, sql_type="SELECT", tables=(), columns=(), where=(), order_by=()):
    return SQLInfo(raw_sql=sql, sql_type=sql_type, tables=list(tables),
                   columns=list(columns), where_conditions=list(where),
                   join_tables=[], order_by=list(order_by))


def test_simple_single_table():
    info = make_info("SELECT * FROM orders WHERE status='pending'",
                     tables=["orders"], columns=["*"], where=["status='pending'"])
    c = ComplexityScorer().score(info)
    assert c.level == "simple"
    assert c.score <= 3


def test_medium_two_tables_group_by():
    info = make_info(
        "SELECT u.city, COUNT(*) FROM users u JOIN orders o ON u.id=o.user_id GROUP BY u.city",
        tables=["users", "orders"], where=["u.id=o.user_id"])
    c = ComplexityScorer().score(info)
    assert c.level == "medium"


def test_complex_window_three_tables():
    info = make_info(
        "SELECT ROW_NUMBER() OVER (ORDER BY a.id) FROM a JOIN b ON a.id=b.id JOIN c ON b.id=c.id",
        tables=["a", "b", "c"], where=["a.id=b.id", "b.id=c.id"])
    c = ComplexityScorer().score(info)
    assert c.level == "complex"
    assert any("窗口" in r for r in c.reasons)


def test_threshold_override():
    # 单表(0) + 聚合/分组(2) = 2；带 WHERE 所以不叠加"无 WHERE"惩罚
    info = make_info("SELECT a, COUNT(*) FROM t WHERE x=1 GROUP BY a",
                     tables=["t"], columns=["a"], where=["x=1"])
    assert ComplexityScorer(threshold=1).score(info).level == "complex"
    assert ComplexityScorer(threshold=8).score(info).level == "simple"


def test_reasons_recorded():
    info = make_info("SELECT * FROM a JOIN b ON a.id=b.id", tables=["a", "b"])
    c = ComplexityScorer().score(info)
    assert any("2 张表" in r for r in c.reasons)
