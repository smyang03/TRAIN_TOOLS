# -*- mode: python ; coding: utf-8 -*-
import sys
# RecursionError 해결 - sympy 등 복잡한 패키지로 인한 깊은 재귀 처리
# Python 최대 recursion limit 설정 (일반적으로 100000 이상 안전)
sys.setrecursionlimit(100000)

block_cipher = None

# 불필요한 패키지 제외 - PyInstaller 빌드 속도 향상 및 RecursionError 방지
excludes = [
    # TensorFlow / Keras
    'tensorflow',
    'tensorflow.python',
    'tensorflow.compat',
    'keras',

    # PyTorch
    'torch',
    'torchvision',
    'torchaudio',
    'torch.testing',
    'torch.testing._internal',

    # SciPy (RecursionError 주요 원인)
    'scipy',
    'scipy.special',
    'scipy.linalg',
    'scipy.sparse',
    'scipy.spatial',
    'scipy.stats',
    'scipy.optimize',
    'scipy.integrate',
    'scipy.interpolate',

    # SymPy (RecursionError 주요 원인)
    'sympy',
    'sympy.core',
    'sympy.logic',
    'sympy.parsing',

    # Matplotlib
    'matplotlib',
    'matplotlib.backends',
    'matplotlib.pyplot',

    # Pandas
    'pandas',
    'pandas.plotting',
    'pandas.io',

    # Jupyter / IPython
    'IPython',
    'jupyter',
    'jupyter_client',
    'jupyter_core',
    'notebook',
    'nbconvert',
    'nbformat',

    # ML Libraries
    'sklearn',
    'scikit-learn',

    # Documentation / Testing
    'sphinx',
    'pytest',
    'docutils',

    # Templates / i18n
    'babel',
    'jinja2',

    # XML / Data
    'lxml',
    'openpyxl',
    'pyarrow',

    # AWS / Cloud
    'botocore',
    'boto3',
    's3transfer',

    # Security / Crypto
    'cryptography',
    'argon2',

    # Qt
    'PyQt5',
    'PyQt5.QtCore',
    'PyQt5.QtWidgets',
    'PyQt5.QtGui',
    'qtpy',

    # Windows COM
    'win32com',
    'pywintypes',
    'pythoncom',

    # Misc
    'zmq',
    'cloudpickle',
    'jsonschema',
    'expecttest',
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
    upx=False,  # UPX 압축 비활성화 - 빌드 속도 향상 및 메모리 사용량 감소
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
