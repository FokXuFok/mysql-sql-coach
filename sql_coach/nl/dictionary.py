"""从数据库 schema 构建 jieba 自定义词典，并做中文别名 → 数据库标识符的映射。"""
from typing import Optional

from ..local.schema import Schema

# 内置中文同义词表：中文词 → 候选英文标识符列表。
# 只有当候选英文名真实存在于 schema（表名/列名/注释）中时，才会建立映射；
# 候选按顺序取第一个存在的。
CN_SYNONYMS: dict[str, list[str]] = {
    # 表
    "客户": ["customer", "customers", "client", "clients"],
    "用户": ["user", "users"],
    "订单": ["order", "orders"],
    "商品": ["product", "products", "item", "items"],
    "产品": ["product", "products", "item", "items"],
    "员工": ["employee", "employees", "staff"],
    # 列
    "城市": ["city", "town"],
    "状态": ["status", "state"],
    "名称": ["name"],
    "名字": ["name"],
    "数量": ["count", "qty", "quantity", "num"],
    "金额": ["amount", "total", "price", "sum", "money"],
    "销售额": ["amount", "total", "price", "sum", "money"],
    "总额": ["amount", "total", "price", "sum", "money"],
    "时间": ["created_at", "date", "time", "created_time"],
    "日期": ["created_at", "date", "time", "created_time"],
    "编号": ["id"],
    "ID": ["id"],
    "年龄": ["age"],
    "邮箱": ["email", "mail"],
    "电话": ["phone", "tel", "mobile"],
}


def _has_cjk(text: str) -> bool:
    """是否包含中日韩表意文字（用于筛选中文别名）。"""
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


class SchemaDictionary:
    """从数据库 schema 构建的词典。

    - schema 中的表名、列名、列注释作为词条（别名 = 自身）；
    - 内置 `CN_SYNONYMS` 中文词，若其候选英文名在 schema 中真实存在则建立映射。
    """

    def __init__(self, schema: Schema):
        self._schema = schema
        self._synonyms: dict[str, str] = {}   # 小写别名 → 数据库标识符
        self._tables: set[str] = set()
        self._columns: set[str] = set()
        self._build(schema)

    def _build(self, schema: Schema) -> None:
        for table_name, table_schema in schema.tables.items():
            self._tables.add(table_name.lower())
            self._add_synonym(table_name, table_name)
            for col_name in table_schema.columns:
                self._columns.add(col_name.lower())
                self._add_synonym(col_name, col_name)
            for col_name, comment in table_schema.comments.items():
                if comment:
                    self._add_synonym(comment, col_name)

        for cn_word, candidates in CN_SYNONYMS.items():
            for candidate in candidates:
                low = candidate.lower()
                if low in self._tables or low in self._columns:
                    self._add_synonym(cn_word, candidate)
                    break

    def _add_synonym(self, alias: str, canonical: str) -> None:
        if alias:
            self._synonyms[alias.lower()] = canonical

    def resolve(self, word: str) -> Optional[str]:
        """将分词结果映射到数据库标识符（大小写不敏感）。"""
        if not word:
            return None
        return self._synonyms.get(word.lower())

    def is_table(self, word: str) -> bool:
        """该标识符是否是 schema 中的表名。"""
        return bool(word) and word.lower() in self._tables

    def is_column(self, word: str) -> bool:
        """该标识符是否是 schema 中的列名。"""
        return bool(word) and word.lower() in self._columns

    def jieba_words(self) -> list[str]:
        """返回需要加入 jieba 自定义词典的中文别名。"""
        return [w for w in self._synonyms if _has_cjk(w)]
