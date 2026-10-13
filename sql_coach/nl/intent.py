"""基于关键词的意图识别：select / aggregate / count。"""
from .extractor import EntityExtractor

# aggregate 关键词直接派生自 `EntityExtractor.AGGREGATE_MAP` 的键，
# 确保"能触发聚合函数的关键词"与"判为聚合意图的关键词"始终一致，
# 避免两处各自维护导致聚合被静默丢弃（如"总额/总计/均值"）。
INTENT_KEYWORDS = {
    "aggregate": list(EntityExtractor.AGGREGATE_MAP.keys()),
    "count":     ["多少条", "几条", "数量", "计数"],
    "select":    ["查询", "查找", "找", "列出", "显示", "获取", "看看"],
}

# "数量" 同时出现在 aggregate 与 count 中：明确表达"计数"的强关键词优先命中，
# 而含糊的"数量"则让位给 aggregate（例如"统计每个城市的用户数量"应判 aggregate）。
_STRONG_COUNT_KEYWORDS = ("多少条", "几条", "计数")


class IntentRecognizer:
    """基于关键词的意图识别。"""

    def recognize(self, tokens: list[str]) -> str:
        """返回意图：select / aggregate / count。"""
        text = "".join(tokens)
        for keyword in _STRONG_COUNT_KEYWORDS:
            if keyword in text:
                return "count"
        for keyword in INTENT_KEYWORDS["aggregate"]:
            if keyword in text:
                return "aggregate"
        for keyword in INTENT_KEYWORDS["count"]:
            if keyword in text:
                return "count"
        for keyword in INTENT_KEYWORDS["select"]:
            if keyword in text:
                return "select"
        return "select"  # 默认
