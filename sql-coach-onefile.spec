# sql-coach-onefile.spec
# -*- mode: python ; coding: utf-8 -*-
"""SQL Coach GUI 单文件打包配置 (onefile)。

本地构建（exe 输出到项目根目录）:
    pyinstaller sql-coach-onefile.spec --clean --noconfirm --distpath .

CI 构建（exe 输出到 dist/，再打包为 zip 上传 Release）:
    pyinstaller sql-coach-onefile.spec --clean --noconfirm
"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('.env.example', '.')],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'matplotlib.backends.backend_qtagg',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'IPython', 'jedi', 'prompt_toolkit',
        'pytest', '_pytest', 'tkinter',
        'unittest', 'pydoc_data', 'test',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='sql-coach-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
