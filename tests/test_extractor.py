"""EntityExtractor 实体提取测试。"""
import pytest

from sql_coach.local.schema import Schema, TableSchema
from sql_coach.nl.dictionary import SchemaDictionary
from sql_coach.nl.extractor import EntityExtractor


def make_schema() -> Schema:
    """构造含 customers / orders / users 三张表的测试 schema。"""
    return Schema(tables={
        "customers": TableSchema(name="customers", columns={
            "id": "bigint", "name": "varchar", "city": "varchar",
            "amount": "decimal", "created_at": "datetime"}),
        "orders": TableSchema(name="orders", columns={
            "id": "bigint", "customer_id": "bigint", "status": "varchar",
            "amount": "decimal", "created_at": "datetime"}),
        "users": TableSchema(name="users", columns={
            "id": "bigint", "name": "varchar", "city": "varchar", "age": "int",
            "email": "varchar", "status": "varchar", "created_at": "datetime"}),
    })


@pytest.fixture
def extractor() -> EntityExtractor:
    return EntityExtractor(SchemaDictionary(make_schema()))


def test_extract_table_from_chinese_alias(extractor):
    q = extractor.extract(["查询", "订单"], "select")
    assert q.tables == ["orders"]


def test_extract_table_when_jieba_merges_words(extractor):
    """"用户数量"被 jieba 合成一个词时仍能识别出 users 表。"""
    q = extractor.extract(["统计", "每个", "城市", "的", "用户数量"], "aggregate")
    assert q.tables == ["users"]


def test_extract_columns(extractor):
    q = extractor.extract(["查询", "城市", "和", "状态"], "select")
    assert q.columns == ["city", "status"]


def test_extract_no_duplicate_columns(extractor):
    q = extractor.extract(["查询", "城市", "和", "城市"], "select")
    assert q.columns == ["city"]


def test_extract_sum_aggregate_maps_synonym_to_column(extractor):
    q = extractor.extract(["查询", "销售额"], "aggregate")
    assert [a.mapped for a in q.aggregates] == ["SUM(amount)"]
    assert q.aggregates[0].raw == "销售额"


def test_extract_count_aggregate_without_target(extractor):
    q = extractor.extract(["统计", "用户数量"], "aggregate")
    assert [a.mapped for a in q.aggregates] == ["COUNT(*)"]


def test_extract_average_on_named_column(extractor):
    q = extractor.extract(["平均", "年龄"], "aggregate")
    assert [a.mapped for a in q.aggregates] == ["AVG(age)"]


def test_order_desc_uses_aggregate(extractor):
    q = extractor.extract(["查询", "销售额", "最高"], "aggregate")
    assert len(q.order_by) == 1
    assert q.order_by[0].mapped == "SUM(amount) DESC"


def test_order_desc_uses_time_column_for_recent(extractor):
    q = extractor.extract(["查询", "最近", "10", "条", "订单"], "select")
    assert q.order_by[0].mapped == "created_at DESC"


def test_order_asc_keyword(extractor):
    q = extractor.extract(["查询", "最早", "的", "订单"], "select")
    assert q.order_by[0].mapped == "created_at ASC"


def test_extract_limit(extractor):
    q = extractor.extract(["查询", "最近", "10", "条", "订单"], "select")
    assert q.limit == 10


def test_no_limit_without_number(extractor):
    q = extractor.extract(["有", "多少", "条", "status", "为", "paid", "的", "订单"], "count")
    assert q.limit is None


def test_extract_equality_condition(extractor):
    q = extractor.extract(["查找", "status", "为", "pending", "的", "订单"], "select")
    assert [c.mapped for c in q.conditions] == ["status = 'pending'"]


def test_extract_equality_condition_shi(extractor):
    q = extractor.extract(["查询", "status", "是", "paid", "的", "订单"], "select")
    assert [c.mapped for c in q.conditions] == ["status = 'paid'"]


def test_extract_numeric_condition_not_quoted(extractor):
    q = extractor.extract(["查询", "年龄", "大于", "18", "的", "用户"], "select")
    assert [c.mapped for c in q.conditions] == ["age > 18"]


def test_group_by_triggered_by_meige(extractor):
    q = extractor.extract(["统计", "每个", "城市", "的", "用户数量"], "aggregate")
    assert q.group_by == ["city"]


def test_group_by_empty_without_trigger(extractor):
    q = extractor.extract(["查询", "城市"], "select")
    assert q.group_by == []


def test_intent_and_raw_text_passthrough(extractor):
    q = extractor.extract(["查询", "订单"], "select")
    assert q.intent == "select"
    assert q.raw_text == "查询订单"
