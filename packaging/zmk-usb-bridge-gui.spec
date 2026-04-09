from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
src_root = project_root / "src"
entry_point = src_root / "zmk_usb_bridge_gui" / "__main__.py"

a = Analysis(
    [str(entry_point)],
    pathex=[str(src_root)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="zmk-usb-bridge-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="zmk-usb-bridge-gui",
)
