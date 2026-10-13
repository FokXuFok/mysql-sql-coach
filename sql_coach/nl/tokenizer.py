"""jieba 分词器，加载 schema 自定义词典。

jieba 采用惰性导入：只有真正分词时才加载，避免拖慢 CLI 启动。
分词异常时降级为简单的空格分词。
"""
from typing import Optional

from .dictionary import SchemaDictionary


class Tokenizer:
    """jieba 分词器，加载 schema 自定义词典。"""

    def __init__(self, dictionary: Optional[SchemaDictionary] = None):
        self._dictionary = dictionary
        self._jieba = None
        self._loaded = False

    def _get_jieba(self):
        """惰性加载 jieba 并注入自定义词典；失败返回 None。"""
        if not self._loaded:
            self._loaded = True
            try:
                import jieba  # 惰性导入：避免模块导入阶段拖慢启动
                if self._dictionary is not None:
                    for word in self._dictionary.jieba_words():
                        jieba.add_word(word)
                self._jieba = jieba
            except Exception:  # noqa: BLE001 - 降级不阻断
                self._jieba = None
        return self._jieba

    def tokenize(self, text: str) -> list[str]:
        """分词，返回词列表；jieba 不可用或异常时降级为空格分词。"""
        jieba = self._get_jieba()
        if jieba is None:
            return self._simple_split(text)
        try:
            return [w.strip() for w in jieba.cut(text) if w.strip()]
        except Exception:  # noqa: BLE001 - 降级不阻断
            return self._simple_split(text)

    @staticmethod
    def _simple_split(text: str) -> list[str]:
        return [w for w in (text or "").split() if w]
