"""Google Fast Pair (servis UUID 0xFE2C) BLE reklamlarından pil verisi.

REDMI Buds 8 Active ayrı bir BLE adresinden (ör. F0:B8:84:B0:63:87) Fast Pair
"keşfedilemez" reklamı yayınlar. Gerçek örnek (servis verisi, AD tür 0x16):

    2c fe | 00 | 40 61 20 0c 81 | 11 56 | 34 5a 5a ff
          ver   hesap filtresi    salt    pil: sol, sağ, kutu

Alan başlığı 0bLLLLTTTT: L = uzunluk, T = tür (0 filtre, 1 salt,
3 = pil + arayüz göster, 4 = pil + arayüz gizle). Pil baytı: bit7 şarj,
bit0-6 seviye, 0x7F = bilinmiyor.

Bu kaynak YEDEKTİR: yalnızca FD2D RFCOMM oturumu kurulamazsa ve kısa süreli
tarama ile kullanılır (sürekli tarama yapılmaz).
"""
from __future__ import annotations

import asyncio
import logging

from .discovery import matches
from .protocol import BatteryState, BatteryUnit

log = logging.getLogger(__name__)

FAST_PAIR_UUID16 = b"\x2c\xfe"


def _unit(b: int) -> BatteryUnit:
    lvl = b & 0x7F
    return BatteryUnit(None if lvl == 0x7F or lvl > 100 else lvl, bool(b & 0x80) and lvl != 0x7F)


def parse_service_data(sd: bytes) -> BatteryState | None:
    """AD tür 0x16 verisi (UUID dahil). Pil alanı yoksa None."""
    if len(sd) < 3 or sd[:2] != FAST_PAIR_UUID16:
        return None
    data = sd[2:]
    if len(data) <= 3:      # keşfedilebilir mod: yalnızca 3 baytlık model kimliği
        return None
    i = 1                   # data[0] = sürüm/bayraklar
    while i < len(data):
        ln, typ = data[i] >> 4, data[i] & 0x0F
        body = data[i + 1:i + 1 + ln]
        if typ in (3, 4) and len(body) >= 3:
            return BatteryState(_unit(body[0]), _unit(body[1]), _unit(body[2]))
        i += 1 + ln
    return None


async def scan_battery(seconds: float, name_hint: str) -> tuple[BatteryState, int] | None:
    """Kısa süreli BLE taraması; adı eşleşen cihazın Fast Pair pil verisini döndürür."""
    from winrt.windows.devices.bluetooth.advertisement import (
        BluetoothLEAdvertisementWatcher,
        BluetoothLEScanningMode,
    )
    from winrt.windows.storage.streams import DataReader

    loop = asyncio.get_running_loop()
    named: set[int] = set()
    batteries: dict[int, BatteryState] = {}
    done = asyncio.Event()

    def on_recv(_s, a):
        try:
            adv = a.advertisement
            addr = a.bluetooth_address
            if adv.local_name and matches(adv.local_name, name_hint):
                named.add(addr)
            for s in adv.data_sections:
                if s.data_type == 0x16:
                    r = DataReader.from_buffer(s.data)
                    buf = bytearray(s.data.length)
                    r.read_bytes(buf)
                    bat = parse_service_data(bytes(buf))
                    if bat:
                        batteries[addr] = bat
            if any(x in named for x in batteries):
                loop.call_soon_threadsafe(done.set)
        except Exception:
            log.debug("Reklam çözümlenemedi", exc_info=True)

    w = BluetoothLEAdvertisementWatcher()
    w.scanning_mode = BluetoothLEScanningMode.ACTIVE   # yerel ad tarama yanıtında gelir
    w.add_received(on_recv)
    try:
        w.start()
    except OSError as e:
        log.info("BLE taraması başlatılamadı: %s", e)
        return None
    try:
        await asyncio.wait_for(done.wait(), seconds)
    except asyncio.TimeoutError:
        pass
    finally:
        w.stop()
    for addr, bat in batteries.items():
        if addr in named:
            return bat, addr
    return None
