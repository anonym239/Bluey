"""Erkennt Grafikkarte und Arbeitsspeicher und empfiehlt passende Ollama-Modelle."""
import ctypes
import json
import subprocess
import sys

# (Name, Download-Größe GB, nötiger Grafikspeicher GB, was es kann)
MODELS = [
    ("llama3.2:3b", 2.0, 3.0, "sehr schnell, einfache Antworten"),
    ("qwen3:4b", 2.6, 4.0, "gut mit Werkzeugen (klicken, tippen)"),
    ("qwen2.5vl:3b", 3.2, 4.5, "sieht Bildschirmfotos"),
    ("gemma3:4b", 3.3, 4.5, "sieht Bildschirmfotos, gutes Deutsch"),
    ("qwen3:8b", 5.2, 6.5, "klüger, gut mit Werkzeugen"),
    ("qwen2.5vl:7b", 6.0, 7.5, "sieht Bildschirmfotos, klüger"),
    ("gemma3:12b", 8.1, 10.0, "sieht Bildschirmfotos, deutlich klüger"),
    ("qwen3:14b", 9.3, 11.0, "sehr klug mit Werkzeugen"),
    ("gemma3:27b", 17.0, 20.0, "sieht Bildschirmfotos, sehr klug"),
]


class Hardware:
    def __init__(self, gpu=None, vram=None, ram=None):
        self.gpu, self.vram, self.ram = gpu, vram, ram  # vram/ram in GB

    @property
    def summary(self):
        parts = []
        if self.gpu:
            parts.append(self.gpu + (f" ({self.vram:.0f} GB Grafikspeicher)" if self.vram else ""))
        else:
            parts.append("keine NVIDIA-Grafikkarte erkannt")
        if self.ram:
            parts.append(f"{self.ram:.0f} GB Arbeitsspeicher")
        return ", ".join(parts)


def _nvidia():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=8, creationflags=0x08000000 if sys.platform == "win32" else 0)
        line = out.stdout.strip().splitlines()[0]
        name, memory = [part.strip() for part in line.split(",")[:2]]
        return name, float(memory) / 1024
    except Exception:
        return None, None


def _windows_gpu():
    """Fallback ohne nvidia-smi: Name und Speicher aus der Registry/WMI (Speicher oft ungenau)."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                              "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress"],
                             capture_output=True, text=True, timeout=15, creationflags=0x08000000)
        data = json.loads(out.stdout or "[]")
        if isinstance(data, dict):
            data = [data]
        best = max(data, key=lambda d: d.get("AdapterRAM") or 0)
        ram = (best.get("AdapterRAM") or 0) / 1024 ** 3
        return best.get("Name"), (ram if ram >= 1 else None)
    except Exception:
        return None, None


def _ram():
    if sys.platform != "win32":
        try:
            import os
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3
        except Exception:
            return None

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    try:
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return status.ullTotalPhys / 1024 ** 3
    except Exception:
        return None


_cached = None


def detect():
    global _cached
    if _cached is None:
        gpu, vram = _nvidia()
        if not gpu and sys.platform == "win32":
            gpu, vram = _windows_gpu()
        _cached = Hardware(gpu, vram, _ram())
    return _cached


def recommend(hardware):
    """Alle Modelle mit Bewertung: [(Name, Text, passt?, empfohlen?)], passende zuerst."""
    vram = hardware.vram or 0
    ram = hardware.ram or 8
    budget = vram if vram >= 3 else 0
    result = []
    for name, size, need, what in MODELS:
        if budget:
            fits = need <= budget + 0.3
            note = "passt in deine Grafikkarte" if fits else "zu groß für deine Grafikkarte (langsam)"
        else:
            fits = size * 1.5 <= ram * 0.5 and size <= 3.5
            note = "läuft auf dem Prozessor (langsamer)" if fits else "zu groß für deinen PC"
        result.append([name, f"{what} · ~{size:.1f} GB · {note}".replace(".", ","), fits, False])
    fitting = [r for r in result if r[2]]
    # Empfehlung: das größte passende Modell, das Bildschirmfotos sieht (gemma bevorzugt), sonst das größte passende.
    seeing = [r for r in fitting if "Bildschirmfotos" in r[1]]
    best = (seeing or fitting or result[:1])[-1]
    best[3] = True
    best[1] = "★ empfohlen · " + best[1]
    size = {m[0]: m[1] for m in MODELS}
    # Empfohlenes zuerst, dann passende (größte zuerst), dann zu große (kleinste zuerst).
    return sorted(result, key=lambda r: (not r[3], not r[2], -size[r[0]] if r[2] else size[r[0]]))
