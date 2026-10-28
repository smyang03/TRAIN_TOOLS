# -*- mode: python ; coding: utf-8 -*-
import sys
sys.setrecursionlimit(100000)

excludes = [
    'tensorflow', 'tensorflow.python', 'tensorflow.compat', 'keras',
    'torch', 'torchvision', 'torchaudio',
    'scipy', 'scipy.special', 'scipy.linalg', 'scipy.sparse',
    'sympy', 'sympy.core',
    'matplotlib', 'matplotlib.backends', 'matplotlib.pyplot',
    'pandas', 'pandas.plotting', 'pandas.io',
    'IPython', 'jupyter', 'notebook', 'nbconvert', 'nbformat',
    'sklearn', 'scikit-learn',
    'sphinx', 'pytest', 'docutils',
    'babel', 'jinja2', 'lxml', 'openpyxl', 'pyarrow',
    'botocore', 'boto3', 's3transfer',
    'cryptography', 'argon2',
    'PyQt5', 'qtpy',
    'win32com', 'pywintypes', 'pythoncom',
    'zmq', 'cloudpickle', 'jsonschema', 'expecttest',
]

a = Analysis(
    ['label_check/main.py'],
    pathex=['label_check'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'tkinter', 'tkinter.ttk', 'tkinter.filedialog', '_tkinter',
        'PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL.ImageDraw', 'PIL.ImageFont',
        'numpy', 'psutil',
        'utils', 'data_manager', 'label_operations', 'image_processor', 'ui_manager',
        'threading', 'queue', 'collections', 'copy', 'gc', 'shutil',
        'logging', 'datetime', 'time', 'random', 'os',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='06.label_check',
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
)
