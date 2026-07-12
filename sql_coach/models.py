"""Shared data models for SQL Coach."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SQLInfo:
    raw_sql: str
    sql_type: str  # SELECT/UPDATE/DELETE/INSERT
    tables: list[str]
    columns: list[str]
    where_conditions: list[str]
    join_tables: list[str]
    order_by: list[str]


@dataclass
class ExplainRow:
    id: int
    select_type: str
    table: str
    type: str  # ALL/index/range/ref/eq_ref/const
    key: Optional[str]
    rows: int
    extra: str


@dataclass
class ExplainResult:
    rows: list[ExplainRow]
    is_full_scan: bool
    missing_indexes: list[str]
    problems: list[str]


@dataclass
class Problem:
    severity: str  # critical/warning/info
    table: str
    description: str
    suggestion: str


@dataclass
class AnalysisResult:
    problems: list[Problem]
    optimized_sql: str
    index_ddls: list[str]
    explanation: str


@dataclass
class BenchmarkResult:
    original_time: float
    optimized_time: float
    speedup: float
    original_rows: int
    optimized_rows: int


@dataclass
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


@dataclass
class Config:
    db: DBConfig
    model: str
    deepseek_api_key: str
    openai_api_key: str
    ollama_url: str
    benchmark_runs: int
    mock: bool

    @classmethod
    def from_env(cls, mock: bool = False) -> 'Config':
        from .config import _get_env, _get_env_int
        db = DBConfig(
            host=_get_env("DB_HOST", "localhost"),
            port=_get_env_int("DB_PORT", 3306),
            user=_get_env("DB_USER", "root"),
            password=_get_env("DB_PASSWORD", ""),
            database=_get_env("DB_NAME", "test"),
        )
        return cls(
            db=db,
            model=_get_env("AI_MODEL", "deepseek"),
            deepseek_api_key=_get_env("DEEPSEEK_API_KEY"),
            openai_api_key=_get_env("OPENAI_API_KEY"),
            ollama_url=_get_env("OLLAMA_URL", "http://localhost:11434"),
            benchmark_runs=_get_env_int("BENCHMARK_RUNS", 3),
            mock=mock,
        )