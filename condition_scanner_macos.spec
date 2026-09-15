# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)
datas = [
    (str(root / "templates"), "templates"),
    (str(root / "static"), "static"),
    (str(root / ".env.example"), "."),
]

a = Analysis(
    [str(root / "desktop.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=["keyring.backends.macOS"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JudopickConditionScanner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    argv_emulation=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="JudopickConditionScanner",
)
app = BUNDLE(
    coll,
    name="주도픽 조건검색.app",
    bundle_identifier="com.judopick.conditionscanner",
    info_plist={
        "CFBundleDisplayName": "주도픽 조건검색",
        "CFBundleName": "주도픽 조건검색",
        "CFBundleShortVersionString": "0.3.0",
        "CFBundleVersion": "0.3.0",
        "LSApplicationCategoryType": "public.app-category.finance",
        "NSHighResolutionCapable": True,
    },
)
