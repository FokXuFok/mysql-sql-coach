"""基于关键词的意图识别：select / aggregate / count。"""

INTENT_KEYWORDS = {
    "aggregate": ["最高", "最低", "平均", "总和", "总数", "统计", "多少", "销售额", "数量"],
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
