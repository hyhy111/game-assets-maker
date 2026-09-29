# -*- mode: python ; coding: utf-8 -*-
import os
import sys

"""
PyInstaller spec for Game Assets Maker - WebView UI (PyWebView + Vue3)
Usage: uv run pyinstaller GameAssetsMaker.spec

Uses one-directory mode. Model weights are downloaded on demand and are not bundled.
"""

from PyInstaller.building.build_main import Analysis
from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.utils.hooks import copy_metadata

if sys.platform == 'darwin':
    from PyInstaller.building.osx import BUNDLE

APP_DISPLAY_NAME = 'Game Assets Maker'

a = Analysis(
    ['backend/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('frontend/dist', 'frontend/dist'),
        ('backend', 'backend'),
        ('src/core', 'src/core'),
        ('src/utils', 'src/utils'),
        ('icon', 'icon'),
        # config.json is an optional gitignored legacy dev config; installed
        # releases read the per-user config and do not require it.
    ] + ([('config.json', '.')] if os.path.exists('config.json') else []) + copy_metadata('rembg') + copy_metadata('pymatting'),
    hiddenimports=[
        'rembg',
        'rembg.session_factory',
        'pymatting',
        'onnxruntime',
        'cv2',
        'PIL',
        'numpy',
        'psd_tools',
        'src.core.image_aligning',
        'src.utils.logger',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch',
        'torchvision',
        'torchaudio',
        'pytest',
        'matplotlib',
        'pandas',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='game-assets-maker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon/app-icon.ico',
    contents_directory='_internal',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='game-assets-maker',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name=f'{APP_DISPLAY_NAME}.app',
        bundle_identifier='com.hyhy111.game-assets-maker',
        icon='icon/app-icon.icns',
    )
