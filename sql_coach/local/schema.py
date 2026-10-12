"""数据库 schema 读取（供本地规则校验），连不上库时降级为空 schema。"""
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TableSchema:
    name: str
    columns: dict[str, str] = field(default_factory=dict)
    indexes: list[list[str]] = field(default_factory=list)


@dataclass
class Schema:
    tables: dict[str, TableSchema] = field(default_factory=dict)

    def has_table(self, table: str) -> bool:
        """该表是否已从数据库读到（用于区分"已校验"与"未校验"）。"""
        return table.lower() in self.tables

    def has_index_on(self, table: str, column: str) -> bool:
        """该列是否为某个索引的最左列（MySQL 最左前缀语义）。"""
        t = self.tables.get(table.lower())
        if t is None:
            return False
        col = column.lower()
        return any(idx and idx[0].lower() == col for idx in t.indexes)

    def column_type(self, table: str, column: str) -> Optional[str]:
        t = self.tables.get(table.lower())
        if t is None:
            return None
        return t.columns.get(column.lower())

    def __bool__(self) -> bool:
        return bool(self.tables)


class SchemaProvider:
    """从 information_schema 读取表结构与索引，按表累积缓存。

    注意：provider 会被 SQLCoach 复用（CLI 交互模式一次会话分析多条 SQL），
    因此缓存必须按表维度累积，不能"第一次查了谁就一直返回谁"。
    """

    def __init__(self, connector=None):
        self.connector = connector
        self._tables: dict[str, TableSchema] = {}
        self._attempted: set[str] = set()

    def load(self, tables: list[str]) -> Schema:
        if self.connector is None or not self._is_connected():
            return Schema()
        wanted = [t for t in tables if t and t.lower() not in self._attempted]
        if wanted:
            try:
                fetched = self._read(wanted)
            except Exception as e:  # noqa: BLE001 - 降级不阻断
                logger.warning("读取 schema 失败，降级为空 schema: %s", e)
                return Schema(tables=dict(self._tables))
            self._merge(fetched)
            self._attempted.update(t.lower() for t in wanted)
        return Schema(tables=dict(self._tables))

    def _merge(self, schema: Schema) -> None:
        for name, ts in schema.tables.items():
            existing = self._tables.get(name)
            if existing is None:
                self._tables[name] = ts
                continue
            existing.columns.update(ts.columns)
            for idx in ts.indexes:
                if idx not in existing.indexes:
                    existing.indexes.append(idx)

    def _is_connected(self) -> bool:
        checker = getattr(self.connector, "is_connected", None)
        return bool(checker()) if callable(checker) else False

    def _read(self, tables: list[str]) -> Schema:
        schema = Schema()
        if not tables:
            return schema
        lowered = [t.lower() for t in tables]
        placeholders = ",".join(["%s"] * len(lowered))

        for tname, cname, dtype in self.connector.query(
            "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS "
            f"WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) IN ({placeholders}) "
            "ORDER BY TABLE_NAME, ORDINAL_POSITION",
            tuple(lowered),
        ):
            ts = schema.tables.setdefault(tname.lower(), TableSchema(name=tname))
            ts.columns[cname.lower()] = (dtype or "").lower()

        grouped: dict[tuple[str, str], list[tuple[int, str]]] = {}
        for tname, iname, seq, cname in self.connector.query(
            "SELECT TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX, COLUMN_NAME "
            "FROM information_schema.STATISTICS "
            f"WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) IN ({placeholders}) "
            "ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX",
            tuple(lowered),
        ):
            grouped.setdefault((tname.lower(), iname), []).append((seq, cname))
        for (tname, _iname), cols in grouped.items():
            ts = schema.tables.setdefault(tname, TableSchema(name=tname))
            ts.indexes.append([c for _, c in sorted(cols)])
        return schema
