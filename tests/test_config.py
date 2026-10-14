# tests/test_config.py
import os
from sql_coach.config import Config, DBConfig, load_config, load_env_file


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_USER", "root")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    monkeypatch.setenv("DB_NAME", "testdb")
    monkeypatch.setenv("AI_MODEL", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-xxx")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    monkeypatch.setenv("BENCHMARK_RUNS", "5")

    config = Config.from_env()

    assert config.db.host == "localhost"
    assert config.db.port == 3306
    assert config.db.user == "root"
    assert config.db.password == "secret"
    assert config.db.database == "testdb"
    assert config.model == "deepseek"
    assert config.deepseek_api_key == "sk-xxx"
    assert config.benchmark_runs == 5
    assert config.mock is False


def test_config_mock_flag(monkeypatch):
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_USER", "root")
    monkeypatch.setenv("DB_PASSWORD", "x")
    monkeypatch.setenv("DB_NAME", "test")
    monkeypatch.setenv("AI_MODEL", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    monkeypatch.setenv("BENCHMARK_RUNS", "3")

    config = Config.from_env(mock=True)
    assert config.mock is True


def test_measure_index_defaults_false(monkeypatch):
    """未设置 MEASURE_INDEX 时默认关闭。"""
    monkeypatch.delenv("MEASURE_INDEX", raising=False)
    config = Config.from_env()
    assert config.measure_index is False


def test_measure_index_dataclass_default_false():
    """直接构造 Config 时 measure_index 默认 False，保持既有行为。"""
    db = DBConfig(host="h", port=3306, user="u", password="p", database="d")
    config = Config(db=db, model="deepseek", deepseek_api_key="",
                    openai_api_key="", ollama_url="http://x",
                    benchmark_runs=3, mock=False)
    assert config.measure_index is False


def test_measure_index_env_override(monkeypatch):
    monkeypatch.setenv("MEASURE_INDEX", "1")
    assert Config.from_env().measure_index is True


def test_measure_index_env_true_case_insensitive(monkeypatch):
    monkeypatch.setenv("MEASURE_INDEX", "TRUE")
    assert Config.from_env().measure_index is True


def test_measure_index_env_yes(monkeypatch):
    monkeypatch.setenv("MEASURE_INDEX", "yes")
    assert Config.from_env().measure_index is True


def test_measure_index_env_false(monkeypatch):
    monkeypatch.setenv("MEASURE_INDEX", "false")
    assert Config.from_env().measure_index is False


def test_get_env_bool_helper(monkeypatch):
    from sql_coach.config import _get_env_bool
    monkeypatch.setenv("X_FLAG", "on")
    assert _get_env_bool("X_FLAG") is True
    monkeypatch.setenv("X_FLAG", "0")
    assert _get_env_bool("X_FLAG", default=True) is False
    monkeypatch.delenv("X_FLAG", raising=False)
    assert _get_env_bool("X_FLAG", default=True) is True


def test_load_env_file_default_does_not_override(monkeypatch, tmp_path):
    """默认不覆盖已存在的环境变量（保持启动时的既有行为）。"""
    monkeypatch.setenv("SQLCOACH_TMP_KEY", "from_env")
    env_file = tmp_path / "t.env"
    env_file.write_text("SQLCOACH_TMP_KEY=from_file\n", encoding="utf-8")

    load_env_file(str(env_file))

    assert os.environ["SQLCOACH_TMP_KEY"] == "from_env"


def test_load_env_file_override_replaces_existing(monkeypatch, tmp_path):
    """override=True 时用 .env 的值覆盖已有环境变量。"""
    monkeypatch.setenv("SQLCOACH_TMP_KEY", "from_env")
    env_file = tmp_path / "t.env"
    env_file.write_text("SQLCOACH_TMP_KEY=from_file\n", encoding="utf-8")

    load_env_file(str(env_file), override=True)

    assert os.environ["SQLCOACH_TMP_KEY"] == "from_file"


def test_saved_setting_applies_without_restart(monkeypatch, tmp_path):
    """回归测试：设置对话框保存到 .env 后重新加载必须立即生效，无需重启程序。

    这正是「第 4 幕在设置里勾选索引实测，右侧却没有实测结果」的根因：
    load_env_file 默认不覆盖已有环境变量，启动时读进来的旧值把新值挡住了。
    主窗口保存配置后走的是 override_env=True 这条路径。
    """
    monkeypatch.delenv("MEASURE_INDEX", raising=False)
    env_file = tmp_path / "t.env"
    env_file.write_text("MEASURE_INDEX=false\n", encoding="utf-8")
    assert load_config(env_path=str(env_file)).measure_index is False

    # 模拟设置对话框把勾选结果写回 .env
    env_file.write_text("MEASURE_INDEX=true\n", encoding="utf-8")

    # 旧路径（不加 override）读不到新值——这就是原来的 bug
    assert load_config(env_path=str(env_file)).measure_index is False
    # 新路径（设置保存后重载走这条）：新值立即生效
    assert load_config(env_path=str(env_file), override_env=True).measure_index is True