# gui/paths.py
"""路径工具: 定位 .env 文件。

PyInstaller 打包后 (sys.frozen), 工作目录可能不是 .exe 所在目录,
需要显式指向 .exe 同目录的 .env。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def get_env_path() -> str:
    """返回 .env 文件绝对路径。

    - 打包模式 (sys.frozen): .exe 同目录下的 .env
    - 开发模式: 当前工作目录下的 .env (原行为)
    """
    if getattr(sys, "frozen", False):
        # PyInstaller: .exe 所在目录
        base = Path(sys.executable).parent
    else:
        # 开发模式: cwd
        base = Path.cwd()
    return str(base / ".env")
