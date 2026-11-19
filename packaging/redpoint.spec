# PyInstaller spec for Windows (one-file exe), Linux (folder for the AppImage) and macOS (.app).
# Build from the repository root:  pyinstaller packaging/redpoint.spec
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
ICONS = ROOT / "build" / "icons"
APP_ID = "io.github.dawidkrynski.Redpoint"

binaries = []
if sys.platform.startswith("linux"):
    # wl-paste lets us read the PRIMARY selection on Wayland (Qt's wheel cannot).
    import shutil

    wl = os.environ.get("REDPOINT_WL_PASTE") or shutil.which("wl-paste")
    if wl:
        binaries.append((wl, "bin"))

excludes = [
    "tkinter", "unittest", "pydoc", "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtQuickWidgets",
    "PyQt6.QtPdf", "PyQt6.QtPdfWidgets", "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets",
    "PyQt6.QtBluetooth", "PyQt6.QtNfc", "PyQt6.QtPositioning", "PyQt6.QtSensors", "PyQt6.QtSerialPort",
    "PyQt6.QtSql", "PyQt6.QtTest", "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtOpenGL",
    "PyQt6.QtOpenGLWidgets", "PyQt6.QtQuick3D", "PyQt6.QtRemoteObjects", "PyQt6.QtSpatialAudio",
    "PyQt6.QtTextToSpeech", "PyQt6.QtWebChannel", "PyQt6.QtWebSockets", "PyQt6.QtSvg", "PyQt6.QtSvgWidgets",
    "PyQt6.QtXml", "PyQt6.QtPrintSupport", "PyQt6.QtStateMachine",
]  # fmt: skip

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    hiddenimports=["redpoint.hotkeys.windows", "redpoint.hotkeys.x11", "redpoint.hotkeys.portal",
                   "redpoint.hotkeys.kde", "redpoint.hotkeys.macos", "redpoint.winclip", "redpoint.macclip"],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

if sys.platform == "win32":
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="Redpoint", console=False, upx=False, icon=str(ICONS / "redpoint.ico"),
        version=str(ROOT / "build" / "version_info.txt") if (ROOT / "build" / "version_info.txt").exists() else None,
    )
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="redpoint", console=False, upx=False,
              icon=str(ICONS / ("redpoint.icns" if sys.platform == "darwin" else "redpoint.png")))
    coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="redpoint")
    if sys.platform == "darwin":
        from redpoint import __version__

        app = BUNDLE(
            coll,
            name="Redpoint.app",
            icon=str(ICONS / "redpoint.icns"),
            bundle_identifier=APP_ID,
            info_plist={
                "CFBundleShortVersionString": __version__,
                "CFBundleVersion": __version__,
                "LSUIElement": True,  # background app: no Dock icon
                "NSHighResolutionCapable": True,
            },
        )
