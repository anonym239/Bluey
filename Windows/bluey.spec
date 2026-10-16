# PyInstaller-Rezept für Bluey.exe (Ordner-Variante: startet schneller als eine Einzeldatei).
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [("bluey/assets", "bluey/assets")]
binaries = []
hiddenimports = collect_submodules("bluey") + collect_submodules("keyring.backends") + collect_submodules("winrt")
for package in ("faster_whisper", "ctranslate2", "uiautomation", "onnxruntime", "tokenizers", "av"):
    try:
        d, b, h = collect_all(package)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(["launcher.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=["tkinter", "matplotlib", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtQuick",
                       "PySide6.QtQml", "PySide6.QtPdf", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Bluey", icon="bluey.ico", console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Bluey", upx=False)
