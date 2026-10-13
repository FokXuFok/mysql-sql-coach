"""自然语言解析器：分词 → 意图识别 → 实体提取。"""
from ..local.schema import Schema
from ..models import NLQuery
from .dictionary import SchemaDictionary
from .extractor import EntityExtractor
from .intent import IntentRecognizer
from .tokenizer import Tokenizer


class NLParser:
    """自然语言解析器：分词 → 意图识别 → 实体提取。"""

    def __init__(self, schema: Schema, value_probe=None):
        """Args:
            schema: 数据库 schema。
            value_probe: 可选值探测回调 `(table, column, value) -> bool`，
                用于把"北京的用户"这类隐式条件落成 `city = '北京'`；
                默认 None 时行为完全不变。
        """
        self._dict = SchemaDictionary(schema)
        self._tokenizer = Tokenizer(self._dict)
        self._intent = IntentRecognizer()
        self._extractor = EntityExtractor(self._dict, schema, value_probe=value_probe)

    def parse(self, text: str) -> NLQuery:
        """解析自然语言文本，返回 NLQuery。"""
        tokens = self._tokenizer.tokenize(text)
        intent = self._intent.recognize(tokens)
        return self._extractor.extract(tokens, intent)
