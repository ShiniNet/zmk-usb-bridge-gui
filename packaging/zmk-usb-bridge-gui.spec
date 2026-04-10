import platform
from pathlib import Path

from PyInstaller.config import CONF


def _normalize_architecture(machine: str) -> str:
    normalized = machine.lower().replace(" ", "_")
    if normalized in {"amd64", "x86_64"}:
        return "x86_64"
    if normalized in {"arm64", "aarch64"}:
        return "arm64"
    return normalized or "unknown"


project_root = Path(SPECPATH).resolve().parent
src_root = project_root / "src"
entry_point = src_root / "zmk_usb_bridge_gui" / "__main__.py"
build_flavor = f"{platform.system().lower()}-{_normalize_architecture(platform.machine())}"
dist_root = project_root / "dist" / build_flavor
work_root = project_root / "build" / "pyinstaller" / build_flavor

dist_root.mkdir(parents=True, exist_ok=True)
work_root.mkdir(parents=True, exist_ok=True)

# Keep Linux and Windows PyInstaller artifacts isolated so cross-OS reruns do
# not try to delete incompatible files or symlinks from a previous build.
CONF["distpath"] = str(dist_root)
CONF["workpath"] = str(work_root)
CONF["warnfile"] = str(work_root / f"warn-{specnm}.txt")
CONF["dot-file"] = str(work_root / f"graph-{specnm}.dot")
CONF["xref-file"] = str(work_root / f"xref-{specnm}.html")

a = Analysis(
    [str(entry_point)],
    pathex=[str(src_root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtWidgets",
    ],
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
