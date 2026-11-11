"""Windows oturum açılışında izleyiciyi başlatma (HKCU\\...\\Run, yönetici gerektirmez)."""
from __future__ import annotations

import logging
import subprocess
import winreg

from .paths import launch_command

log = logging.getLogger(__name__)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "SPEXRON Buds Monitor"


def _command() -> str:
    return subprocess.list2cmdline(launch_command("--watch"))


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            val, _ = winreg.QueryValueEx(k, VALUE_NAME)
            return bool(val)
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ, _command())
            log.info("Başlangıçta çalıştır: AÇIK (%s)", _command())
        else:
            try:
                winreg.DeleteValue(k, VALUE_NAME)
            except FileNotFoundError:
                pass
            log.info("Başlangıçta çalıştır: KAPALI")


def sync(enabled: bool) -> None:
    """Kayıt defterini ayarla eşitle (EXE taşındıysa yolu da günceller)."""
    try:
        if enabled:
            set_enabled(True)
        elif is_enabled():
            set_enabled(False)
    except OSError as e:
        log.warning("Başlangıç kaydı güncellenemedi: %s", e)
