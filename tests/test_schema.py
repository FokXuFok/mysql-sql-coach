"""schema 读取测试。"""
from sql_coach.local.schema import Schema, TableSchema, SchemaProvider


class FakeConnector:
    def __init__(self, connected=True):
        self.connected = connected
        self.calls = []

    def is_connected(self):
        return self.connected

    def query(self, sql, params=()):
        self.calls.append(sql)
        if "information_schema.COLUMNS" in sql:
            return [("orders", "id", "bigint"),
                    ("orders", "status", "varchar"),
                    ("orders", "created_at", "datetime")]
        if "information_schema.STATISTICS" in sql:
            return [("orders", "PRIMARY", 1, "id"),
                    ("orders", "idx_status", 1, "status")]
        return []


def test_empty_schema_is_falsy():
    assert not Schema()


def test_has_index_on_and_column_type():
    s = Schema(tables={"orders": TableSchema(
        name="orders",
        columns={"status": "varchar"},
        indexes=[["status"], ["id"]])})
    assert s.has_index_on("orders", "status")
    assert not s.has_index_on("orders", "missing")
    assert s.column_type("orders", "status") == "varchar"
    assert s.column_type("orders", "nope") is None


def test_provider_without_connector_returns_empty():
    sp = SchemaProvider(None)
    assert sp.load(["orders"]) == Schema()


def test_provider_reads_information_schema():
    sp = SchemaProvider(FakeConnector())
    schema = sp.load(["orders"])
    assert schema.has_index_on("orders", "status")
    assert schema.column_type("orders", "status") == "varchar"


def test_provider_caches_after_first_load():
    fake = FakeConnector()
    sp = SchemaProvider(fake)
    sp.load(["orders"])
    n = len(fake.calls)
    sp.load(["orders"])
    assert len(fake.calls) == n  # 第二次不再查库


def test_provider_swallows_query_error():
    class Boom(FakeConnector):
        def query(self, sql, params=()):
            raise RuntimeError("db down")
    sp = SchemaProvider(Boom())
    assert sp.load(["orders"]) == Schema()
