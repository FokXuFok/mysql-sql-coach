"""IntentRecognizer 意图识别测试。"""
import pytest

from sql_coach.nl.intent import INTENT_KEYWORDS, IntentRecognizer


def recognize(text: str) -> str:
    return IntentRecognizer().recognize(list(text))


@pytest.mark.parametrize("tokens,expected", [
    (["查询", "订单"], "select"),
    (["查找", "订单"], "select"),
    (["列出", "用户"], "select"),
    (["显示", "数据"], "select"),
    (["获取", "订单"], "select"),
    (["看看", "订单"], "select"),
    (["订单"], "select"),  # 无关键词默认 select
])
def test_select_intent(tokens, expected):
    assert IntentRecognizer().recognize(tokens) == expected


@pytest.mark.parametrize("tokens", [
    ["查询", "销售额", "最高", "的", "10", "个", "客户"],
    ["统计", "每个", "城市", "的", "用户数量"],
    ["平均", "年龄"],
    ["总和"],
    ["总数"],
])
def test_aggregate_intent(tokens):
    assert IntentRecognizer().recognize(tokens) == "aggregate"


@pytest.mark.parametrize("tokens", [
    ["有", "多少", "条", "status", "为", "paid", "的", "订单"],
    ["几", "条", "订单"],
    ["计数"],
])
def test_count_intent(tokens):
    assert IntentRecognizer().recognize(tokens) == "count"


def test_bare_shu_liang_defaults_to_aggregate():
    """单独的"数量"属歧义词，按文档关键词顺序归 aggregate。"""
    assert IntentRecognizer().recognize(["数量"]) == "aggregate"


def test_ambiguous_shu_liang_with_statistics_is_aggregate():
    """锁定歧义："统计...数量" 应判为 aggregate 而非 count。"""
    assert IntentRecognizer().recognize(
        ["统计", "每个", "城市", "的", "用户数量"]) == "aggregate"


def test_ambiguous_duo_shao_tiao_is_count():
    """锁定歧义："有多少条..." 应判为 count（强计数关键词优先）。"""
    assert IntentRecognizer().recognize(
        ["有", "多少", "条", "status", "为", "paid", "的", "订单"]) == "count"


def test_intent_keywords_shape():
    assert set(INTENT_KEYWORDS) == {"aggregate", "count", "select"}
    assert all(isinstance(v, list) for v in INTENT_KEYWORDS.values())


def test_aggregate_keywords_derived_from_aggregate_map():
    """aggregate 关键词必须**包含** AGGREGATE_MAP 的全部键，避免两处漂移。"""
    from sql_coach.nl.extractor import EntityExtractor

    derived = set(EntityExtractor.AGGREGATE_MAP)
    assert derived <= set(INTENT_KEYWORDS["aggregate"])


@pytest.mark.parametrize("tokens", [
    ["查询", "每个", "城市", "的", "订单", "总额"],
    ["总计"],
    ["均值"],
])
def test_aggregate_intent_covers_map_only_keywords(tokens):
    """总额 / 总计 / 均值 只存在于 AGGREGATE_MAP，也应判为 aggregate。"""
    assert IntentRecognizer().recognize(tokens) == "aggregate"


def test_extra_aggregate_keywords_still_recognized():
    """补的意图词（统计/多少）仍应判为 aggregate，且强计数词优先。"""
    r = IntentRecognizer()
    assert r.recognize(["统计", "各", "城市", "的", "用户"]) == "aggregate"
    assert r.recognize(["销售额", "是", "多少"]) == "aggregate"
    # 强计数词仍优先
    assert r.recognize(["有", "多少条", "订单"]) == "count"


def test_skipped_aggregates_is_declared_field():
    """skipped_aggregates 必须是 NLQuery 的正式字段，而非动态属性。"""
    from dataclasses import fields
    from sql_coach.models import NLQuery
    assert "skipped_aggregates" in {f.name for f in fields(NLQuery)}
