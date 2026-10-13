"""EntityExtractor 实体提取测试。"""
import pytest

from sql_coach.local.schema import Schema, TableSchema
from sql_coach.nl.dictionary import SchemaDictionary
from sql_coach.nl.extractor import EntityExtractor


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


@pytest.fixture
def extractor() -> EntityExtractor:
    schema = make_schema()
    return EntityExtractor(SchemaDictionary(schema), schema)


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


def test_aggregate_target_column_not_in_columns(extractor):
    """聚合的目标列（SUM 的 amount）不应进入 columns；补入代表列。"""
    q = extractor.extract(
        ["查询", "销售额", "最高", "的", "10", "个", "客户"], "aggregate")
    assert [a.mapped for a in q.aggregates] == ["SUM(amount)"]
    assert q.columns == ["customer_name"]


def test_condition_column_not_in_columns(extractor):
    """WHERE 条件里的列（status）不应进入 columns。"""
    q = extractor.extract(["查找", "status", "为", "pending", "的", "订单"], "select")
    assert q.columns == []
    assert [c.mapped for c in q.conditions] == ["status = 'pending'"]


@pytest.mark.parametrize("columns,expected", [
    ({"id": "bigint", "name": "varchar", "customer_name": "varchar"}, "name"),
    ({"id": "bigint", "customer_name": "varchar"}, "customer_name"),
    ({"id": "bigint", "title": "varchar"}, "title"),
    ({"id": "bigint", "amount": "decimal"}, None),
])
def test_representative_column_selection_order(columns, expected):
    """Top-N 聚合（带排序）且无显式列/group_by 时，按 name → *_name → title 选代表列。"""
    schema = Schema(tables={"t": TableSchema(name="t", columns=columns)})
    ex = EntityExtractor(SchemaDictionary(schema), schema)
    q = ex.extract(["查询", "t", "数量", "最高", "的", "10", "个"], "aggregate")
    assert q.columns == ([expected] if expected else [])


def test_representative_column_requires_schema():
    """未传 schema 时保持向后兼容：不补代表列。"""
    ex = EntityExtractor(SchemaDictionary(make_schema()))
    q = ex.extract(["查询", "销售额", "最高", "的", "10", "个", "客户"], "aggregate")
    assert q.columns == []


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


# --------------------------------------------------------- 语义缺陷修复回归

def test_aggregate_total_amount_per_city(extractor):
    """Critical 1："总额" 应触发 SUM，且 city 作分组而非查询列。"""
    q = extractor.extract(["查询", "每个", "城市", "的", "订单", "总额"], "aggregate")
    assert [a.mapped for a in q.aggregates] == ["SUM(amount)"]
    assert q.group_by == ["city"]


def test_aggregate_merged_token_finds_column(extractor):
    """Important 2：jieba 把"平均年龄"合成一个 token 时仍能取到 age。"""
    q = extractor.extract(["查询", "用户", "的", "平均年龄"], "aggregate")
    assert [a.mapped for a in q.aggregates] == ["AVG(age)"]
    assert "age" not in q.columns  # 聚合目标列不得进入 SELECT / GROUP BY


def test_aggregate_skipped_when_non_count_target_missing():
    """Important 2：非 COUNT 聚合找不到目标列时跳过，绝不生成 SUM(*)。"""
    ex = EntityExtractor(SchemaDictionary(Schema()))  # 空 schema
    q = ex.extract(["查询", "销售额", "最高", "的", "10", "个", "客户"], "aggregate")
    assert q.aggregates == []
    assert q.skipped_aggregates == ["销售额"]


def test_count_still_uses_star_when_target_missing(extractor):
    """COUNT 找不到目标列时仍合法地使用 COUNT(*)。"""
    q = extractor.extract(["统计", "用户数量"], "aggregate")
    assert [a.mapped for a in q.aggregates] == ["COUNT(*)"]


def test_order_recent_prefers_time_column_over_first_column(extractor):
    """Important 3："最近" 排序优先取时间列，而非 columns[0]。"""
    q = extractor.extract(["查询", "最近", "10", "个", "用户", "的", "名称"], "select")
    assert q.order_by[0].mapped == "created_at DESC"


def test_condition_value_with_wan_unit(extractor):
    """Important 4："1万" 应换算为 10000。"""
    q = extractor.extract(["查询", "销售额", "超过", "1", "万", "的", "客户"], "select")
    assert [c.mapped for c in q.conditions] == ["amount > 10000"]


def test_condition_value_with_unit_in_single_token(extractor):
    """Important 4：jieba 未拆开"1万"时也应换算。"""
    q = extractor.extract(["查询", "销售额", "超过", "1万", "的", "客户"], "select")
    assert [c.mapped for c in q.conditions] == ["amount > 10000"]


def test_condition_quoted_literal_keeps_full_value(extractor):
    """Important 5：带引号的字面量取引号内完整内容（含内部单引号）。"""
    q = extractor.extract(
        ["查找", "name", "为", "'", "O", "'", "Brien", "'", "的", "用户"], "select")
    assert [c.mapped for c in q.conditions] == ["name = 'O'Brien'"]


def test_condition_plain_literal_unchanged(extractor):
    """Important 5：无引号的简单值仍按单 token 处理。"""
    q = extractor.extract(["查找", "status", "为", "pending", "的", "订单"], "select")
    assert [c.mapped for c in q.conditions] == ["status = 'pending'"]


def test_global_aggregate_has_no_group_by():
    """纯全局聚合不应带 GROUP BY（"用户的平均年龄"只该返回一个数）。"""
    schema = Schema(tables={"users": TableSchema(
        name="users", columns={"name": "varchar", "age": "int"})})
    q = EntityExtractor(SchemaDictionary(schema), schema).extract(
        ["查询", "用户", "的", "平均", "年龄"], "aggregate")
    assert q.columns == []          # 不应补代表列
    assert q.group_by == []


def test_topn_aggregate_still_uses_representative_column():
    """Top-N 聚合仍需代表列作分组（"销售额最高的10个客户"）。"""
    schema = Schema(tables={"customers": TableSchema(
        name="customers", columns={"customer_name": "varchar", "amount": "decimal"})})
    q = EntityExtractor(SchemaDictionary(schema), schema).extract(
        ["查询", "销售额", "最高", "的", "10", "个", "客户"], "aggregate")
    assert q.columns == ["customer_name"]


# --------------------------------------------------------- RC1~RC5 语义缺陷修复

def real_schema() -> Schema:
    """模拟真实 test 库：无 customers 表，users 无 age/amount 列。"""
    return Schema(tables={
        "orders": TableSchema(name="orders", columns={
            "id": "bigint", "user_id": "bigint", "amount": "decimal",
            "status": "varchar", "created_at": "datetime"}),
        "products": TableSchema(name="products", columns={
            "id": "bigint", "name": "varchar", "price": "decimal",
            "category": "varchar", "created_at": "datetime"}),
        "users": TableSchema(name="users", columns={
            "id": "bigint", "name": "varchar", "email": "varchar",
            "city": "varchar", "created_at": "datetime"}),
    })


def _real_extractor(value_probe=None) -> EntityExtractor:
    schema = real_schema()
    return EntityExtractor(SchemaDictionary(schema), schema, value_probe=value_probe)


def test_rc1_customer_maps_to_users_and_missing_amount_aggregate_skipped():
    """RC1：客户→users；users 无 amount 列 → SUM 被跳过而非生成 unknown_table。"""
    q = _real_extractor().extract(
        ["查询", "销售额", "最高", "的", "10", "个", "客户"], "aggregate")
    assert q.tables == ["users"]
    assert q.aggregates == []
    assert q.skipped_aggregates == ["销售额"]
    # 被跳过的聚合目标列不得残留到 SELECT / ORDER BY
    assert "amount" not in q.columns
    assert all("amount" not in o.mapped for o in q.order_by)


def test_rc2_value_probe_adds_implicit_condition():
    """RC2：'北京的用户' 通过 value_probe 命中 users.city → 生成 city = '北京'。"""

    def probe(table, column, value):
        return table == "users" and column == "city" and value == "北京"

    q = _real_extractor(value_probe=probe).extract(["查询", "北京", "的", "用户"], "select")
    assert [c.mapped for c in q.conditions] == ["city = '北京'"]


def test_rc2_value_probe_none_keeps_behavior_unchanged():
    """RC2：value_probe 为 None 时行为完全不变（不探测、不加条件）。"""
    q = _real_extractor().extract(["查询", "北京", "的", "用户"], "select")
    assert q.conditions == []


def test_rc2_value_probe_miss_records_trace():
    """RC2：候选值都没命中时跳过，并在 NLQuery 里留痕。"""
    q = _real_extractor(value_probe=lambda t, c, v: False).extract(
        ["查询", "火星", "的", "用户"], "select")
    assert q.conditions == []
    assert q.unresolved_values == ["火星"]


def test_rc3_aggregate_skipped_when_target_column_not_in_table():
    """RC3：目标列不属于任何识别到的表时跳过聚合（供上层提示）。"""
    q = _real_extractor().extract(["用户", "的", "平均", "年龄"], "aggregate")
    assert q.tables == ["users"]
    assert q.aggregates == []
    assert q.skipped_aggregates == ["平均"]


def test_rc4_group_column_kept_and_count_star():
    """RC4：'每个分类' 的 category 应作为分组列保留，且 COUNT 用 *。"""
    q = _real_extractor().extract(
        ["查询", "每个", "分类", "的", "商品", "数量"], "aggregate")
    assert q.columns == ["category"]
    assert q.group_by == ["category"]
    assert [a.mapped for a in q.aggregates] == ["COUNT(*)"]


def test_rc5_top1_without_number_implies_limit_one():
    """RC5：'最高/最低' 且无显式数字时隐含 LIMIT 1。"""
    q = _real_extractor().extract(["查询", "价格", "最高", "的", "商品"], "select")
    assert q.limit == 1


def test_rc5_explicit_number_keeps_limit():
    """RC5 回归：带显式数字时仍取该数字。"""
    q = _real_extractor().extract(
        ["查询", "销售额", "最高", "的", "10", "个", "客户"], "aggregate")
    assert q.limit == 10
