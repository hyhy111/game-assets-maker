# -*- mode: python ; coding: utf-8 -*-
import sys
import tomllib
from pathlib import Path

"""
PyInstaller spec for Game Assets Maker - WebView UI (PyWebView + Vue3)
Usage: uv run pyinstaller GameAssetsMaker.spec

Bundles the GUI and Agent CLI in one directory with shared runtime libraries.
Model weights and user configuration are not bundled.
"""

from PyInstaller.building.build_main import Analysis
from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.utils.hooks import copy_metadata

if sys.platform == 'darwin':
    from PyInstaller.building.osx import BUNDLE

APP_DISPLAY_NAME = 'Game Assets Maker'
with (Path(SPECPATH) / 'pyproject.toml').open('rb') as stream:
    APP_VERSION = tomllib.load(stream)['project']['version']

a = Analysis(
    ['backend/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('pyproject.toml', '.'),
        ('frontend/dist', 'frontend/dist'),
        ('backend', 'backend'),
        ('src/core', 'src/core'),
        ('src/utils', 'src/utils'),
        ('icon', 'icon'),
    ] + copy_metadata('rembg') + copy_metadata('pymatting'),
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

# Analyze the console entry separately so it never starts the desktop window.
agent_analysis = Analysis(
    ['scripts/gam_agent_entry.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchvision', 'torchaudio', 'pytest', 'matplotlib', 'pandas'],
    noarchive=False,
    optimize=0,
)
agent_pyz = PYZ(agent_analysis.pure)
agent_exe = EXE(
    agent_pyz,
    agent_analysis.scripts,
    [],
    exclude_binaries=True,
    name='gam-agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='_internal',
)

coll = COLLECT(
    exe,
    agent_exe,
    a.binaries,
    a.datas,
    agent_analysis.binaries,
    agent_analysis.datas,
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
        version=APP_VERSION,
        # The console sibling must not make the GUI a background-only app.
        info_plist={
            'LSBackgroundOnly': False,
            'NSHighResolutionCapable': True,
            'CFBundleShortVersionString': APP_VERSION,
            'CFBundleVersion': APP_VERSION,
        },
    )
