# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all


project_root = os.path.abspath(".")
version_file = os.environ.get("UT_VERSION_FILE") or None

# accessible_output2 charge à l'exécution des DLL de lecteurs d'écran (NVDA, JAWS…)
# depuis son dossier ; collect_all embarque ces données + sous-modules. On inclut
# aussi ses dépendances pures-Python pour fiabiliser le bundle.
_speech_datas, _speech_binaries, _speech_hidden = [], [], []
for _pkg in ('accessible_output2', 'platform_utils', 'libloader'):
    _d, _b, _h = collect_all(_pkg)
    _speech_datas += _d
    _speech_binaries += _b
    _speech_hidden += _h


a = Analysis(
    ['main.py'],
    pathex=[project_root],
    binaries=[('bin\\ffmpeg.exe', 'bin'), ('bin\\ffprobe.exe', 'bin')] + _speech_binaries,
    datas=[('locales', 'locales'), ('docs', 'docs')] + _speech_datas,
    hiddenimports=['wx.richtext', 'wx._richtext', 'wx.xml', 'wx._xml'] + _speech_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AccessibleMediaConverter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    version=version_file,
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
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AccessibleMediaConverter',
)
