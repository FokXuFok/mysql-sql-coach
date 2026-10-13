"""SQLBuilder 测试：NLQuery → SQL，含 sqlparse 语法校验。"""
import pytest
import sqlparse

from sql_coach.local.schema import Schema, TableSchema
from sql_coach.models import NLEntity, NLQuery
from sql_coach.nl.parser import NLParser
from sql_coach.nl_to_sql.builder import SQLBuilder
from sql_coach.nl_to_sql.mapper import EntityMapper
from sql_coach.nl_to_sql import templates


def make_schema() -> Schema:
    """构造含 customers / orders / users 三张表的测试 schema。"""
    return Schema(tables={
        "customers": TableSchema(name="customers", columns={
            "id": "bigint", "customer_name": "varchar", "city": "varchar",
            "amount": "decimal", "created_at": "datetime"}),
        "orders": TableSchema(name="orders", columns={
            "id": "bigint", "customer_id": "bigint", "status": "varchar",
            "amount": "decimal", "created_at": "datetime"}),
        "users": TableSchema(name="users", columns={
            "id": "bigint", "name": "varchar", "city": "varchar", "age": "int",
            "email": "varchar", "status": "varchar", "created_at": "datetime"}),
    })


@pytest.fixture(scope="module")
def builder() -> SQLBuilder:
    return SQLBuilder()


@pytest.fixture(scope="module")
def parser() -> NLParser:
    return NLParser(make_schema())


def _query(**kwargs) -> NLQuery:
    """构造 NLQuery，未提供的字段用空默认值补齐。"""
    base = dict(intent="select", tables=[], columns=[], conditions=[],
                aggregates=[], order_by=[], group_by=[], limit=None, raw_text="")
    base.update(kwargs)
    return NLQuery(**base)


def _assert_parses(sql: str) -> None:
    """生成的 SQL 必须能被 sqlparse 解析。"""
    parsed = sqlparse.parse(sql)
    assert parsed, f"sqlparse 无法解析: {sql}"


# --------------------------------------------------------------------- 文档示例

def test_example_top_customers_by_sales(builder, parser):
    """示例 1：查询销售额最高的10个客户（按客户分组，而非按金额分组）。"""
    q = parser.parse("查询销售额最高的10个客户")
    sql = builder.build(q)
    assert sql == ("SELECT customer_name, SUM(amount) FROM customers "
                   "GROUP BY customer_name ORDER BY SUM(amount) DESC LIMIT 10;")
    _assert_parses(sql)


def test_example_pending_orders(builder, parser):
    """示例 2：查找status为pending的订单（status 只作条件，不进 SELECT）。"""
    q = parser.parse("查找status为pending的订单")
    sql = builder.build(q)
    assert sql == "SELECT * FROM orders WHERE status = 'pending';"
    _assert_parses(sql)


def test_example_users_per_city(builder, parser):
    """示例 3：统计每个城市的用户数量。"""
    q = parser.parse("统计每个城市的用户数量")
    sql = builder.build(q)
    assert sql == "SELECT city, COUNT(*) FROM users GROUP BY city;"
    _assert_parses(sql)


def test_example_recent_orders(builder, parser):
    """示例 4：查询最近10条订单。"""
    q = parser.parse("查询最近10条订单")
    sql = builder.build(q)
    assert sql == "SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;"
    _assert_parses(sql)


@pytest.mark.parametrize("text,expected_sql", [
    ("查询销售额最高的10个客户",
     "SELECT customer_name, SUM(amount) FROM customers "
     "GROUP BY customer_name ORDER BY SUM(amount) DESC LIMIT 10;"),
    ("查找status为pending的订单",
     "SELECT * FROM orders WHERE status = 'pending';"),
    ("统计每个城市的用户数量",
     "SELECT city, COUNT(*) FROM users GROUP BY city;"),
    ("查询最近10条订单",
     "SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;"),
])
def test_end_to_end_examples(builder, parser, text, expected_sql):
    """4 条示例输入经 NLParser.parse + SQLBuilder.build 后逐字符等于预期 SQL。"""
    sql = builder.build(parser.parse(text))
    assert sql == expected_sql
    _assert_parses(sql)


# --------------------------------------------------------------------- 单元用例

def test_select_defaults_to_all_columns(builder):
    sql = builder.build(_query(tables=["orders"]))
    assert sql == "SELECT * FROM orders;"
    _assert_parses(sql)


def test_select_with_columns_where_order_limit(builder):
    sql = builder.build(_query(
        tables=["orders"], columns=["id", "status"],
        conditions=[NLEntity("condition", "status为paid", "status = 'paid'")],
        order_by=[NLEntity("order", "最近", "created_at DESC")],
        limit=5))
    assert sql == ("SELECT id, status FROM orders WHERE status = 'paid' "
                   "ORDER BY created_at DESC LIMIT 5;")
    _assert_parses(sql)


def test_select_unknown_table_when_no_table(builder):
    sql = builder.build(_query())
    assert sql == f"SELECT * FROM {templates.UNKNOWN_TABLE};"
    _assert_parses(sql)


def test_count_intent(builder):
    sql = builder.build(_query(
        intent="count", tables=["orders"],
        conditions=[NLEntity("condition", "status为paid", "status = 'paid'")]))
    assert sql == "SELECT COUNT(*) AS cnt FROM orders WHERE status = 'paid';"
    _assert_parses(sql)


def test_count_unknown_table(builder):
    sql = builder.build(_query(intent="count"))
    assert sql == f"SELECT COUNT(*) AS cnt FROM {templates.UNKNOWN_TABLE};"
    _assert_parses(sql)


def test_aggregate_uses_group_by_when_provided(builder):
    sql = builder.build(_query(
        intent="aggregate", tables=["users"], columns=["city"],
        group_by=["city"],
        aggregates=[NLEntity("aggregate", "数量", "COUNT(*)")]))
    assert sql == "SELECT city, COUNT(*) FROM users GROUP BY city;"
    _assert_parses(sql)


def test_aggregate_without_plain_columns_has_no_group_by(builder):
    sql = builder.build(_query(
        intent="aggregate", tables=["orders"],
        aggregates=[NLEntity("aggregate", "销售额", "SUM(amount)")]))
    assert sql == "SELECT SUM(amount) FROM orders;"
    _assert_parses(sql)


def test_aggregate_multiple_conditions(builder):
    sql = builder.build(_query(
        intent="aggregate", tables=["orders"], columns=["status"],
        conditions=[
            NLEntity("condition", "status为paid", "status = 'paid'"),
            NLEntity("condition", "金额大于100", "amount > 100"),
        ],
        aggregates=[NLEntity("aggregate", "总计", "SUM(amount)")]))
    assert sql == ("SELECT status, SUM(amount) FROM orders "
                   "WHERE status = 'paid' AND amount > 100 GROUP BY status;")
    _assert_parses(sql)


def test_multiple_order_by(builder):
    sql = builder.build(_query(
        tables=["orders"],
        order_by=[NLEntity("order", "a", "created_at DESC"),
                  NLEntity("order", "b", "id ASC")]))
    assert sql == "SELECT * FROM orders ORDER BY created_at DESC, id ASC;"
    _assert_parses(sql)


# --------------------------------------------------------------------- 转义（防注入）

def test_condition_escapes_single_quote(builder):
    """条件里的字符串值必须转义单引号，避免注入/语法错误。"""
    sql = builder.build(_query(
        tables=["orders"],
        conditions=[NLEntity("condition", "name为O'Brien", "name = 'O'Brien'")]))
    assert sql == "SELECT * FROM orders WHERE name = 'O''Brien';"
    _assert_parses(sql)


def test_condition_escapes_multiple_quotes(builder):
    sql = builder.build(_query(
        tables=["orders"],
        conditions=[NLEntity("condition", "x", "name = 'a'b'c'")]))
    assert sql == "SELECT * FROM orders WHERE name = 'a''b''c';"
    _assert_parses(sql)


def test_condition_without_literal_unchanged(builder):
    sql = builder.build(_query(
        tables=["orders"],
        conditions=[NLEntity("condition", "age>18", "age > 18")]))
    assert sql == "SELECT * FROM orders WHERE age > 18;"


def test_mapper_escape_string():
    assert EntityMapper.escape_string("O'Brien") == "O''Brien"
    assert EntityMapper.escape_string("plain") == "plain"
    assert EntityMapper.escape_string("") == ""


def test_mapper_escape_literal_no_quotes():
    m = EntityMapper()
    assert m.escape_literal("age > 18") == "age > 18"
    assert m.escape_literal("status = 'pending'") == "status = 'pending'"


def test_mapper_strips_whitespace():
    m = EntityMapper()
    e = NLEntity("condition", "x", "  status = 'a'  ")
    assert m.condition(e) == "status = 'a'"
    assert m.aggregate(NLEntity("aggregate", "x", " SUM(amount) ")) == "SUM(amount)"
    assert m.order(NLEntity("order", "x", " id DESC ")) == "id DESC"


# --------------------------------------------------------------------- 模板

def test_templates_render_fills_missing_with_empty():
    assert templates.render("{a}{b}", a="x") == "x"
    assert templates.render("{a}{b}", a="x", b="y") == "xy"


@pytest.mark.parametrize("text", [
    "查询销售额最高的10个客户",
    "查找status为pending的订单",
    "统计每个城市的用户数量",
    "查询最近10条订单",
    "有多少条status为paid的订单",
])
def test_all_examples_parse_with_sqlparse(builder, parser, text):
    sql = builder.build(parser.parse(text))
    assert sql.endswith(";")
    _assert_parses(sql)


# --------------------------------------------------------- 语义缺陷修复回归

def test_example_total_amount_per_city(builder, parser):
    """Critical 1：'查询每个城市的订单总额' 必须含 SUM(amount)。"""
    sql = builder.build(parser.parse("查询每个城市的订单总额"))
    assert "SUM(amount)" in sql
    _assert_parses(sql)


def test_example_average_age(builder, parser):
    """Important 2：'查询用户的平均年龄' 必须含 AVG(age) 且不含 AVG(*)。"""
    sql = builder.build(parser.parse("查询用户的平均年龄"))
    assert "AVG(age)" in sql
    assert "AVG(*)" not in sql
    assert "GROUP BY age" not in sql
    _assert_parses(sql)


def test_empty_schema_never_emits_star_aggregate(builder):
    """Important 2：空 schema 下宁可退化为 SELECT *，也不生成 SUM(*)。"""
    sql = builder.build(NLParser(Schema()).parse("查询销售额最高的10个客户"))
    assert "SUM(*)" not in sql
    assert "AVG(*)" not in sql
    assert "MAX(*)" not in sql
    assert "MIN(*)" not in sql
    _assert_parses(sql)


def test_example_recent_users_order_by_time(builder, parser):
    """Important 3：'查询最近10个用户的名称' 按 created_at 排序。"""
    sql = builder.build(parser.parse("查询最近10个用户的名称"))
    assert "ORDER BY created_at DESC" in sql
    _assert_parses(sql)


def test_example_quoted_literal_escaped(builder, parser):
    """Important 5：带引号字面量正确转义。"""
    sql = builder.build(parser.parse("查找name为'O'Brien'的用户"))
    assert sql == "SELECT * FROM users WHERE name = 'O''Brien';"
    _assert_parses(sql)


def test_example_wan_unit_in_where(builder, parser):
    """Important 4：WHERE 里的值应为 10000。"""
    sql = builder.build(parser.parse("查询销售额超过1万的客户"))
    assert "10000" in sql
    _assert_parses(sql)
