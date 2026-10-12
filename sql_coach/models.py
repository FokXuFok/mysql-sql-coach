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
class Complexity:
    level: str  # simple / medium / complex
    score: int
    reasons: list[str] = field(default_factory=list)


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
class IndexImpact:
    """索引实测结果：临时建索引 → 复测 → 回滚。"""
    before_time: float          # 建索引前耗时（秒）
    after_time: float           # 建索引后耗时（秒）
    speedup: float              # before/after
    applied_ddls: list[str]     # 实际执行成功的 DDL
    skipped_ddls: list[str]     # 因索引已存在（或无法解析）而跳过的 DDL
    rolled_back: bool           # 是否已成功回滚
    error: str = ""             # 出错信息（如回滚失败）
    matched_rows: int = 0        # 命中的行数（估算/实测，0 表示未知）
    total_rows: int = 0          # 表总行数（0 表示未知）
    selectivity: float = -1.0    # 命中率 0~1；-1 表示未知
    recommended: bool = False    # 是否建议采纳该索引
    verdict: str = ""            # 中文结论


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
    optimizer_mode: str = "ai"          # dataclass 默认保持既有行为；from_env 默认 auto
    complexity_threshold: int = 8
    measure_index: bool = False         # 索引实测模式（默认关闭）

    @classmethod
    def from_env(cls, mock: bool = False) -> 'Config':
        from .config import _get_env, _get_env_int, _get_env_bool
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
            optimizer_mode=_get_env("OPTIMIZER_MODE", "auto"),
            complexity_threshold=_get_env_int("COMPLEXITY_THRESHOLD", 8),
            measure_index=_get_env_bool("MEASURE_INDEX", False),
        )