"""schema 读取测试。"""
from sql_coach.local.schema import Schema, TableSchema, SchemaProvider


class FakeConnector:
    def __init__(self, connected=True):
        self.connected = connected
        self.calls = []

    def is_connected(self):
        return self.connected

    def query(self, sql, params=None):
        self.calls.append(sql)
        if "information_schema.TABLES" in sql:
            return [("orders",), ("users",)]
        wanted = {str(p).lower() for p in (params or ())}
        if "information_schema.COLUMNS" in sql:
            rows = [("orders", "id", "bigint", "订单ID"),
                    ("orders", "status", "varchar", "状态"),
                    ("orders", "created_at", "datetime", ""),
                    ("users", "id", "bigint", ""),
                    ("users", "phone", "varchar", "手机号")]
        elif "information_schema.STATISTICS" in sql:
            rows = [("orders", "PRIMARY", 1, "id"),
                    ("orders", "idx_status", 1, "status"),
                    ("users", "PRIMARY", 1, "id")]
        else:
            rows = []
        return [r for r in rows if r[0].lower() in wanted]


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


def test_has_index_on_uses_leftmost_column_only():
    # 复合索引 (a, b)：单独用 b 无法走该索引
    s = Schema(tables={"t": TableSchema(name="t", indexes=[["a", "b"]])})
    assert s.has_index_on("t", "a")
    assert not s.has_index_on("t", "b")


def test_has_table_distinguishes_unknown_table():
    assert not Schema().has_table("orders")
    s = Schema(tables={"orders": TableSchema(name="orders")})
    assert s.has_table("orders")
    assert not s.has_table("users")


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


def test_provider_accumulates_across_different_tables():
    """复用 provider 时，第二次换表不能返回陈旧 schema。"""
    sp = SchemaProvider(FakeConnector())
    sp.load(["orders"])
    schema = sp.load(["users"])
    assert schema.has_table("orders")
    assert schema.has_table("users")


def test_provider_empty_tables_does_not_pollute_cache():
    """tables 为空时不得把空结果写进缓存。"""
    sp = SchemaProvider(FakeConnector())
    sp.load([])
    assert sp.load(["orders"]).has_table("orders")


def test_provider_swallows_query_error():
    class Boom(FakeConnector):
        def query(self, sql, params=()):
            raise RuntimeError("db down")
    sp = SchemaProvider(Boom())
    assert sp.load(["orders"]) == Schema()


def test_columns_query_orders_by_ordinal_position():
    """列序必须按表定义顺序（ORDINAL_POSITION），否则 SELECT * 展开后列序会乱。"""
    fake = FakeConnector()
    SchemaProvider(fake).load(["orders"])
    cols_sql = [c for c in fake.calls if "information_schema.COLUMNS" in c]
    assert cols_sql, "应查询 information_schema.COLUMNS"
    assert "ORDINAL_POSITION" in cols_sql[0]


def test_table_schema_comments_defaults_empty():
    ts = TableSchema(name="orders")
    assert ts.comments == {}


def test_provider_reads_column_comments():
    sp = SchemaProvider(FakeConnector())
    schema = sp.load(["orders"])
    assert schema.tables["orders"].comments["status"] == "状态"
    assert schema.tables["orders"].comments["id"] == "订单ID"


def test_provider_skips_empty_column_comment():
    sp = SchemaProvider(FakeConnector())
    schema = sp.load(["orders"])
    # created_at 注释为空字符串，不应写入
    assert "created_at" not in schema.tables["orders"].comments


def test_columns_query_selects_column_comment():
    fake = FakeConnector()
    SchemaProvider(fake).load(["orders"])
    cols_sql = [c for c in fake.calls if "information_schema.COLUMNS" in c]
    assert cols_sql and "COLUMN_COMMENT" in cols_sql[0]


def test_provider_load_all_reads_every_table():
    sp = SchemaProvider(FakeConnector())
    schema = sp.load_all()
    assert schema.has_table("orders")
    assert schema.has_table("users")
    assert schema.column_type("users", "phone") == "varchar"


def test_provider_load_all_without_connector_returns_empty():
    assert SchemaProvider(None).load_all() == Schema()


def test_provider_load_all_disconnected_returns_empty():
    assert SchemaProvider(FakeConnector(connected=False)).load_all() == Schema()


def test_provider_load_all_limits_tables():
    fake = FakeConnector()
    SchemaProvider(fake).load_all(max_tables=50)
    tables_sql = [c for c in fake.calls if "information_schema.TABLES" in c]
    assert tables_sql, "应查询 information_schema.TABLES"
    assert "LIMIT 50" in tables_sql[0]


def test_provider_load_all_caches_and_accumulates():
    fake = FakeConnector()
    sp = SchemaProvider(fake)
    sp.load_all()
    n_struct = len([c for c in fake.calls if "information_schema.COLUMNS" in c])
    schema = sp.load_all()
    n_struct2 = len([c for c in fake.calls if "information_schema.COLUMNS" in c])
    assert n_struct2 == n_struct  # 第二次不再重复读表结构
    assert schema.has_table("orders") and schema.has_table("users")


def test_provider_load_all_merges_with_previous_load():
    fake = FakeConnector()
    sp = SchemaProvider(fake)
    sp.load(["orders"])
    schema = sp.load_all()
    assert schema.has_table("orders")
    assert schema.tables["orders"].comments["status"] == "状态"
    assert schema.has_table("users")


def test_provider_load_all_swallows_query_error():
    class Boom(FakeConnector):
        def query(self, sql, params=None):
            raise RuntimeError("db down")
    sp = SchemaProvider(Boom())
    assert sp.load_all() == Schema()
