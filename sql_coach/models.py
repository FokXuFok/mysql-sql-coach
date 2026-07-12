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