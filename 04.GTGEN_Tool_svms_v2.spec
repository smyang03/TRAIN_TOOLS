# -*- mode: python ; coding: utf-8 -*-
import sys
# RecursionError 해결 - label_check와 동일하게 100000으로 설정
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

    # SciPy
    'scipy',
    'scipy.special',
    'scipy.linalg',
    'scipy.sparse',

    # SymPy
    'sympy',
    'sympy.core',

    # Matplotlib
    'matplotlib',
    'matplotlib.backends',

    # Jupyter / IPython
    'IPython',
    'jupyter',
    'jupyter_client',
    'jupyter_core',
    'notebook',
    'nbconvert',
    'nbformat',

    # ML Libraries
    'pandas',
    'sklearn',

    # Documentation / Testing
    'sphinx',
    'pytest',
    'docutils',

    # Templates / i18n
    'babel',
    'jinja2',

    # Data
    'lxml',
    'openpyxl',
    'pyarrow',
    'botocore',

    # Security
    'cryptography',
    'argon2',

    # Qt
    'PyQt5',

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
    ['04.GTGEN_Tool_svms_v2.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # tkinter 관련 (exe 빌드 시 필수)
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        '_tkinter',

        # PIL/Pillow 이미지 처리
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.ImageDraw',
        'PIL.ImageFont',

        # 필수 라이브러리
        'numpy',
        'cv2',

        # 내장 모듈 (exe에서 누락될 수 있음)
        'threading',
        'queue',
        'collections',
        'copy',
        'gc',
        'shutil',
        'logging',
        'datetime',
        'time',
        'random',
        'os',
        'json',
        'configparser',
    ],
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
    name='04.GTGEN_Tool_svms_v2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX 압축 비활성화 - 빌드 속도 향상 및 안정성 개선
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
