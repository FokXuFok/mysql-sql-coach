# sql-coach.spec
# -*- mode: python ; coding: utf-8 -*-
"""SQL Coach GUI PyInstaller 配置 (onedir, 含 .env.example 模板)。"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # .env.example 模板打包进 _internal/, 用户复制到 exe 同级改名 .env
        ('.env.example', '.'),
    ],
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
    [],
    exclude_binaries=True,
    name='sql-coach-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    a.zipfiles,
    strip=False,
    upx=False,
    name='sql-coach-gui',
)
