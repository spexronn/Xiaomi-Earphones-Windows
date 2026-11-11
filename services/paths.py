"""Uygulama dizinleri.

- Kaynaktan çalışırken: proje içindeki config/ ve logs/ klasörleri kullanılır.
- EXE olarak: EXE'nin yanında "portable.flag" varsa EXE klasörü (taşınabilir mod),
  yoksa %LOCALAPPDATA%\\SPEXRON\\BudsMonitor kullanılır.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "SPEXRON Buds Monitor"
APP_VERSION = "1.0.0"
DEVELOPER = "SPEXRON SOFT"
FROZEN = getattr(sys, "frozen", False)


def resource_dir() -> Path:
    """Paketlenmiş salt-okunur kaynaklar (assets)."""
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    if not FROZEN:
        base = Path(__file__).resolve().parent.parent
    else:
        exe_dir = Path(sys.executable).parent
        if (exe_dir / "portable.flag").exists():
            base = exe_dir
        else:
            base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SPEXRON" / "BudsMonitor"
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_dir() -> Path:
    p = data_dir() / "config"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def launch_command(mode: str) -> list[str]:
    """Uygulamayı belirtilen modda başlatacak komut satırı."""
    if FROZEN:
        return [sys.executable, mode]
    main = str(Path(__file__).resolve().parent.parent / "main.py")
    exe = sys.executable
    # Konsolsuz yorumlayıcı tercih edilir
    pyw = Path(exe).with_name("pythonw.exe")
    if pyw.exists():
        exe = str(pyw)
    return [exe, main, mode]
