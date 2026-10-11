"""本地优化引擎测试。"""
from sql_coach.models import SQLInfo
from sql_coach.local.schema import Schema, TableSchema
from sql_coach.local.engine import LocalOptimizer
from sql_coach.local.rules.base import Rule
from sql_coach.local.rules.select_star import SelectStarRule


def make_info(sql, tables=(), columns=(), where=()):
    return SQLInfo(raw_sql=sql, sql_type="SELECT", tables=list(tables),
                   columns=list(columns), where_conditions=list(where),
                   join_tables=[], order_by=[])


def test_optimizer_aggregates_problems_and_ddls():
    info = make_info("SELECT * FROM orders WHERE status='pending'",
                     tables=["orders"], columns=["*"], where=["status='pending'"])
    result = LocalOptimizer().optimize(info, Schema())
    descs = [p.description for p in result.problems]
    assert any("SELECT *" in d for d in descs)
    assert any("status" in d for d in descs)
    assert result.index_ddls == ["CREATE INDEX idx_orders_status ON orders(status);"]
    assert "本地规则引擎" in result.explanation


def test_optimizer_rewrites_select_star_with_schema():
    schema = Schema(tables={"orders": TableSchema(
        name="orders", columns={"id": "bigint", "status": "varchar"})})
    info = make_info("SELECT * FROM orders WHERE status='x'",
                     tables=["orders"], columns=["*"], where=["status='x'"])
    result = LocalOptimizer().optimize(info, schema)
    assert result.optimized_sql == "SELECT id, status FROM orders WHERE status='x'"


def test_optimizer_isolates_rule_exception():
    class Boom(Rule):
        name = "boom"

        def check(self, ctx):
            raise RuntimeError("boom")

    info = make_info("SELECT * FROM orders", tables=["orders"], columns=["*"])
    result = LocalOptimizer(rules=[Boom(), SelectStarRule()]).optimize(info, Schema())
    assert any("SELECT *" in p.description for p in result.problems)


def test_optimizer_no_hit_keeps_original_sql():
    info = make_info("SELECT id FROM orders WHERE id=1",
                     tables=["orders"], columns=["id"], where=["id=1"])
    result = LocalOptimizer(rules=[SelectStarRule()]).optimize(info, Schema())
    assert result.optimized_sql == "SELECT id FROM orders WHERE id=1"
    assert result.problems == []
