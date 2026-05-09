# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path


ROOT = Path.cwd()


def collect_data_tree(source_rel: str, target_rel: str):
    source = ROOT / source_rel
    if not source.exists():
        return []
    return [
        (str(path), str(Path(target_rel) / path.relative_to(source)))
        for path in source.rglob("*")
        if path.is_file()
    ]


def collect_data_tree_absolute(source: Path, target_rel: str):
    if not source.exists():
        return []
    return [
        (str(path), str(Path(target_rel) / path.relative_to(source)))
        for path in source.rglob("*")
        if path.is_file()
    ]


datas = []
datas += collect_data_tree("skills", "skills")
datas += collect_data_tree("vendor", "vendor")
datas += collect_data_tree("tool_runtime/pandoc", "tool_runtime/pandoc")
datas += collect_data_tree_absolute(
    Path(os.environ.get("TEMP", "")) / "office_local_tools" / "pandoc",
    "tool_runtime/pandoc",
)

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'config',
        'data.db',
        'api_calls',
        'knowledge',
        'skills',
        'keyring',
        'keyring.backends',
        'keyring.backends.Windows',
    ],
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
    a.binaries,
    a.datas,
    [],
    name='AI-Platform',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
