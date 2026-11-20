# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
import os
from pathlib import Path

msvc = [Path(os.environ['SystemRoot']) / 'System32' / name for name in ('msvcp140.dll', 'msvcp140_1.dll')]
if any(not path.is_file() for path in msvc):
    raise RuntimeError('The Windows GPU worker build requires the MSVC 14 redistributable DLLs')

a = Analysis(
    ['scripts/gam_gpu_worker.py'],
    pathex=['.'],
    binaries=[(str(path), '.') for path in msvc],
    hiddenimports=collect_submodules('PIL') + ['numpy', 'flatbuffers', 'packaging', 'google.protobuf'],
    excludes=['torch', 'torchvision', 'torchaudio', 'onnxruntime', 'cv2', 'pytest', 'tkinter', 'matplotlib'],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='gam-gpu-worker', console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name='gpu-worker', upx=False)
