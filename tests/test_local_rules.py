"""本地规则测试。"""
from sql_coach.models import SQLInfo
from sql_coach.local.schema import Schema, TableSchema
from sql_coach.local.rules.base import Rule, RuleContext


def make_info(sql, sql_type="SELECT", tables=(), columns=(), where=(), order_by=()):
    return SQLInfo(raw_sql=sql, sql_type=sql_type, tables=list(tables),
                   columns=list(columns), where_conditions=list(where),
                   join_tables=[], order_by=list(order_by))


def test_rule_base_defaults_are_noop():
    class Noop(Rule):
        name = "noop"
    ctx = RuleContext(sql_info=make_info("SELECT 1"), schema=Schema())
    assert Noop().check(ctx) == []
    assert Noop().rewrite(ctx) is None
    assert Noop().ddls(ctx) == []


from sql_coach.local.rules.missing_index import MissingIndexRule
from sql_coach.local.rules.leading_wildcard import LeadingWildcardRule
from sql_coach.local.rules.implicit_cast import ImplicitCastRule
from sql_coach.local.rules.no_limit import NoLimitRule
from sql_coach.local.rules.deep_pagination import DeepPaginationRule
from sql_coach.local.rules.or_condition import OrConditionRule
from sql_coach.local.rules.subquery_to_join import SubqueryToJoinRule


def _ctx(sql, tables=(), columns=(), where=(), order_by=(), schema=None):
    return RuleContext(sql_info=make_info(sql, tables=tables, columns=columns,
                                          where=where, order_by=order_by),
                       schema=schema or Schema())


def test_missing_index_without_schema_flags_suspected():
    ctx = _ctx("SELECT * FROM orders WHERE status='pending'",
               tables=["orders"], where=["status='pending'"])
    problems = MissingIndexRule().check(ctx)
    assert len(problems) == 1
    assert "疑似" in problems[0].description
    assert MissingIndexRule().ddls(ctx) == ["CREATE INDEX idx_orders_status ON orders(status);"]


def test_missing_index_with_schema_skips_existing_index():
    schema = Schema(tables={"orders": TableSchema(name="orders", indexes=[["status"]])})
    ctx = _ctx("SELECT * FROM orders WHERE status='pending'",
               tables=["orders"], where=["status='pending'"], schema=schema)
    assert MissingIndexRule().check(ctx) == []
    assert MissingIndexRule().ddls(ctx) == []


def test_leading_wildcard():
    ctx = _ctx("SELECT id FROM users WHERE name LIKE '%abc'", tables=["users"], columns=["id"])
    assert len(LeadingWildcardRule().check(ctx)) == 1
    ctx_ok = _ctx("SELECT id FROM users WHERE name LIKE 'abc%'", tables=["users"], columns=["id"])
    assert LeadingWildcardRule().check(ctx_ok) == []


def test_implicit_cast_only_when_schema_known():
    schema = Schema(tables={"users": TableSchema(name="users", columns={"phone": "varchar"})})
    ctx = _ctx("SELECT * FROM users WHERE phone=13800000000",
               tables=["users"], where=["phone=13800000000"], schema=schema)
    assert len(ImplicitCastRule().check(ctx)) == 1
    # 无 schema 时不误报
    ctx2 = _ctx("SELECT * FROM users WHERE phone=13800000000",
                tables=["users"], where=["phone=13800000000"])
    assert ImplicitCastRule().check(ctx2) == []


def test_no_limit_requires_no_where():
    ctx = _ctx("SELECT * FROM orders", tables=["orders"], columns=["*"])
    assert len(NoLimitRule().check(ctx)) == 1
    ctx_ok = _ctx("SELECT * FROM orders WHERE status='x'", tables=["orders"],
                  columns=["*"], where=["status='x'"])
    assert NoLimitRule().check(ctx_ok) == []


def test_deep_pagination_threshold():
    ctx = _ctx("SELECT * FROM orders LIMIT 100000, 20", tables=["orders"], columns=["*"])
    assert len(DeepPaginationRule().check(ctx)) == 1
    ctx_ok = _ctx("SELECT * FROM orders LIMIT 10, 20", tables=["orders"], columns=["*"])
    assert DeepPaginationRule().check(ctx_ok) == []


def test_or_condition():
    ctx = _ctx("SELECT * FROM orders WHERE a=1 OR b=2", tables=["orders"],
               columns=["*"], where=["a=1", "b=2"])
    assert len(OrConditionRule().check(ctx)) == 1


def test_subquery_to_join():
    ctx = _ctx("SELECT * FROM users WHERE id IN (SELECT user_id FROM orders)",
               tables=["users"], columns=["*"])
    assert len(SubqueryToJoinRule().check(ctx)) == 1
