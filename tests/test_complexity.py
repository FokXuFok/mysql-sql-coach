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


def test_multi_column_group_by_adds_score():
    single = make_info("SELECT a, b FROM t WHERE x=1 GROUP BY a",
                       tables=["t"], columns=["a", "b"], where=["x=1"])
    multi = make_info("SELECT a, b FROM t WHERE x=1 GROUP BY a, b",
                      tables=["t"], columns=["a", "b"], where=["x=1"])
    c1 = ComplexityScorer().score(single)
    c2 = ComplexityScorer().score(multi)
    assert "多列分组" not in c1.reasons
    assert "多列分组" in c2.reasons
    assert c2.score == c1.score + 1


def test_nested_function_expression_detected():
    info = make_info("SELECT UPPER(SUBSTR(name, 1, 3)) FROM t",
                     tables=["t"], columns=["name"], where=["x=1"])
    c = ComplexityScorer().score(info)
    assert "嵌套函数表达式" in c.reasons


def test_window_function_not_treated_as_nested_function():
    info = make_info("SELECT ROW_NUMBER() OVER (ORDER BY id) FROM t",
                     tables=["t"], columns=["id"], where=["x=1"])
    c = ComplexityScorer().score(info)
    assert "嵌套函数表达式" not in c.reasons


def test_nested_function_without_space_detected():
    """M3: 无空格的嵌套函数 UPPER(SUBSTR(...)) 仍应命中。"""
    info = make_info("SELECT UPPER(SUBSTR(x,1,2)) FROM t",
                     tables=["t"], columns=["x"], where=["y=1"])
    c = ComplexityScorer().score(info)
    assert "嵌套函数表达式" in c.reasons


def test_in_subquery_not_treated_as_nested_function():
    """M3: IN(SELECT COUNT(...)) 的外层是关键字 IN，不应命中。"""
    info = make_info("SELECT * FROM t WHERE id IN(SELECT COUNT(*) FROM o)",
                     tables=["t"], columns=["*"], where=["id IN(SELECT COUNT(*) FROM o)"])
    c = ComplexityScorer().score(info)
    assert "嵌套函数表达式" not in c.reasons


def test_exists_subquery_not_treated_as_nested_function():
    """M3: EXISTS(SELECT MAX(...)) 的外层是关键字 EXISTS，不应命中。"""
    info = make_info("SELECT * FROM t WHERE EXISTS(SELECT MAX(x) FROM o)",
                     tables=["t"], columns=["*"], where=["EXISTS(SELECT MAX(x) FROM o)"])
    c = ComplexityScorer().score(info)
    assert "嵌套函数表达式" not in c.reasons


def test_group_by_function_with_commas_not_multi_column():
    """M2: GROUP BY IF(a,b,c) 括号内逗号不算多列分组。"""
    info = make_info("SELECT IF(a, b, c) FROM t WHERE x=1 GROUP BY IF(a, b, c)",
                     tables=["t"], columns=["a", "b", "c"], where=["x=1"])
    c = ComplexityScorer().score(info)
    assert "多列分组" not in c.reasons


def test_group_by_multiple_columns_still_multi_column():
    """M2: GROUP BY a, b 仍算多列分组。"""
    info = make_info("SELECT a, b FROM t WHERE x=1 GROUP BY a, b",
                     tables=["t"], columns=["a", "b"], where=["x=1"])
    c = ComplexityScorer().score(info)
    assert "多列分组" in c.reasons


def test_correlated_subquery_not_specially_penalized():
    info = make_info(
        "SELECT u.id FROM users u WHERE (SELECT COUNT(*) FROM orders o "
        "WHERE o.user_id=u.id) > 3",
        tables=["users", "orders"],
        where=["(SELECT COUNT(*) FROM orders o WHERE o.user_id=u.id) > 3"])
    c = ComplexityScorer().score(info)
    # 2 表(+2) + 1 个子查询(+3) + 聚合函数 COUNT(+2) = 7，无"相关子查询"专项加分
    assert c.score == 7
    assert all("相关子查询" not in r for r in c.reasons)
