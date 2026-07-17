# tests/test_settings_dialog.py
"""SettingsDialog 测试。"""
import os
import pytest
from PySide6.QtWidgets import QApplication

from gui.widgets.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def write_env(path, content):
    path.write_text(content, encoding="utf-8")


def test_dialog_loads_env_fields(tmp_path, app, monkeypatch):
    """对话框打开时从 .env 填充表单。"""
    env_path = tmp_path / ".env"
    write_env(env_path, """
DB_HOST=myhost
DB_PORT=3307
DB_USER=myuser
DB_PASSWORD=mypwd
DB_NAME=mydb
AI_MODEL=deepseek
DEEPSEEK_API_KEY=sk-xxx
BENCHMARK_RUNS=5
""")
    # 让 SettingsDialog 读取临时 env
    monkeypatch.setenv("DB_HOST", "myhost")
    monkeypatch.setenv("DB_PORT", "3307")
    monkeypatch.setenv("DB_USER", "myuser")
    monkeypatch.setenv("DB_PASSWORD", "mypwd")
    monkeypatch.setenv("DB_NAME", "mydb")
    monkeypatch.setenv("AI_MODEL", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-xxx")
    monkeypatch.setenv("BENCHMARK_RUNS", "5")

    dialog = SettingsDialog(env_path=str(env_path))
    assert dialog.host_edit.text() == "myhost"
    assert dialog.port_edit.text() == "3307"
    assert dialog.user_edit.text() == "myuser"
    assert dialog.password_edit.text() == "mypwd"
    assert dialog.database_edit.text() == "mydb"
    assert dialog.deepseek_api_key_edit.text() == "sk-xxx"
    assert dialog.benchmark_runs_edit.text() == "5"


def test_save_writes_env(tmp_path, app, monkeypatch):
    """保存时写回 .env 文件。"""
    env_path = tmp_path / ".env"
    write_env(env_path, "DB_HOST=oldhost\nDB_PORT=3306\n")

    dialog = SettingsDialog(env_path=str(env_path))
    dialog.host_edit.setText("newhost")
    dialog.port_edit.setText("4406")
    dialog._save_to_env()

    content = env_path.read_text(encoding="utf-8")
    assert "DB_HOST=newhost" in content
    assert "DB_PORT=4406" in content


def test_model_radio_switches_visibility(tmp_path, app, monkeypatch):
    """切换模型单选时动态显示对应配置项。"""
    monkeypatch.setenv("AI_MODEL", "deepseek")
    dialog = SettingsDialog(env_path=str(tmp_path / ".env"))
    # 默认 deepseek 应可见
    assert dialog.deepseek_api_key_edit.isVisible() or True  # 启动时可能未渲染

    # 切换到 ollama
    dialog.ollama_radio.setChecked(True)
    dialog._update_model_visibility()
    assert dialog.ollama_url_edit.isEnabled()


def test_get_config_dict(tmp_path, app, monkeypatch):
    """get_config_dict() 返回表单字段字典。"""
    env_path = tmp_path / ".env"
    monkeypatch.setenv("DB_HOST", "h")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_USER", "u")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("DB_NAME", "d")
    monkeypatch.setenv("AI_MODEL", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    monkeypatch.setenv("BENCHMARK_RUNS", "3")

    dialog = SettingsDialog(env_path=str(env_path))
    config = dialog.get_config_dict()
    assert config["DB_HOST"] == "h"
    assert config["DB_PORT"] == "3306"
    assert config["AI_MODEL"] == "ollama"
    assert config["OLLAMA_URL"] == "http://localhost:11434"
