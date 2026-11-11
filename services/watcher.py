"""Hafif bağlantı izleyicisi.

Qt YÜKLEMEZ, Bluetooth taraması YAPMAZ. Windows'un ConnectionStatusChanged
olayını dinler (olay güdümlü, ~%0 CPU). Kulaklık bağlandığında arayüzü (--gui)
başlatır; arayüz bağlantı kesilince kendini tamamen kapatır.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any

from bluetooth.discovery import find_buds
from services.config import Settings
from services.paths import launch_command
from services.single_instance import GUI_MUTEX, is_running

log = logging.getLogger("watcher")

RESCAN_SECONDS = 180   # eşleşme listesini yeniden oku (yerel veritabanı, radyo kullanmaz)
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


def launch_gui() -> None:
    if is_running(GUI_MUTEX):
        log.info("Arayüz zaten çalışıyor")
        return
    cmd = launch_command("--gui")
    log.info("Kulaklık bağlandı → arayüz başlatılıyor: %s", cmd)
    subprocess.Popen(cmd, close_fds=True, creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW)


class Watcher:
    def __init__(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.devices: dict[int, tuple[Any, Any]] = {}  # adres → (BluetoothDevice, token)
        self.last_connected: dict[int, bool] = {}
        self.wake = asyncio.Event()

    async def refresh_devices(self) -> None:
        from winrt.windows.devices.bluetooth import BluetoothDevice
        s = Settings.load()
        fixed = "" if s.auto_detect else s.device_address
        try:
            found = await find_buds(s.device_name_pattern, fixed, s.device_address)
        except Exception as e:
            log.warning("Cihaz listesi okunamadı: %s", e)
            return
        # Boş liste geçici bir Windows numaralandırma hatası olabilir: izlenen cihazı bırakma
        # (bırakılırsa bağlantı olayı kaçar ve arayüz 3 dakikaya kadar gecikir).
        if found:
            wanted = {d.address for d in found}
            for addr in list(self.devices):
                if addr not in wanted:
                    self._drop(addr)
        for d in found:
            if d.address in self.devices:
                continue
            bd = await BluetoothDevice.from_bluetooth_address_async(d.address)
            if bd is None:
                continue
            token = bd.add_connection_status_changed(
                lambda sender, _a, addr=d.address: self.loop.call_soon_threadsafe(self.on_change, addr))
            self.devices[d.address] = (bd, token)
            log.info("İzleniyor: %s (%s)", d.name, d.address_str)
            self.on_change(d.address, initial=True)
        if not found and not self.devices:
            log.info("İzlenecek eşleşmiş Xiaomi kulaklık yok (desen='%s')", s.device_name_pattern)

    def _drop(self, addr: int) -> None:
        bd, token = self.devices.pop(addr)
        try:
            bd.remove_connection_status_changed(token)
            bd.close()
        except Exception:
            pass

    def _connected(self, addr: int) -> bool:
        from winrt.windows.devices.bluetooth import BluetoothConnectionStatus
        bd, _ = self.devices[addr]
        try:
            return bd.connection_status == BluetoothConnectionStatus.CONNECTED
        except Exception:
            return False

    def on_change(self, addr: int, initial: bool = False) -> None:
        if addr not in self.devices:
            return
        now = self._connected(addr)
        before = self.last_connected.get(addr, False)
        self.last_connected[addr] = now
        log.info("Durum %012X: %s%s", addr, "BAĞLI" if now else "BAĞLI DEĞİL", " (ilk)" if initial else "")
        if now and (not before or initial):
            self._try_launch()
            # Yarış koruması: önceki arayüz o an kapanıyor olabilir → 10 sn sonra tekrar doğrula
            self.loop.call_later(10, self._verify, addr)

    def _verify(self, addr: int) -> None:
        if addr in self.devices and self._connected(addr) and not is_running(GUI_MUTEX):
            self._try_launch()

    @staticmethod
    def _try_launch() -> None:
        try:
            launch_gui()
        except Exception:
            log.exception("Arayüz başlatılamadı")

    async def run(self) -> None:
        from services.efficiency import enable_efficiency_mode, trim_working_set
        enable_efficiency_mode()
        while True:
            await self.refresh_devices()
            trim_working_set()
            # Güvenlik ağı: olay kaçırılırsa (radyo kapanıp açıldığında) yerel durumu oku
            for addr in list(self.devices):
                if self._connected(addr) != self.last_connected.get(addr, False):
                    self.on_change(addr)
            try:
                await asyncio.wait_for(self.wake.wait(), RESCAN_SECONDS)
            except asyncio.TimeoutError:
                pass


async def watch_forever() -> None:
    w = Watcher()
    await w.run()
