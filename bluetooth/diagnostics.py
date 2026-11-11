"""Bluetooth tanılama modülü.

Kulaklığın gerçekte hangi verileri sunduğunu kanıtlayan bir rapor üretir:
  1. Adaptör ve eşleşmiş cihaz bilgisi
  2. Windows PnP düğümleri ve Windows'un kendi (HFP) pil değeri
  3. SDP üzerinden sunulan RFCOMM servisleri
  4. Xiaomi FD2D protokol oturumu: ham paketler + çözümlenmiş TLV kayıtları,
     dinleme süresi boyunca gelen tüm bildirimler (kutu kapağı testleri için)
  5. BLE reklam taraması (Xiaomi üretici verisi 0x038F / servis verisi FD2D)
  6. BLE GATT servisleri (Battery Service 0x180F / Battery Level 0x2A19)
"""
from __future__ import annotations

import asyncio
import logging
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from services.paths import APP_NAME, APP_VERSION, logs_dir

from .buds_client import BudsSession
from .discovery import adapter_info, find_buds, format_address
from .fastpair import parse_service_data as parse_fastpair
from .protocol import (
    Message,
    MsgType,
    Opcode,
    iter_tlv,
    parse_device_info,
    parse_status_report,
)
from .windows_battery import device_nodes, hfp_battery

log = logging.getLogger(__name__)

XIAOMI_COMPANY_ID = 0x038F
KNOWN_UUIDS = {
    "0000110b": "A2DP Audio Sink", "0000110c": "AVRCP Target", "0000110e": "AVRCP Controller",
    "0000111e": "Hands-Free (HFP)", "00001124": "HID", "00001101": "Serial Port (SPP)",
    "0000fd2d": "Xiaomi özel kontrol servisi (pil protokolü)",
    "df21fe2c": "Jieli (JL_SPP) üretici servisi",
}
TLV_NAMES = {0x00: "Model adı", 0x01: "Firmware", 0x03: "VID/PID", 0x07: "Pil (sol, sağ, kutu)"}


def _bat_text(b: int) -> str:
    if b == 0xFF:
        return "bilinmiyor(0xFF)"
    return f"%{b & 0x7F}{' şarjda' if b & 0x80 else ''}"


fastpair_hits: list = []


async def _ble_scan(seconds: int, interesting: set[int], out: list[str]) -> list[int]:
    from winrt.windows.devices.bluetooth.advertisement import (
        BluetoothLEAdvertisementWatcher,
        BluetoothLEScanningMode,
    )
    from winrt.windows.storage.streams import DataReader

    def b2b(buf) -> bytes:
        r = DataReader.from_buffer(buf)
        data = bytearray(buf.length)
        r.read_bytes(data)
        return bytes(data)

    loop = asyncio.get_running_loop()
    seen: dict[tuple, int] = {}
    candidates: set[int] = set()
    total = {"n": 0}

    def on_recv(_s, a):
        total["n"] += 1
        adv = a.advertisement
        mfr = [(m.company_id, b2b(m.data)) for m in adv.manufacturer_data]
        sections = [(s.data_type, b2b(s.data)) for s in adv.data_sections]
        is_xiaomi = any(cid == XIAOMI_COMPANY_ID for cid, _ in mfr) or any(
            t == 0x16 and d[:2] == b"\x2d\xfd" for t, d in sections)
        name = adv.local_name or ""
        addr = a.bluetooth_address
        # Fast Pair (FE2C) paketleri adsızdır; aynı adresin tarama yanıtı "REDMI…" adını taşır
        if not (is_xiaomi or addr in interesting or addr in candidates or "redmi" in name.lower()):
            return
        key = (addr, tuple(mfr), tuple(sections))
        if key in seen:
            return
        seen[key] = 1
        candidates.add(addr)
        line = (f"  [{datetime.now():%H:%M:%S}] {format_address(a.bluetooth_address)} "
                f"RSSI={a.raw_signal_strength_in_dbm} ad='{name}'")
        for cid, d in mfr:
            line += f"\n      Üretici 0x{cid:04X}: {d.hex(' ')}"
        for t, d in sections:
            line += f"\n      AD tür 0x{t:02X}: {d.hex(' ')}"
            if t == 0x16:
                fp = parse_fastpair(d)
                if fp:
                    fmt = lambda u: "bilinmiyor" if u.level is None else f"%{u.level}{' şarjda' if u.charging else ''}"
                    line += (f"\n        → Google Fast Pair pil: sol {fmt(fp.left)}, sağ {fmt(fp.right)}, "
                             f"kutu {fmt(fp.case)}")
                    fastpair_hits.append(fp)
        loop.call_soon_threadsafe(out.append, line)

    w = BluetoothLEAdvertisementWatcher()
    w.scanning_mode = BluetoothLEScanningMode.ACTIVE
    w.add_received(on_recv)
    try:
        w.start()
    except OSError as e:
        out.append(f"  BLE taraması BAŞLATILAMADI: {e}")
        out.append("  → Windows bu adaptörde LE taramasına izin vermiyor (radyo LE için 'hazır değil').")
        return []
    await asyncio.sleep(seconds)
    w.stop()
    out.append(f"  Toplam alınan reklam paketi: {total['n']}, ilgili (Xiaomi/Redmi) eşleşme: {len(seen)}")
    return sorted(candidates)


async def _gatt_probe(addr: int, out: list[str]) -> None:
    from winrt.windows.devices.bluetooth import BluetoothCacheMode, BluetoothLEDevice
    try:
        dev = await asyncio.wait_for(BluetoothLEDevice.from_bluetooth_address_async(addr), 10)
    except Exception as e:
        out.append(f"  {format_address(addr)}: LE cihaz açılamadı ({e})")
        return
    if dev is None:
        out.append(f"  {format_address(addr)}: Windows'ta bu adres için LE cihaz kaydı YOK (LE eşleşmesi yok)")
        return
    try:
        res = await asyncio.wait_for(dev.get_gatt_services_with_cache_mode_async(BluetoothCacheMode.UNCACHED), 20)
        out.append(f"  {format_address(addr)}: GATT durum={res.status}, servis sayısı={len(res.services)}")
        for s in res.services:
            out.append(f"    Servis {s.uuid}")
            if str(s.uuid).startswith("0000180f"):
                cr = await s.get_characteristics_async()
                for c in cr.characteristics:
                    out.append(f"      Karakteristik {c.uuid}")
                    if str(c.uuid).startswith("00002a19"):
                        rv = await c.read_value_async()
                        out.append(f"      Battery Level okuma durumu={rv.status}")
    except Exception as e:
        out.append(f"  {format_address(addr)}: GATT sorgusu başarısız ({type(e).__name__}: {e})")
    finally:
        dev.close()


async def run_diagnostics(settings, listen_seconds: int = 30,
                          progress: Callable[[str], None] = lambda s: None,
                          live_session: BudsSession | None = None) -> tuple[str, Path]:
    out: list[str] = []
    findings: dict[str, str] = {}

    def step(title: str) -> None:
        out.append("")
        out.append(f"=== {title} ===")
        progress(title)

    out.append(f"{APP_NAME} v{APP_VERSION} — Bluetooth Tanılama Raporu")
    out.append(f"Tarih: {datetime.now():%Y-%m-%d %H:%M:%S}")
    out.append(f"Sistem: {platform.platform()} / Python {platform.python_version()}")

    step("1. Bluetooth adaptörü")
    ad = await adapter_info()
    if ad:
        out.append(f"  Ad: {ad.name}\n  Adres: {ad.address}\n  Classic: {ad.classic}  LE: {ad.low_energy}"
                   f"\n  Windows radyo durumu: {'Açık' if ad.radio_on else 'Kapalı/bilinmiyor' if ad.radio_on is not None else '?'}")
    else:
        out.append("  Adaptör bulunamadı!")

    step("2. Eşleşmiş cihaz")
    fixed = "" if settings.auto_detect else settings.device_address
    devs = await find_buds(settings.device_name_pattern, fixed)
    if not devs:
        out.append("  REDMI Buds eşleşmiş cihazlar arasında bulunamadı.")
        return _finish(out, findings)
    dev = sorted(devs, key=lambda d: not d.connected)[0]
    out.append(f"  Ad: {dev.name}\n  Adres: {dev.address_str}\n  Windows bağlantı durumu: "
               f"{'BAĞLI' if dev.connected else 'BAĞLI DEĞİL'}")

    step("3. Windows PnP düğümleri ve Windows pil değeri")
    for n in device_nodes(dev.address):
        out.append(f"  {n}")
    wb = hfp_battery(dev.address)
    out.append(f"  Windows (HFP) pil değeri: {wb if wb is not None else 'yok'}")
    out.append("  NOT: Windows yalnızca TEK birleşik değer tutar; sol/sağ/kutu ayrımı yoktur.")
    findings["windows"] = f"Windows HFP pil: {wb if wb is not None else 'yok'} (tek değer)"

    step("4. SDP / RFCOMM servisleri")
    try:
        from winrt.windows.devices.bluetooth import BluetoothCacheMode, BluetoothDevice
        bd = await BluetoothDevice.from_bluetooth_address_async(dev.address)
        if bd is None:
            raise RuntimeError("Windows cihaz nesnesini döndürmedi")
        res = await bd.get_rfcomm_services_with_cache_mode_async(
            BluetoothCacheMode.UNCACHED if dev.connected else BluetoothCacheMode.CACHED)
        for s in res.services:
            u = str(s.service_id.uuid)
            out.append(f"  {u}  {KNOWN_UUIDS.get(u[:8].lower(), '')}")
        bd.close()
    except Exception as e:
        out.append(f"  SDP sorgusu başarısız: {e}")

    step("5. Xiaomi FD2D protokol oturumu")
    peer_addr: int | None = None
    if not dev.connected:
        out.append("  Kulaklık bağlı değil → protokol testi atlandı.")
        findings["protocol"] = "Test edilemedi (bağlı değil)"
    else:
        rx: list[tuple[float, Message]] = []
        own = None
        session = live_session
        try:
            if session is None:
                own = BudsSession(dev.address, lambda s: None)
                session = own
                task = asyncio.create_task(own.run(lambda: 3600))
                for _ in range(100):
                    if own.snapshot.updated_at or task.done():
                        break
                    await asyncio.sleep(0.1)
                if task.done() and task.exception():
                    raise task.exception()  # type: ignore[misc]
            session.extra_listeners.append(lambda m: rx.append((time.time(), m)))
            await session.request_device_info()
            await session.request(Opcode.GET_DEVICE_RUN_INFO, b"\xff\xff\xff\xff")
            progress(f"Dinleniyor ({listen_seconds} sn) — kulaklıkları kutuya koyup kapağı açıp kapatın")
            out.append(f"  {listen_seconds} saniye boyunca tüm paketler dinlendi.")
            await asyncio.sleep(listen_seconds)
        except Exception as e:
            out.append(f"  Protokol oturumu BAŞARISIZ: {type(e).__name__}: {e}")
            findings["protocol"] = f"Başarısız: {e}"
        finally:
            if session is not None:
                session.extra_listeners.clear()
            if own:
                own.close()
        case_seen = False
        for ts, m in rx:
            out.append(f"  [{datetime.fromtimestamp(ts):%H:%M:%S}] RX {m}")
            if m.opcode == Opcode.GET_DEVICE_INFO and m.type == MsgType.RESPONSE:
                for tag, data in iter_tlv(m.payload):
                    extra = ""
                    if tag == 0x07 and len(data) >= 3:
                        extra = f" → sol {_bat_text(data[0])}, sağ {_bat_text(data[1])}, kutu {_bat_text(data[2])}"
                        case_seen |= data[2] != 0xFF
                    elif tag == 0x00:
                        extra = f" → '{data.decode('utf-8', 'replace')}'"
                    out.append(f"      TLV 0x{tag:02X} {TLV_NAMES.get(tag, '?'):<22} {data.hex(' ')}{extra}")
                info = parse_device_info(m.payload)
                if info.battery:
                    findings["protocol"] = "ÇALIŞIYOR — sol/sağ/kutu ayrı baytlarla raporlanıyor"
            elif m.opcode == Opcode.GET_DEVICE_RUN_INFO and m.type == MsgType.RESPONSE:
                for tag, data in iter_tlv(m.payload):
                    out.append(f"      TLV 0x{tag:02X} {data.hex(' ')}")
                    if tag == 0x07 and len(data) == 7 and data[0] == 0x01:
                        peer_addr = int.from_bytes(data[1:], "big")
                        out.append(f"        → eş/ikincil adres: {format_address(peer_addr)}")
            elif m.opcode == Opcode.REPORT_STATUS:
                b = parse_status_report(m.payload)
                if b:
                    out.append(f"      → durum bildirimi: sol {b.left.level}, sağ {b.right.level}, kutu {b.case.level}")
                    case_seen |= b.case.level is not None
        findings["case"] = ("Kutu pil değeri bu testte ALINDI" if case_seen else
                            "Kutu pil değeri bu testte 0xFF (bilinmiyor) geldi. Kulaklık kutu verisini yalnızca "
                            "en az bir kulaklık kutudayken ve kapak açıkken gönderir.")

    step("6. BLE reklam taraması (12 sn)")
    interesting = {dev.address} | ({peer_addr} if peer_addr else set())
    fastpair_hits.clear()
    candidates = await _ble_scan(12, interesting, out)
    if fastpair_hits:
        fp = fastpair_hits[-1]
        findings["ble_adv"] = (f"Google Fast Pair (0xFE2C) reklamında pil var — sol {fp.left.level}, "
                               f"sağ {fp.right.level}, kutu {fp.case.level} (yedek kaynak olarak kullanılır)")
    else:
        findings["ble_adv"] = ("Redmi BLE reklamı görüldü ama pil alanı yoktu" if candidates else
                               "Xiaomi/Redmi BLE reklam paketi görülmedi veya tarama yapılamadı")

    step("7. BLE GATT (Battery Service 0x180F)")
    for a in sorted(interesting | set(candidates)):
        await _gatt_probe(a, out)

    return _finish(out, findings)


def _finish(out: list[str], findings: dict[str, str]) -> tuple[str, Path]:
    out.append("")
    out.append("=== SONUÇ ===")
    labels = {"protocol": "Xiaomi FD2D RFCOMM protokolü", "case": "Şarj kutusu", "windows": "Windows standart pil",
              "ble_adv": "BLE reklam verisi"}
    for k, label in labels.items():
        if k in findings:
            out.append(f"  • {label}: {findings[k]}")
    text = "\n".join(out)
    path = logs_dir() / f"diagnostic_{datetime.now():%Y%m%d_%H%M%S}.txt"
    path.write_text(text, encoding="utf-8")
    log.info("Tanılama raporu yazıldı: %s", path)
    return text, path
