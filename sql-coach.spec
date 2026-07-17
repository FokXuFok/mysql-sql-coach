# sql-coach.spec
# PyInstaller 打包配置。运行: pyinstaller sql-coach.spec
# -*- mode: python ; coding: utf-8 -*-
"""SQL Coach GUI PyInstaller 打包配置。

采用 onedir 模式 (而非 onefile) 以大幅加速启动:
  - onefile: 每次启动解压 89MB 到 %TEMP%, 启动 5-10 秒
  - onedir:  依赖已在目录里, 启动 1-2 秒
关闭 UPX 压缩避免运行时解压 DLL。
"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 包含 sql_coach 包的非 .py 资源 (如有)
    ],
    hiddenimports=[
        # PySide6 / matplotlib 常见的隐藏导入
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'matplotlib.backends.backend_qtagg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onedir 模式: 依赖输出到 dist/sql-coach-gui/ 目录, 启动时无需解压
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir: 二进制放到 COLLECT 里, 不嵌入 EXE
    name='sql-coach-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 关闭 UPX: 避免运行时解压, 启动更快
    console=False,  # --windowed: 不弹出控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,  # 关闭 UPX
    upx_exclude=[],
    name='sql-coach-gui',  # 输出目录: dist/sql-coach-gui/
)
