"""Windows verimlilik yardımcıları (izleyici süreci için)."""
from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger(__name__)

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.GetCurrentProcess.restype = wintypes.HANDLE
_k32.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
_k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_k32.SetProcessWorkingSetSize.argtypes = [wintypes.HANDLE, ctypes.c_size_t, ctypes.c_size_t]
ProcessPowerThrottling = 4
PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
IDLE_PRIORITY_CLASS = 0x40
NORMAL_PRIORITY_CLASS = 0x20


class _PPTS(ctypes.Structure):
    _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]


def enable_efficiency_mode() -> None:
    """Windows 11 'Verimlilik modu' (EcoQoS) + düşük öncelik. Windows 10'da sessizce yok sayılır."""
    h = _k32.GetCurrentProcess()
    try:
        st = _PPTS(PROCESS_POWER_THROTTLING_CURRENT_VERSION, PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
                   PROCESS_POWER_THROTTLING_EXECUTION_SPEED)
        _k32.SetProcessInformation(h, ProcessPowerThrottling, ctypes.byref(st), ctypes.sizeof(st))
        _k32.SetPriorityClass(h, IDLE_PRIORITY_CLASS)
    except Exception as e:
        log.debug("Verimlilik modu ayarlanamadı: %s", e)


def normal_priority() -> None:
    """Arayüz süreci izleyicinin düşük önceliğini miras alır; akıcı arayüz için normale döndür."""
    try:
        h = _k32.GetCurrentProcess()
        st = _PPTS(PROCESS_POWER_THROTTLING_CURRENT_VERSION, PROCESS_POWER_THROTTLING_EXECUTION_SPEED, 0)
        _k32.SetProcessInformation(h, ProcessPowerThrottling, ctypes.byref(st), ctypes.sizeof(st))
        _k32.SetPriorityClass(h, NORMAL_PRIORITY_CLASS)
    except Exception:
        pass


def trim_working_set() -> None:
    """Başlangıçta yüklenen ve artık kullanılmayan sayfaları RAM'den bırak."""
    try:
        mx = ctypes.c_size_t(-1).value
        _k32.SetProcessWorkingSetSize(_k32.GetCurrentProcess(), mx, mx)
    except Exception:
        pass
