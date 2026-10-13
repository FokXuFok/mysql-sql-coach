"""从数据库 schema 构建 jieba 自定义词典，并做中文别名 → 数据库标识符的映射。"""
from typing import Optional

from ..local.schema import Schema

# 中文同义组：组内任一中文词都应能映射到组内任一真实存在的英文标识符。
# 每个列表按优先级排列，候选既可以是表名也可以是列名。
_CUSTOMER = ["customer", "customers", "client", "clients",
             "user", "users", "member", "members", "buyer", "buyers"]
_ORDER = ["order", "orders", "purchase", "purchases", "sale", "sales"]
_PRODUCT = ["product", "products", "item", "items", "goods", "sku", "skus"]
_EMPLOYEE = ["employee", "employees", "staff", "worker", "workers"]
_CITY = ["city", "town", "cities"]
_STATUS = ["status", "state"]
_NAME = ["name", "title", "full_name", "username", "nickname"]
_COUNT = ["count", "qty", "quantity", "num", "number", "cnt"]
_AMOUNT = ["amount", "total", "price", "sum", "money", "fee"]
_PRICE = ["price", "unit_price"]
_TIME = ["created_at", "date", "time", "created_time", "updated_at"]
_ID = ["id"]
_AGE = ["age"]
_EMAIL = ["email", "mail"]
_PHONE = ["phone", "tel", "mobile"]
_CATEGORY = ["category", "type", "kind"]
_STOCK = ["stock", "inventory"]
_ADDRESS = ["address", "addr"]
_GENDER = ["gender", "sex"]
_BIRTHDAY = ["birthday", "birth_date"]


def _merge(*groups: list[str]) -> list[str]:
    """按顺序合并候选并去重（大小写不敏感），保证优先候选在前。"""
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for word in group:
            low = word.lower()
            if low not in seen:
                seen.add(low)
                out.append(word)
    return out


# 内置中文同义词表：中文词 → 候选英文标识符列表。
# 只有当候选英文名真实存在于 schema（表名/列名/注释）中时，才会建立映射；
# 候选按顺序取第一个存在的。
#
# 关键点：同一"中文同义组"内的词共享候选（例如 客户/顾客/用户/会员/买家），
# 因此任一中文词都能映射到 schema 里真实存在的任一同组英文名
# （库里没有 customers 时，"客户"也能落到 users）。
CN_SYNONYMS: dict[str, list[str]] = {
    # 表：客户组（客户 / 顾客 / 用户 / 会员 / 买家）
    "客户": _merge(["customer", "customers", "client", "clients"], _CUSTOMER),
    "顾客": _merge(["customer", "customers", "client", "clients"], _CUSTOMER),
    "用户": _merge(["user", "users"], _CUSTOMER),
    "会员": _merge(["member", "members"], _CUSTOMER),
    "买家": _merge(["buyer", "buyers"], _CUSTOMER),
    "订单": _merge(["order", "orders"], _ORDER),
    "商品": _merge(["product", "products"], _PRODUCT),
    "产品": _merge(["product", "products"], _PRODUCT),
    "员工": _merge(["employee", "employees"], _EMPLOYEE),
    # 列
    "城市": _CITY,
    "状态": _STATUS,
    "名称": _NAME,
    "名字": _NAME,
    "姓名": _NAME,
    "数量": _COUNT,
    "金额": _AMOUNT,
    "销售额": _AMOUNT,
    "总额": _AMOUNT,
    "价格": _PRICE,
    "单价": _PRICE,
    "时间": _TIME,
    "日期": _TIME,
    "编号": _ID,
    "ID": _ID,
    "年龄": _AGE,
    "邮箱": _EMAIL,
    "电话": _PHONE,
    "手机号": _PHONE,
    "手机": _PHONE,
    "分类": _CATEGORY,
    "类型": _CATEGORY,
    "库存": _STOCK,
    "地址": _ADDRESS,
    "性别": _GENDER,
    "生日": _BIRTHDAY,
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
