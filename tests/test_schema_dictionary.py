"""SchemaDictionary 词典管理测试。"""
from sql_coach.local.schema import Schema, TableSchema
from sql_coach.nl.dictionary import CN_SYNONYMS, SchemaDictionary


def make_schema() -> Schema:
    """构造含 customers / orders / users 三张表的测试 schema。"""
    return Schema(tables={
        "customers": TableSchema(name="customers", columns={
            "id": "bigint", "name": "varchar", "city": "varchar",
            "amount": "decimal", "created_at": "datetime"}),
        "orders": TableSchema(name="orders",
                              columns={"id": "bigint", "customer_id": "bigint",
                                       "status": "varchar", "amount": "decimal",
                                       "created_at": "datetime"},
                              comments={"amount": "订单金额"}),
        "users": TableSchema(name="users", columns={
            "id": "bigint", "name": "varchar", "city": "varchar", "age": "int",
            "email": "varchar", "phone": "varchar", "status": "varchar",
            "created_at": "datetime"}),
    })


def test_resolve_english_identifiers_case_insensitive():
    d = SchemaDictionary(make_schema())
    assert d.resolve("customers") == "customers"
    assert d.resolve("CUSTOMERS") == "customers"
    assert d.resolve("Status") == "status"


def test_resolve_unknown_returns_none():
    d = SchemaDictionary(make_schema())
    assert d.resolve("不存在的词") is None


def test_resolve_chinese_table_synonyms():
    d = SchemaDictionary(make_schema())
    assert d.resolve("客户") == "customers"
    assert d.resolve("用户") == "users"
    assert d.resolve("订单") == "orders"


def test_resolve_chinese_column_synonyms():
    d = SchemaDictionary(make_schema())
    assert d.resolve("城市") == "city"
    assert d.resolve("状态") == "status"
    assert d.resolve("名称") == "name"
    assert d.resolve("名字") == "name"
    assert d.resolve("金额") == "amount"
    assert d.resolve("销售额") == "amount"
    assert d.resolve("总额") == "amount"
    assert d.resolve("时间") == "created_at"
    assert d.resolve("日期") == "created_at"
    assert d.resolve("编号") == "id"
    assert d.resolve("年龄") == "age"
    assert d.resolve("邮箱") == "email"
    assert d.resolve("电话") == "phone"


def test_resolve_synonym_only_when_candidate_exists_in_schema():
    d = SchemaDictionary(make_schema())
    # 商品/产品 的候选（product/products/item/items）都不在 schema 中
    assert d.resolve("商品") is None
    assert d.resolve("产品") is None
    # 数量 的候选（count/qty/quantity/num）都不在 schema 中
    assert d.resolve("数量") is None


def test_column_comment_becomes_alias():
    d = SchemaDictionary(make_schema())
    assert d.resolve("订单金额") == "amount"


def test_empty_comment_is_ignored():
    schema = Schema(tables={"t": TableSchema(
        name="t", columns={"a": "int"}, comments={"a": ""})})
    d = SchemaDictionary(schema)
    assert d.resolve("") is None


def test_is_table_and_is_column():
    d = SchemaDictionary(make_schema())
    assert d.is_table("customers")
    assert not d.is_table("status")
    assert d.is_column("status")
    assert not d.is_column("customers")


def test_jieba_words_only_chinese_aliases():
    d = SchemaDictionary(make_schema())
    words = d.jieba_words()
    assert "客户" in words
    assert "销售额" in words
    assert "订单金额" in words
    # 英文标识符不进入 jieba 自定义词典
    assert "customers" not in words
    assert "status" not in words


def test_cn_synonyms_covers_required_terms():
    for term in ["客户", "用户", "订单", "商品", "产品", "员工",
                 "城市", "状态", "名称", "名字", "数量", "金额", "销售额",
                 "总额", "时间", "日期", "编号", "ID", "年龄", "邮箱", "电话"]:
        assert term in CN_SYNONYMS, f"CN_SYNONYMS 缺少 {term}"
        assert isinstance(CN_SYNONYMS[term], list)
        assert CN_SYNONYMS[term], f"{term} 的候选列表不应为空"
