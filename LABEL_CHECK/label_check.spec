# -*- mode: python ; coding: utf-8 -*-
import sys
sys.setrecursionlimit(100000)

block_cipher = None

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
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'tkinter', 'tkinter.ttk', 'tkinter.filedialog', '_tkinter',
        'PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL.ImageDraw', 'PIL.ImageFont',
        'numpy', 'tqdm', 'psutil',
        'utils', 'data_manager', 'label_operations', 'image_processor', 'ui_manager',
        'threading', 'queue', 'collections', 'copy', 'gc', 'shutil',
        'logging', 'datetime', 'time', 'random', 'os',
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
    name='label_check',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
