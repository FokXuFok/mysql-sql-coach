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
