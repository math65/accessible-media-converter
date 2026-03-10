# -*- mode: python ; coding: utf-8 -*-
import os


project_root = os.path.abspath(".")
version_file = os.environ.get("UT_VERSION_FILE") or None


a = Analysis(
    ['main.py'],
    pathex=[project_root],
    binaries=[('bin\\ffmpeg.exe', 'bin'), ('bin\\ffprobe.exe', 'bin')],
    datas=[('locales', 'locales'), ('docs', 'docs')],
    hiddenimports=['wx.richtext', 'wx._richtext', 'wx.xml', 'wx._xml'],
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
