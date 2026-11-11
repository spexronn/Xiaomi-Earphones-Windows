"""Windows'un kendi Bluetooth pil göstergesini okur (karşılaştırma/tanılama için).

Windows, HFP (Hands-Free, UUID 0x111E) düğümüne kulaklığın AT+IPHONEACCEV / AT+BIEV
ile bildirdiği TEK bir pil değerini yazar:
DEVPKEY {104EA319-6EE2-4701-BD47-8DDBF425BBE5} pid 2. Sol/sağ/kutu ayrımı yoktur.
"""
from __future__ import annotations

import ctypes
import logging
import uuid
from ctypes import wintypes

log = logging.getLogger(__name__)

_cfg = ctypes.WinDLL("cfgmgr32")
CR_SUCCESS = 0
CM_GETIDLIST_FILTER_ENUMERATOR = 0x1


class DEVPROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", ctypes.c_byte * 16), ("pid", wintypes.ULONG)]


def _key(fmtid: str, pid: int) -> DEVPROPKEY:
    k = DEVPROPKEY()
    ctypes.memmove(k.fmtid, uuid.UUID(fmtid).bytes_le, 16)
    k.pid = pid
    return k


BATTERY_KEY = _key("{104EA319-6EE2-4701-BD47-8DDBF425BBE5}", 2)


def _device_ids(enumerator: str) -> list[str]:
    size = wintypes.ULONG()
    if _cfg.CM_Get_Device_ID_List_SizeW(ctypes.byref(size), enumerator, CM_GETIDLIST_FILTER_ENUMERATOR) != CR_SUCCESS:
        return []
    buf = ctypes.create_unicode_buffer(size.value)
    if _cfg.CM_Get_Device_ID_ListW(enumerator, buf, size.value, CM_GETIDLIST_FILTER_ENUMERATOR) != CR_SUCCESS:
        return []
    return [s for s in ctypes.wstring_at(ctypes.addressof(buf), size.value).split("\0") if s]


def _get_prop(instance_id: str, key: DEVPROPKEY) -> bytes | None:
    devinst = wintypes.DWORD()
    if _cfg.CM_Locate_DevNodeW(ctypes.byref(devinst), instance_id, 0) != CR_SUCCESS:
        return None
    ptype = wintypes.ULONG()
    size = wintypes.ULONG(0)
    _cfg.CM_Get_DevNode_PropertyW(devinst, ctypes.byref(key), ctypes.byref(ptype), None, ctypes.byref(size), 0)
    if size.value == 0:
        return None
    buf = (ctypes.c_ubyte * size.value)()
    if _cfg.CM_Get_DevNode_PropertyW(devinst, ctypes.byref(key), ctypes.byref(ptype), buf, ctypes.byref(size), 0) != CR_SUCCESS:
        return None
    return bytes(buf)


def device_nodes(address: int) -> list[str]:
    mac = f"{address:012X}"
    return [i for i in _device_ids("BTHENUM") if mac in i.upper()]


LAST_ARRIVAL_KEY = _key("{83DA6326-97A6-4088-9453-A1923F573B29}", 102)  # DEVPKEY_Device_LastArrivalDate


def last_connected_time(address: int) -> float | None:
    """Windows'un kaydettiği son bağlanma anı (Unix zamanı); yoksa None."""
    try:
        for inst in device_nodes(address):
            if "\\DEV_" in inst.upper():
                raw = _get_prop(inst, LAST_ARRIVAL_KEY)
                if raw and len(raw) >= 8:
                    ft = int.from_bytes(raw[:8], "little")      # FILETIME: 1601'den beri 100 ns
                    return ft / 10_000_000 - 11_644_473_600
    except Exception as e:
        log.debug("Bağlanma zamanı okunamadı: %s", e)
    return None


def hfp_battery(address: int) -> int | None:
    """Windows'un gösterdiği birleşik pil yüzdesi; yoksa None."""
    try:
        for inst in device_nodes(address):
            if "{0000111E" in inst.upper():
                raw = _get_prop(inst, BATTERY_KEY)
                if raw:
                    return raw[0]
    except Exception as e:
        log.debug("HFP pil okunamadı: %s", e)
    return None
