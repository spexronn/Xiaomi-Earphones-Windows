"""SPEXRON Buds Monitor — giriş noktası.

Modlar:
  (argümansız)  İzleyiciyi arka planda başlatır ve arayüzü pencereyle açar.
  --watch       Hafif bağlantı izleyicisi (Qt yok). Windows başlangıcında bu çalışır.
  --gui         Kulaklık bağlanınca izleyicinin başlattığı tepsi arayüzü.
  --diagnose    Tanılama raporu üretir (logs/diagnostic_*.txt) ve açar.
  --stop        Çalışan izleyiciyi durdurur (kaldırma öncesi).
  --find [left|right|both]  Bağlı kulaklıktan bulma sesi çaldırır (çalışan arayüz üzerinden).
  --stop-find   Bulma sesini durdurur.

SPEXRON SOFT
"""
from __future__ import annotations

import sys


def _start_watcher_detached() -> None:
    import subprocess
    from services.paths import launch_command
    from services.single_instance import WATCHER_MUTEX, is_running
    if not is_running(WATCHER_MUTEX):
        subprocess.Popen(launch_command("--watch"), close_fds=True, creationflags=0x00000008 | 0x08000000)


def mode_watch() -> int:
    import asyncio
    import logging
    from services.logging_setup import setup_logging
    from services.single_instance import WATCHER_MUTEX, InstanceLock
    setup_logging("watcher")
    lock = InstanceLock(WATCHER_MUTEX)
    if not lock.acquire():
        return 0
    log = logging.getLogger("watcher")
    log.info("İzleyici başladı")
    from services.watcher import watch_forever
    while True:
        try:
            asyncio.run(watch_forever())
        except KeyboardInterrupt:
            return 0
        except Exception:
            log.exception("İzleyici hatası, 15 sn sonra yeniden başlatılıyor")
            import time
            time.sleep(15)


def mode_gui(show_window: bool) -> int:
    from services.config import Settings
    from services.logging_setup import setup_logging
    setup_logging("gui", Settings.load().diagnostic_mode)
    from ui.app import run_gui
    return run_gui(show_window)


def mode_diagnose() -> int:
    import asyncio
    import os
    from services.config import Settings
    from services.logging_setup import setup_logging
    setup_logging("diagnose", True)
    from bluetooth.diagnostics import run_diagnostics
    text, path = asyncio.run(run_diagnostics(Settings.load(), 30, lambda m: print("»", m, flush=True)))
    try:
        print(text)
    except UnicodeEncodeError:
        pass
    print(f"\nRapor: {path}")
    if getattr(sys, "frozen", False):
        os.startfile(path)
    return 0


def mode_stop() -> int:
    import subprocess
    # İzleyici kendi exe/yorumlayıcı adıyla çalışır; komut satırında --watch olanları sonlandır
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*--watch*' -and "
          "($_.CommandLine -like '*SPEXRON*' -or $_.CommandLine -like '*main.py*') } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=0x08000000)
    return 0


def mode_find(args: list[str]) -> int:
    """Çalışan tepsi arayüzüne 'kulaklığı bul' komutu iletir (RFCOMM oturumu orada açık)."""
    from PySide6.QtCore import QCoreApplication
    from ui.app import notify_running_instance
    _app = QCoreApplication(sys.argv)  # noqa: F841  (QLocalSocket için)
    if "--stop-find" in args:
        msg = b"stopfind"
    else:
        i = args.index("--find")
        target = args[i + 1].lower() if i + 1 < len(args) else "both"
        msg = b"find:" + {"left": b"LEFT", "sol": b"LEFT", "right": b"RIGHT", "sag": b"RIGHT",
                          "sağ": b"RIGHT"}.get(target, b"BOTH")
    if notify_running_instance(msg):
        return 0
    print("Arayüz çalışmıyor: kulaklık bu PC'ye bağlı değil.", file=sys.stderr)
    return 1


def main() -> int:
    args = sys.argv[1:]
    if "--find" in args or "--stop-find" in args:
        return mode_find(args)
    if "--watch" in args:
        return mode_watch()
    if "--gui" in args:
        return mode_gui(show_window=False)
    if "--diagnose" in args:
        return mode_diagnose()
    if "--stop" in args:
        return mode_stop()
    # Kullanıcı elle açtı: izleyiciyi garanti et + pencereyi göster
    try:
        _start_watcher_detached()
    except Exception:
        pass
    return mode_gui(show_window=True)


if __name__ == "__main__":
    sys.exit(main())
