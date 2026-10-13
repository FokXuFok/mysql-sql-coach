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
