# gui/widgets/settings_dialog.py
"""设置对话框, QDialog 子类。

读取 .env 填充表单, 保存时写回 .env。
模型单选切换时动态显示对应模型的配置项。
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QVBoxLayout, QWidget,
)

# .env 字段顺序 (写回时用)
_ENV_KEYS = [
    "DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME",
    "AI_MODEL", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
    "OLLAMA_URL", "BENCHMARK_RUNS",
]


def _get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


class SettingsDialog(QDialog):
    """设置对话框。"""

    def __init__(
        self,
        env_path: str = ".env",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.env_path = env_path
        self.setWindowTitle("设置")
        self.resize(540, 580)
        self._build_ui()
        self._load_from_env()
        self._connect_signals()

    # ---- UI ----
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- MySQL 连接 ---
        db_group = QGroupBox("MySQL 连接")
        db_form = QFormLayout(db_group)
        self.host_edit = QLineEdit()
        self.port_edit = QLineEdit()
        self.user_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.database_edit = QLineEdit()
        db_form.addRow("Host:", self.host_edit)
        db_form.addRow("Port:", self.port_edit)
        db_form.addRow("User:", self.user_edit)
        db_form.addRow("Password:", self.password_edit)
        db_form.addRow("Database:", self.database_edit)

        # 测试连接按钮
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._on_test_connection)
        test_row = QHBoxLayout()
        test_row.addStretch(1)
        test_row.addWidget(self.test_btn)
        test_row_widget = QWidget()
        test_row_widget.setLayout(test_row)
        db_form.addRow(test_row_widget)
        layout.addWidget(db_group)

        # --- AI 模型 ---
        ai_group = QGroupBox("AI 模型")
        ai_layout = QVBoxLayout(ai_group)

        # 模型单选
        radio_row = QHBoxLayout()
        self.deepseek_radio = QRadioButton("DeepSeek")
        self.openai_radio = QRadioButton("OpenAI")
        self.ollama_radio = QRadioButton("Ollama")
        self.deepseek_radio.setChecked(True)
        radio_row.addWidget(self.deepseek_radio)
        radio_row.addWidget(self.openai_radio)
        radio_row.addWidget(self.ollama_radio)
        radio_row.addStretch(1)
        radio_widget = QWidget()
        radio_widget.setLayout(radio_row)
        ai_layout.addWidget(radio_widget)

        # 动态配置区
        self.deepseek_api_key_edit = QLineEdit()
        self.deepseek_api_key_edit.setEchoMode(QLineEdit.Password)
        self.openai_api_key_edit = QLineEdit()
        self.openai_api_key_edit.setEchoMode(QLineEdit.Password)
        self.ollama_url_edit = QLineEdit()

        self.deepseek_form = QFormLayout()
        self.deepseek_form.addRow("DeepSeek API Key:", self.deepseek_api_key_edit)

        self.openai_form = QFormLayout()
        self.openai_form.addRow("OpenAI API Key:", self.openai_api_key_edit)

        self.ollama_form = QFormLayout()
        self.ollama_form.addRow("Ollama URL:", self.ollama_url_edit)

        ai_layout.addLayout(self.deepseek_form)
        ai_layout.addLayout(self.openai_form)
        ai_layout.addLayout(self.ollama_form)
        layout.addWidget(ai_group)

        # --- 通用 ---
        common_group = QGroupBox("通用")
        common_form = QFormLayout(common_group)
        self.benchmark_runs_edit = QLineEdit()
        common_form.addRow("Benchmark 次数:", self.benchmark_runs_edit)
        layout.addWidget(common_group)

        # --- 底部按钮 ---
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.save_btn = QPushButton("💾 保存到 .env")
        self.save_btn.clicked.connect(self._on_save_clicked)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _connect_signals(self) -> None:
        """绑定模型单选切换。"""
        self.deepseek_radio.toggled.connect(self._update_model_visibility)
        self.openai_radio.toggled.connect(self._update_model_visibility)
        self.ollama_radio.toggled.connect(self._update_model_visibility)
        self._update_model_visibility()

    # ---- 数据加载/保存 ----
    def _load_from_env(self) -> None:
        """从环境变量填充表单 (load_config 已加载 .env)。"""
        self.host_edit.setText(_get_env("DB_HOST", "localhost"))
        self.port_edit.setText(_get_env("DB_PORT", "3306"))
        self.user_edit.setText(_get_env("DB_USER", "root"))
        self.password_edit.setText(_get_env("DB_PASSWORD", ""))
        self.database_edit.setText(_get_env("DB_NAME", "test"))
        self.deepseek_api_key_edit.setText(_get_env("DEEPSEEK_API_KEY", ""))
        self.openai_api_key_edit.setText(_get_env("OPENAI_API_KEY", ""))
        self.ollama_url_edit.setText(_get_env("OLLAMA_URL", "http://localhost:11434"))
        self.benchmark_runs_edit.setText(_get_env("BENCHMARK_RUNS", "3"))

        model = _get_env("AI_MODEL", "deepseek").lower()
        if model == "openai":
            self.openai_radio.setChecked(True)
        elif model == "ollama":
            self.ollama_radio.setChecked(True)
        else:
            self.deepseek_radio.setChecked(True)

    def _update_model_visibility(self) -> None:
        """切换模型时动态显示对应配置项。"""
        # 全部隐藏, 仅显示选中模型的字段
        for i in range(self.deepseek_form.rowCount()):
            self.deepseek_form.itemAt(i, QFormLayout.LabelRole).widget().setVisible(False)
            self.deepseek_form.itemAt(i, QFormLayout.FieldRole).widget().setVisible(False)
        for i in range(self.openai_form.rowCount()):
            self.openai_form.itemAt(i, QFormLayout.LabelRole).widget().setVisible(False)
            self.openai_form.itemAt(i, QFormLayout.FieldRole).widget().setVisible(False)
        for i in range(self.ollama_form.rowCount()):
            self.ollama_form.itemAt(i, QFormLayout.LabelRole).widget().setVisible(False)
            self.ollama_form.itemAt(i, QFormLayout.FieldRole).widget().setVisible(False)

        if self.deepseek_radio.isChecked():
            for i in range(self.deepseek_form.rowCount()):
                self.deepseek_form.itemAt(i, QFormLayout.LabelRole).widget().setVisible(True)
                self.deepseek_form.itemAt(i, QFormLayout.FieldRole).widget().setVisible(True)
        elif self.openai_radio.isChecked():
            for i in range(self.openai_form.rowCount()):
                self.openai_form.itemAt(i, QFormLayout.LabelRole).widget().setVisible(True)
                self.openai_form.itemAt(i, QFormLayout.FieldRole).widget().setVisible(True)
        elif self.ollama_radio.isChecked():
            for i in range(self.ollama_form.rowCount()):
                self.ollama_form.itemAt(i, QFormLayout.LabelRole).widget().setVisible(True)
                self.ollama_form.itemAt(i, QFormLayout.FieldRole).widget().setVisible(True)

    def get_config_dict(self) -> dict[str, str]:
        """返回表单字段为字典 (key=value)。"""
        if self.deepseek_radio.isChecked():
            model = "deepseek"
        elif self.openai_radio.isChecked():
            model = "openai"
        else:
            model = "ollama"
        return {
            "DB_HOST": self.host_edit.text(),
            "DB_PORT": self.port_edit.text(),
            "DB_USER": self.user_edit.text(),
            "DB_PASSWORD": self.password_edit.text(),
            "DB_NAME": self.database_edit.text(),
            "AI_MODEL": model,
            "DEEPSEEK_API_KEY": self.deepseek_api_key_edit.text(),
            "OPENAI_API_KEY": self.openai_api_key_edit.text(),
            "OLLAMA_URL": self.ollama_url_edit.text(),
            "BENCHMARK_RUNS": self.benchmark_runs_edit.text(),
        }

    def _save_to_env(self) -> None:
        """把表单字段写回 .env 文件。"""
        config = self.get_config_dict()
        lines = []
        for key in _ENV_KEYS:
            value = config.get(key, "")
            lines.append(f"{key}={value}")
        # 写入时保留之前注释行 (这里简化: 全量重写)
        with open(self.env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    # ---- 事件处理 ----
    def _on_test_connection(self) -> None:
        """测试连接: 创建临时 SQLCoach, 验证连通性。"""
        from sql_coach.models import Config, DBConfig
        from sql_coach.coach import SQLCoach
        from sql_coach.db.connector import DBConnector

        try:
            db_config = DBConfig(
                host=self.host_edit.text() or "localhost",
                port=int(self.port_edit.text() or "3306"),
                user=self.user_edit.text() or "root",
                password=self.password_edit.text(),
                database=self.database_edit.text() or "test",
            )
            connector = DBConnector(db_config)
            ok = connector.connect()
            connector.close()
            if ok:
                self.save_btn.setText("✅ 连接成功 - 点击保存")
            else:
                self.save_btn.setText("❌ 连接失败 - 检查配置")
        except Exception as e:
            self.save_btn.setText(f"❌ 错误: {str(e)[:30]}")

    def _on_save_clicked(self) -> None:
        """保存: 写回 .env, accept 关闭。"""
        self._save_to_env()
        self.accept()
