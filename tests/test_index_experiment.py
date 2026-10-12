# tests/test_index_experiment.py
"""索引实测模式单元测试。"""
from sql_coach.index_experiment import (
    parse_create_index,
    build_drop_index,
    measure_index_impact,
)
from sql_coach.models import IndexImpact


class FakeConnector:
    """测试用最小连接器替身，记录执行过的语句。"""

    def __init__(self, connected=True, existing_indexes=None,
                 fail_on=None, benchmark_times=None, query_raises=False):
        self.connected = connected
        self.existing_indexes = set(existing_indexes or [])
        self.fail_on = fail_on
        self.benchmark_times = list(benchmark_times) if benchmark_times else [0.2, 0.05]
        self.query_raises = query_raises
        self.executed = []
        self.benchmark_calls = 0

    def is_connected(self):
        return self.connected

    def query(self, sql, params=None):
        if self.query_raises:
            raise RuntimeError("query boom")
        if params:
            _, index_name = params
            if index_name in self.existing_indexes:
                return [(1,)]
        return []

    def execute(self, sql):
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("execute boom")
        self.executed.append(sql)

    def benchmark(self, sql, runs=3):
        i = self.benchmark_calls
        self.benchmark_calls += 1
        if self.benchmark_times:
            return self.benchmark_times[min(i, len(self.benchmark_times) - 1)]
        return 0.0


# ---- parse_create_index ----

def test_parse_create_index_basic():
    assert parse_create_index("CREATE INDEX idx_x ON tbl(col);") == ("idx_x", "tbl")


def test_parse_create_index_backticks():
    assert parse_create_index("CREATE INDEX `idx_x` ON `tbl`(`col`);") == ("idx_x", "tbl")


def test_parse_create_index_if_not_exists():
    assert parse_create_index("CREATE INDEX IF NOT EXISTS idx_x ON tbl(col);") == ("idx_x", "tbl")


def test_parse_create_index_lowercase():
    assert parse_create_index("create index idx_x on tbl(col);") == ("idx_x", "tbl")


def test_parse_create_index_leading_whitespace():
    assert parse_create_index("  CREATE  INDEX  idx_x  ON  tbl (col);") == ("idx_x", "tbl")


def test_parse_create_index_invalid_returns_none():
    assert parse_create_index("DROP INDEX idx ON tbl;") is None
    assert parse_create_index("CREATE TABLE t(x int);") is None
    assert parse_create_index("") is None
    assert parse_create_index("SELECT 1") is None


# ---- build_drop_index ----

def test_build_drop_index_basic():
    assert build_drop_index("CREATE INDEX idx_x ON tbl(col);") == "DROP INDEX `idx_x` ON `tbl`;"


def test_build_drop_index_with_backticks_and_if_not_exists():
    assert (build_drop_index("CREATE INDEX IF NOT EXISTS `idx_x` ON `tbl`(`col`);")
            == "DROP INDEX `idx_x` ON `tbl`;")


def test_build_drop_index_invalid_returns_none():
    assert build_drop_index("DROP INDEX idx ON tbl;") is None


# ---- measure_index_impact ----

def test_measure_not_connected_returns_none():
    conn = FakeConnector(connected=False)
    assert measure_index_impact(conn, "SELECT 1", ["CREATE INDEX i ON t(c);"]) is None


def test_measure_empty_ddls_returns_none():
    conn = FakeConnector()
    assert measure_index_impact(conn, "SELECT 1", []) is None


def test_measure_normal_path():
    conn = FakeConnector(benchmark_times=[0.2, 0.05])
    ddl = "CREATE INDEX idx_a ON t(a);"
    result = measure_index_impact(conn, "SELECT * FROM t WHERE a=1", [ddl], runs=3)

    assert isinstance(result, IndexImpact)
    assert result.applied_ddls == [ddl]
    assert result.skipped_ddls == []
    assert result.rolled_back is True
    assert result.error == ""
    assert result.before_time == 0.2
    assert result.after_time == 0.05
    assert result.speedup == 4.0
    # 执行了 CREATE、ANALYZE、DROP
    assert any(s == ddl for s in conn.executed)
    assert any("ANALYZE" in s for s in conn.executed)
    assert any("DROP INDEX `idx_a` ON `t`;" == s for s in conn.executed)


def test_measure_index_already_exists_skips():
    conn = FakeConnector(existing_indexes={"idx_a"})
    ddl = "CREATE INDEX idx_a ON t(a);"
    result = measure_index_impact(conn, "SELECT 1", [ddl])

    assert result.applied_ddls == []
    assert result.skipped_ddls == [ddl]
    assert result.rolled_back is True
    # 不应创建、不应回滚
    assert conn.executed == []


def test_measure_invalid_ddl_skipped():
    conn = FakeConnector()
    result = measure_index_impact(conn, "SELECT 1", ["DROP INDEX x ON t;"])
    assert result.applied_ddls == []
    assert result.skipped_ddls == ["DROP INDEX x ON t;"]


def test_measure_creation_error_still_rolls_back():
    ddl_a = "CREATE INDEX idx_a ON t(a);"
    ddl_b = "CREATE INDEX idx_b ON t(b);"
    conn = FakeConnector(fail_on="idx_b")
    result = measure_index_impact(conn, "SELECT 1", [ddl_a, ddl_b])

    assert result.applied_ddls == [ddl_a]
    assert result.error != ""
    # 已创建的 idx_a 必须被回滚
    assert "DROP INDEX `idx_a` ON `t`;" in conn.executed


def test_measure_rollback_failure_sets_rolled_back_false():
    ddl = "CREATE INDEX idx_a ON t(a);"
    conn = FakeConnector(fail_on="DROP INDEX")
    result = measure_index_impact(conn, "SELECT 1", [ddl])

    assert result.rolled_back is False
    assert result.error != ""


def test_measure_analyze_failure_ignored():
    ddl = "CREATE INDEX idx_a ON t(a);"
    conn = FakeConnector(fail_on="ANALYZE")
    result = measure_index_impact(conn, "SELECT 1", [ddl])

    assert result.applied_ddls == [ddl]
    assert result.rolled_back is True
    assert result.error == ""


def test_measure_speedup_infinite_when_after_zero():
    conn = FakeConnector(benchmark_times=[2.0, 0.0])
    ddl = "CREATE INDEX idx_a ON t(a);"
    result = measure_index_impact(conn, "SELECT 1", [ddl])
    assert result.speedup == float("inf")


def test_measure_speedup_one_when_both_zero():
    conn = FakeConnector(benchmark_times=[0.0, 0.0])
    ddl = "CREATE INDEX idx_a ON t(a);"
    result = measure_index_impact(conn, "SELECT 1", [ddl])
    assert result.speedup == 1.0


def test_measure_query_error_treated_as_not_existing():
    """索引存在性查询异常时按“不存在”处理，仍尝试创建。"""
    conn = FakeConnector(query_raises=True)
    ddl = "CREATE INDEX idx_a ON t(a);"
    result = measure_index_impact(conn, "SELECT 1", [ddl])
    assert result.applied_ddls == [ddl]
