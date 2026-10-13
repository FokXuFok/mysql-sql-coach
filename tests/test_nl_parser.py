"""NLParser 端到端解析测试：自然语言 → NLQuery。"""
import pytest

from sql_coach.local.schema import Schema, TableSchema
from sql_coach.nl.parser import NLParser


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
def parser() -> NLParser:
    return NLParser(make_schema())


@pytest.mark.parametrize("text,intent,tables,limit", [
    ("查询销售额最高的10个客户", "aggregate", ["customers"], 10),
    ("查找status为pending的订单", "select", ["orders"], None),
    ("统计每个城市的用户数量", "aggregate", ["users"], None),
    ("查询最近10条订单", "select", ["orders"], 10),
    ("有多少条status为paid的订单", "count", ["orders"], None),
])
def test_parse_intent_tables_limit(parser, text, intent, tables, limit):
    result = parser.parse(text)
    assert result.intent == intent
    assert result.tables == tables
    assert result.limit == limit


def test_parse_aggregate_sum_amount_and_order_desc(parser):
    result = parser.parse("查询销售额最高的10个客户")
    assert any(a.mapped == "SUM(amount)" for a in result.aggregates)
    assert any("DESC" in o.mapped for o in result.order_by)


def test_parse_aggregate_excludes_target_and_adds_representative(parser):
    """例 1：SUM 的目标列 amount 不应作为查询列，补入代表列 customer_name。"""
    result = parser.parse("查询销售额最高的10个客户")
    assert result.columns == ["customer_name"]
    assert [a.mapped for a in result.aggregates] == ["SUM(amount)"]


def test_parse_condition_column_not_selected(parser):
    """例 2：WHERE 条件里的 status 只作条件，不作为查询列。"""
    result = parser.parse("查找status为pending的订单")
    assert result.columns == []
    assert [c.mapped for c in result.conditions] == ["status = 'pending'"]


def test_parse_group_by_city(parser):
    result = parser.parse("统计每个城市的用户数量")
    assert "city" in result.group_by


def test_parse_order_by_created_at_desc(parser):
    result = parser.parse("查询最近10条订单")
    assert any(o.mapped == "created_at DESC" for o in result.order_by)


def test_parse_equality_condition(parser):
    result = parser.parse("查找status为pending的订单")
    assert [c.mapped for c in result.conditions] == ["status = 'pending'"]


def test_parse_keeps_raw_text(parser):
    result = parser.parse("查询最近10条订单")
    assert result.raw_text == "查询最近10条订单"


def test_parse_empty_schema_does_not_crash():
    result = NLParser(Schema()).parse("查询10条订单")
    assert result.limit == 10
    assert result.tables == []
