"""Win32 adlandırılmış mutex ile tek örnek kontrolü (Qt gerektirmez)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateMutexW.restype = wintypes.HANDLE
_k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_k32.OpenMutexW.restype = wintypes.HANDLE
_k32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
ERROR_ALREADY_EXISTS = 183
SYNCHRONIZE = 0x00100000

WATCHER_MUTEX = "Local\\SPEXRON_BudsMonitor_Watcher"
GUI_MUTEX = "Local\\SPEXRON_BudsMonitor_GUI"
GUI_SERVER_NAME = "SPEXRON_BudsMonitor_GUI_Channel"


class InstanceLock:
    def __init__(self, name: str) -> None:
        self.name = name
        self.handle = None

    def acquire(self) -> bool:
        h = _k32.CreateMutexW(None, False, self.name)
        if not h:
            return False
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            _k32.CloseHandle(h)
            return False
        self.handle = h
        return True

    def release(self) -> None:
        if self.handle:
            _k32.CloseHandle(self.handle)
            self.handle = None


def is_running(name: str) -> bool:
    h = _k32.OpenMutexW(SYNCHRONIZE, False, name)
    if h:
        _k32.CloseHandle(h)
        return True
    return False
