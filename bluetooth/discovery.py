"""Eşleşmiş Bluetooth cihazlarını ve adaptörü sorgular.

Bu sorgular yalnızca Windows'un yerel cihaz veritabanını okur; radyo taraması
(inquiry/scan) YAPMAZ, bu yüzden pil ve CPU maliyeti yoktur.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass

from .protocol import SERVICE_UUID

log = logging.getLogger(__name__)

AUTO_PATTERNS = {"", "auto", "xiaomi", "xiaomi_auto"}

_XIAOMI_BRAND_RE = re.compile(r"\b(xiaomi|redmi|poco|mi)\b", re.IGNORECASE)
_XIAOMI_SOLO_MODEL_RE = re.compile(r"\b(airdots\w*|flipbuds\w*|openwear\w*)\b", re.IGNORECASE)
_AUDIO_WORD_RE = re.compile(
    r"\b(buds\w*|pods\w*|airdots\w*|earbuds?\w*|earphones?\w*|headphones?\w*|"
    r"headsets?\w*|flipbuds\w*|openwear\w*|tws|stereo|neckband|air\s*\d\w*|air\s*se|basic\w*|audio)\b",
    re.IGNORECASE,
)
_NON_AUDIO_RE = re.compile(
    r"\b(watch|band|smart\s*band|note|pad|tablet|phone|laptop|notebook|tv|projector|scale|vacuum|scooter|cam)\b",
    re.IGNORECASE,
)


def _winrt():
    from winrt.windows.devices.bluetooth import (
        BluetoothAdapter,
        BluetoothCacheMode,
        BluetoothConnectionStatus,
        BluetoothDevice,
    )
    from winrt.windows.devices.bluetooth.rfcomm import RfcommServiceId
    from winrt.windows.devices.enumeration import DeviceInformation
    return BluetoothAdapter, BluetoothCacheMode, BluetoothConnectionStatus, BluetoothDevice, RfcommServiceId, DeviceInformation


@dataclass
class PairedDevice:
    name: str
    address: int
    connected: bool
    device_id: str

    @property
    def address_str(self) -> str:
        return format_address(self.address)


@dataclass
class AdapterInfo:
    name: str
    address: str
    classic: bool
    low_energy: bool
    radio_on: bool | None


def format_address(addr: int) -> str:
    return ":".join(f"{(addr >> (8 * i)) & 0xFF:02X}" for i in range(5, -1, -1))


def parse_address(text: str) -> int:
    return int(text.replace(":", "").replace("-", ""), 16)


async def list_paired_classic() -> list[PairedDevice]:
    _ad, _cm, bcs, bd_cls, _rid, di_cls = _winrt()
    selector = bd_cls.get_device_selector_from_pairing_state(True)
    infos = await di_cls.find_all_async_aqs_filter(selector)
    out: list[PairedDevice] = []
    for info in infos:
        try:
            dev = await bd_cls.from_id_async(info.id)
            if dev is None:
                continue
            out.append(PairedDevice(
                name=dev.name or info.name,
                address=dev.bluetooth_address,
                connected=dev.connection_status == bcs.CONNECTED,
                device_id=info.id,
            ))
            dev.close()
        except Exception as e:
            log.debug("Cihaz okunamadı %s: %s", info.name, e)
    return out


def is_xiaomi_audio_name(name: str) -> bool:
    """Xiaomi / Redmi / POCO / Mi marka Bluetooth kulaklık adlarını tanır (telefon/saatleri hariç tutar)."""
    norm = re.sub(r"[_\-.]+", " ", name or "").strip().lower()
    if not norm or _NON_AUDIO_RE.search(norm):
        return False
    if _XIAOMI_SOLO_MODEL_RE.search(norm):
        return True
    return bool(_XIAOMI_BRAND_RE.search(norm) and _AUDIO_WORD_RE.search(norm))


def matches(name: str, pattern: str) -> bool:
    pat = (pattern or "").strip().lower()
    if pat in AUTO_PATTERNS:
        return is_xiaomi_audio_name(name)
    norm = (name or "").lower()
    tokens = [t.strip() for t in re.split(r"[,|;]+", pat) if t.strip()]
    return any(tok in norm for tok in tokens)


async def device_by_address(text: str) -> PairedDevice | None:
    """Eşleşmiş cihazı doğrudan adresinden açar (numaralandırma boş dönse bile çalışır)."""
    _ad, _cm, bcs, bd_cls, _rid, _di = _winrt()
    try:
        addr = parse_address(text)
    except ValueError:
        return None
    try:
        dev = await bd_cls.from_bluetooth_address_async(addr)
    except Exception:
        return None
    if dev is None:
        return None
    try:
        if not dev.device_information.pairing.is_paired:
            return None
        return PairedDevice(dev.name or text, addr, dev.connection_status == bcs.CONNECTED, dev.device_id)
    finally:
        dev.close()


async def has_fd2d_service_cached(address: int) -> bool:
    """Yeniden adlandırılmış bağlı bir kulaklıkta önbellekli Xiaomi FD2D servisi var mı kontrol eder."""
    _ad, cm, _bcs, bd_cls, rid, _di = _winrt()
    try:
        dev = await bd_cls.from_bluetooth_address_async(address)
    except Exception:
        return False
    if dev is None:
        return False
    try:
        sid = rid.from_uuid(uuid.UUID(SERVICE_UUID))
        res = await dev.get_rfcomm_services_for_id_async(sid, cm.CACHED)
        return bool(res is not None and len(list(res.services)) > 0)
    except Exception:
        return False
    finally:
        dev.close()


async def find_buds(pattern: str, fixed_address: str = "", known_address: str = "") -> list[PairedDevice]:
    """Eşleşmiş Xiaomi Bluetooth kulaklıkları bulur (bağlı olanlar önceliklidir)."""
    devices = await list_paired_classic()
    if fixed_address:
        try:
            a = parse_address(fixed_address)
            found = [d for d in devices if d.address == a]
            if not found:
                d = await device_by_address(fixed_address)
                found = [d] if d else []
            return found
        except ValueError:
            log.warning("Geçersiz cihaz adresi: %s", fixed_address)

    found = [d for d in devices if matches(d.name, pattern)]
    if (pattern or "").strip().lower() in AUTO_PATTERNS:
        seen = {d.address for d in found}
        for d in devices:
            if d.connected and d.address not in seen and not _NON_AUDIO_RE.search(d.name or ""):
                if await has_fd2d_service_cached(d.address):
                    log.info("FD2D protokolüyle Xiaomi kulaklık algılandı: %s (%s)", d.name, d.address_str)
                    found.append(d)
                    seen.add(d.address)

    if not found and known_address:
        d = await device_by_address(known_address)
        if d:
            log.info("Numaralandırma boş döndü; kayıtlı adres kullanılıyor: %s", d.address_str)
            found = [d]
    found.sort(key=lambda d: not d.connected)
    return found


async def adapter_info() -> AdapterInfo | None:
    ad_cls, _cm, _bcs, _bd, _rid, di_cls = _winrt()
    try:
        ad = await ad_cls.get_default_async()
        if ad is None:
            return None
        name = "Bluetooth adaptörü"
        try:
            di = await di_cls.create_from_id_async(ad.device_id)
            name = di.name or name
        except Exception:
            pass
        radio_on = None
        try:
            from winrt.windows.devices.radios import RadioState
            radio = await ad.get_radio_async()
            radio_on = radio.state == RadioState.ON if radio else None
        except Exception:
            pass
        return AdapterInfo(name, format_address(ad.bluetooth_address), ad.is_classic_supported,
                           ad.is_low_energy_supported, radio_on)
    except Exception as e:
        log.warning("Adaptör bilgisi alınamadı: %s", e)
        return None
