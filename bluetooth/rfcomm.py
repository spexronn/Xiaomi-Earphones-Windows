"""WinRT tabanlı RFCOMM (Bluetooth Classic) soket istemcisi."""
from __future__ import annotations

import asyncio
import logging
import uuid

from winrt.windows.devices.bluetooth import BluetoothCacheMode, BluetoothDevice
from winrt.windows.devices.bluetooth.rfcomm import RfcommServiceId
from winrt.windows.networking.sockets import SocketProtectionLevel, StreamSocket
from winrt.windows.storage.streams import Buffer, InputStreamOptions

log = logging.getLogger(__name__)


class RfcommError(Exception):
    pass


class RfcommConnection:
    def __init__(self, address: int, service_uuid: str, prefer_cache: bool = True) -> None:
        self.address = address
        self.service_uuid = service_uuid
        self.prefer_cache = prefer_cache
        self._sock: StreamSocket | None = None
        self._device: BluetoothDevice | None = None

    async def open(self, timeout: float = 8.0) -> None:
        self._device = await BluetoothDevice.from_bluetooth_address_async(self.address)
        if self._device is None:
            raise RfcommError("Cihaz bulunamadı")
        sid = RfcommServiceId.from_uuid(uuid.UUID(self.service_uuid))
        # Önce Windows'un önbelleğindeki SDP kaydı (ölçülen: ~0.01 sn). Önbelleksiz SDP sorgusu
        # kapak yeni açılmışken 3–16 sn sürüp boş dönebiliyor; yalnızca önbellek boşsa ve
        # süre sınırıyla kullanılır.
        res = None
        services = []
        if self.prefer_cache:
            res = await self._device.get_rfcomm_services_for_id_async(sid, BluetoothCacheMode.CACHED)
            services = list(res.services) if res is not None else []
        if not services:
            try:
                res = await asyncio.wait_for(
                    self._device.get_rfcomm_services_for_id_async(sid, BluetoothCacheMode.UNCACHED), 6.0)
                services = list(res.services) if res is not None else []
            except asyncio.TimeoutError:
                res = None
        if not services and not self.prefer_cache:
            res = await self._device.get_rfcomm_services_for_id_async(sid, BluetoothCacheMode.CACHED)
            services = list(res.services) if res is not None else []
        if not services:
            raise RfcommError(f"RFCOMM servisi {self.service_uuid} bulunamadı (hata={res.error if res else '?'})")
        svc = services[0]
        log.debug("RFCOMM servisi: host=%s service=%s", svc.connection_host_name.raw_name, svc.connection_service_name)
        sock = StreamSocket()
        try:
            await asyncio.wait_for(
                sock.connect_async(
                    svc.connection_host_name,
                    svc.connection_service_name,
                    SocketProtectionLevel.BLUETOOTH_ENCRYPTION_ALLOW_NULL_AUTHENTICATION,
                ),
                timeout,
            )
        except Exception as e:
            sock.close()
            why = "zaman aşımı" if isinstance(e, asyncio.TimeoutError) else (str(e) or type(e).__name__)
            raise RfcommError(f"RFCOMM bağlantısı kurulamadı: {why}") from e
        self._sock = sock

    async def write(self, data: bytes) -> None:
        if not self._sock:
            raise RfcommError("Bağlı değil")
        buf = Buffer(len(data))
        buf.length = len(data)
        memoryview(buf).cast("B")[:] = data
        await self._sock.output_stream.write_async(buf)
        await self._sock.output_stream.flush_async()

    async def read(self, max_bytes: int = 1024) -> bytes:
        """Veri gelene kadar bekler (olay güdümlü, CPU harcamaz). b'' = bağlantı kapandı."""
        if not self._sock:
            raise RfcommError("Bağlı değil")
        buf = Buffer(max_bytes)
        result = await self._sock.input_stream.read_async(buf, max_bytes, InputStreamOptions.PARTIAL)
        n = result.length
        return bytes(memoryview(result)[:n]) if n else b""

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None
