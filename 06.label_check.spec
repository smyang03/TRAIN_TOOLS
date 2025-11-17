# -*- mode: python ; coding: utf-8 -*-
import sys
sys.setrecursionlimit(5000)  # RecursionError 해결

block_cipher = None

# 불필요한 패키지 제외 - PyInstaller 빌드 속도 향상 및 RecursionError 방지
excludes = [
    'tensorflow',
    'tensorflow.python',
    'tensorflow.compat',
    'keras',
    'torch',
    'torchvision',
    'torchaudio',
    'scipy',
    'matplotlib',
    'IPython',
    'jupyter',
    'jupyter_client',
    'jupyter_core',
    'notebook',
    'nbconvert',
    'nbformat',
    'pandas',
    'sklearn',
    'sympy',
    'sphinx',
    'pytest',
    'babel',
    'jinja2',
    'docutils',
    'lxml',
    'openpyxl',
    'pyarrow',
    'botocore',
    'cryptography',
    'zmq',
    'PyQt5',
    'win32com',
    'pywintypes',
    'pythoncom',
    'argon2',
    'cloudpickle',
    'jsonschema',
]

a = Analysis(
    ['06.label_check.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    name='06.label_check',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
