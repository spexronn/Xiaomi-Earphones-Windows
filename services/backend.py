"""GUI'yi kilitlemeden Bluetooth işlerini yürüten arka plan motoru.

Ayrı bir QThread içinde kendi asyncio döngüsünü çalıştırır; GUI ile yalnızca
Qt sinyalleri (thread-safe, kuyruklu) üzerinden konuşur.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import threading
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from bluetooth.buds_client import BudsSession, BudsSnapshot
from bluetooth.discovery import (
    AdapterInfo,
    PairedDevice,
    adapter_info,
    find_buds,
    format_address,
    list_paired_classic,
)
from bluetooth.windows_battery import hfp_battery, last_connected_time
from services import session_history
from services.session_history import Disconnect
from services.config import Settings

log = logging.getLogger(__name__)


@dataclass
class LinkState:
    device: PairedDevice | None = None
    acl_connected: bool = False          # Windows Bluetooth bağlantısı
    protocol_ready: bool = False          # FD2D oturumu kimlik doğrulamalı açık
    fallback_active: bool = False         # FD2D yok, veriler Fast Pair BLE reklamından
    status_text: str = "Başlatılıyor…"
    error: str | None = None
    adapter: AdapterInfo | None = None
    windows_battery: int | None = None
    last_case: tuple[int, bool, float] | None = None  # (seviye, şarj, zaman) son GERÇEK kutu verisi
    snapshot: BudsSnapshot = field(default_factory=BudsSnapshot)
    connected_since: float | None = None   # bu bağlantının başladığı an
    last_disconnect: Disconnect | None = None  # son kopma (diskten de yüklenir)
    finding: str | None = None             # "LEFT" | "RIGHT" | "BOTH" → kulaklık şu an çalıyor
    finding_until: float | None = None     # otomatik durdurma zamanı (time.time())
    find_error: str | None = None          # son bulma komutunun hatası


class Backend(QObject):
    state_changed = Signal(object)        # LinkState
    device_gone = Signal()                # bağlantı kalıcı olarak kesildi → GUI kapanmalı
    paired_list = Signal(object)          # list[PairedDevice]
    packet = Signal(str, str)             # yön, açıklama (tanılama)
    diagnostic_progress = Signal(str)
    diagnostic_done = Signal(str, str)    # rapor metni, dosya yolu

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.state = LinkState()
        self.loop: asyncio.AbstractEventLoop | None = None
        # Nesne GUI thread'inde kalır (sinyaller GUI'ye kuyruklanır); asyncio döngüsü ayrı thread'de koşar.
        self._thread = threading.Thread(target=self._run_loop, name="BluetoothBackend", daemon=True)
        self._session: BudsSession | None = None
        self._bt_device = None
        self._status_token = None
        self._wake = asyncio.Event()
        self._stopping = False
        self._gone_emitted = False
        self._last_fallback = -1e9
        self._find_timer: asyncio.Task | None = None
        self._case_timer: asyncio.Task | None = None
        self._any_in_use: bool | None = None   # en az bir kulaklık kutu dışında mı (None = bilinmiyor)
        self.allow_exit_on_disconnect = True

    # ------------------------------------------------------------ yaşam döngüsü
    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        # Uygulama kapanırken kulaklık çalıyorsa önce sustur
        if self.state.finding and self.loop and not self.loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(self._find(False, "BOTH"), self.loop).result(2)
            except Exception:
                pass
        self._stopping = True
        if self.loop and not self.loop.is_closed():
            try:
                self.loop.call_soon_threadsafe(self._shutdown)
            except RuntimeError:
                pass
        self._thread.join(4)

    def _shutdown(self) -> None:
        if self._session:
            self._session.close()
        for t in asyncio.all_tasks(self.loop):
            t.cancel()

    def _run_loop(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._main())
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Arka plan motoru çöktü")
        finally:
            self._unsubscribe()
            try:
                self.loop.close()
            except Exception:
                pass

    # ----------------------------------------------------------- GUI komutları
    def call(self, coro_fn, *args) -> None:
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(coro_fn(*args)))

    def refresh(self) -> None:
        def _do():
            if self._session:
                self._session.refresh()
            else:
                self._wake.set()
            asyncio.ensure_future(self._update_aux())
        if self.loop:
            self.loop.call_soon_threadsafe(_do)

    def settings_changed(self) -> None:
        if self.loop:
            self.loop.call_soon_threadsafe(self._on_settings_changed)

    def _on_settings_changed(self) -> None:
        # Cihaz seçimi değişmiş olabilir: oturumu yeniden kur
        dev = self.state.device
        want = self.settings.device_address if not self.settings.auto_detect else ""
        if dev and want and dev.address_str != want.upper():
            log.info("Cihaz seçimi değişti, yeniden bağlanılıyor")
            self.state.device = None
            if self._session:
                self._session.close()
        self._wake.set()

    # ------------------------------------------------------ kulaklığı bul
    def find_earbuds(self, target: str = "BOTH") -> None:
        """Kulaklıktan bulma sesi çaldır. target: LEFT | RIGHT | BOTH."""
        self.call(self._find, True, target)

    def stop_finding(self) -> None:
        self.call(self._find, False, "BOTH")

    def can_find(self) -> bool:
        return bool(self.state.acl_connected and self.state.protocol_ready)

    async def _find(self, start: bool, target: str) -> None:
        from bluetooth.protocol import FindTarget
        if self._find_timer and self._find_timer is not asyncio.current_task():
            self._find_timer.cancel()
        self._find_timer = None
        sess = self._session
        if sess is None or not sess.ready:
            self._emit(finding=None, finding_until=None,
                       find_error="Kulaklık PC'ye bağlı değil ya da protokol oturumu hazır değil" if start else None)
            return
        try:
            await sess.find_earbuds(start, FindTarget[target])
        except Exception as e:
            log.warning("Kulaklığı bul komutu gönderilemedi: %s", e)
            self._emit(finding=None, finding_until=None, find_error=str(e))
            return
        if start:
            dur = max(10, int(self.settings.find_duration))
            self._find_timer = asyncio.ensure_future(self._find_auto_stop(dur))
            self._emit(finding=target, finding_until=time.time() + dur, find_error=None)
        else:
            self._emit(finding=None, finding_until=None, find_error=None)

    async def _find_auto_stop(self, seconds: int) -> None:
        await asyncio.sleep(seconds)
        log.info("Bulma sesi %d sn sonra otomatik durduruluyor", seconds)
        await self._find(False, "BOTH")

    def request_paired_list(self) -> None:
        async def _do():
            try:
                self.paired_list.emit(await list_paired_classic())
            except Exception as e:
                log.warning("Eşleşmiş cihaz listesi alınamadı: %s", e)
                self.paired_list.emit([])
        self.call(_do)

    def run_diagnostics(self, listen_seconds: int) -> None:
        async def _do():
            from bluetooth.diagnostics import run_diagnostics
            text, path = await run_diagnostics(
                self.settings, listen_seconds, self.diagnostic_progress.emit, live_session=self._session
            )
            self.diagnostic_done.emit(text, str(path))
        self.call(_do)

    # ------------------------------------------------------------ ana döngü
    def _emit(self, **changes) -> None:
        for k, v in changes.items():
            setattr(self.state, k, v)
        if self.state.acl_connected:
            self.allow_exit_on_disconnect = True
        # GUI thread'ine kopya gönder (yarış durumlarını önler)
        self.state_changed.emit(copy.deepcopy(self.state))

    async def _main(self) -> None:
        self._emit(adapter=await adapter_info(), last_disconnect=session_history.load_last())
        backoff = 1
        fails = 0
        boot = time.monotonic()
        while not self._stopping:
            self._wake.clear()
            # Kapak yeni açıldığında Windows bağlantısı birkaç saniye gidip gelebilir ve olay
            # kaçabilir: ilk 30 sn (ve her kopmadan sonra) sık kontrol et, sonra olay bekle.
            eager = time.monotonic() - boot < 30
            dev = await self._resolve_device()
            if dev is None:
                self._emit(acl_connected=False, protocol_ready=False,
                           status_text="Eşleşmiş Xiaomi kulaklık bulunamadı")
                await self._sleep(2 if eager else 30)
                continue
            await self._subscribe(dev)
            if not self._is_connected():
                self._emit(acl_connected=False, protocol_ready=False, status_text="Kulaklık bekleniyor…")
                await self._sleep(1 if eager else 30)
                continue
            self._mark_connected()
            self._emit(acl_connected=True, status_text="Protokol oturumu açılıyor…", error=None)
            await self._update_aux()
            # Art arda iki başarısızlıktan sonra Windows SDP önbelleği yerine canlı sorgu dene
            self._session = BudsSession(dev.address, self._on_snapshot, self._on_packet,
                                        prefer_cache=fails % 2 == 0 or fails < 2)
            instant = asyncio.ensure_future(self._instant_ble()) if not self.state.protocol_ready else None
            started = time.monotonic()
            t0 = time.monotonic()
            try:
                await self._session.run(lambda: self.settings.refresh_interval)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                fails += 1
                log.warning("Oturum sona erdi (%.1f sn, deneme %d): %s", time.monotonic() - t0, fails, e)
                self._emit(protocol_ready=False, error=str(e),
                           status_text="Bağlı · protokol oturumu yeniden deneniyor…" if self._is_connected()
                           else "Bağlantı kesildi")
            finally:
                if instant and not instant.done():
                    instant.cancel()
                self._session = None
                if self.state.finding:
                    if self._find_timer:
                        self._find_timer.cancel()
                        self._find_timer = None
                    self._emit(finding=None, finding_until=None)
            if time.monotonic() - started > 60:
                backoff, fails = 1, 0
            if self._is_connected():
                if backoff >= 8:   # FD2D art arda başarısız → yedek kaynağı dene
                    await self._fastpair_fallback()
                await self._sleep(backoff)
                backoff = min(backoff * 2, 60)
            else:
                boot = time.monotonic()   # kopma sonrası yeniden bağlanmayı da hızlı yakala

    async def _instant_ble(self) -> None:
        """Telefondaki gibi anında veri: FD2D oturumu kurulurken kulaklığın BLE (Fast Pair)
        reklamından pil değerlerini oku. FD2D verisi gelince bu sonuç kullanılmaz."""
        await asyncio.sleep(0.8)          # FD2D genelde < 0.5 sn'de hazır; hazırsa tarama yapma
        if self.state.protocol_ready or self._stopping:
            return
        from bluetooth.fastpair import scan_battery
        try:
            hint = self.state.device.name if self.state.device else self.settings.device_name_pattern
            res = await scan_battery(10, hint)
        except Exception as e:
            log.debug("Anlık BLE okuması başarısız: %s", e)
            return
        if res is None or self.state.protocol_ready:
            return
        bat, addr = res
        snap = copy.deepcopy(self.state.snapshot)
        snap.battery, snap.updated_at, snap.source = bat, time.time(), "fastpair"
        log.info("Anlık (Fast Pair %s): sol=%s sağ=%s kutu=%s", format_address(addr),
                 bat.left.level, bat.right.level, bat.case.level)
        self._track_usage(bat)
        self._emit(snapshot=snap, fallback_active=True, status_text="Bağlı · protokol oturumu açılıyor…")

    async def _fastpair_fallback(self) -> None:
        if time.monotonic() - self._last_fallback < self.settings.refresh_interval:
            return
        self._last_fallback = time.monotonic()
        from bluetooth.fastpair import scan_battery
        hint = self.state.device.name if self.state.device else self.settings.device_name_pattern
        res = await scan_battery(8, hint)
        if res is None:
            log.info("Fast Pair yedek kaynağından veri alınamadı")
            return
        bat, addr = res
        snap = copy.deepcopy(self.state.snapshot)
        snap.battery, snap.updated_at, snap.source = bat, time.time(), "fastpair"
        log.info("Yedek (Fast Pair %s): sol=%s sağ=%s kutu=%s", format_address(addr),
                 bat.left.level, bat.right.level, bat.case.level)
        self._track_usage(bat)
        self._emit(snapshot=snap, fallback_active=True, status_text="Bağlı · yedek kaynak (BLE)")

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._wake.wait(), seconds)
        except asyncio.TimeoutError:
            pass
        self._wake.clear()

    async def _resolve_device(self) -> PairedDevice | None:
        if self.state.device and self._is_connected():
            return self.state.device
        fixed = "" if self.settings.auto_detect else self.settings.device_address
        try:
            found = await find_buds(self.settings.device_name_pattern, fixed, self.settings.device_address)
        except Exception as e:
            log.warning("Cihaz araması başarısız: %s", e)
            return self.state.device
        if not found:
            return self.state.device
        found.sort(key=lambda d: not d.connected)  # bağlı olan önce
        dev = found[0]
        if self.state.device and self.state.device.address == dev.address:
            self.state.device = dev
            return dev
        if self.state.device and not dev.connected:
            return self.state.device
        if self.state.device and self.state.device.address != dev.address:
            log.info("Aktif Xiaomi kulaklık değişti: %s (%s)", dev.name, dev.address_str)
            self._unsubscribe()
            self.state.snapshot = BudsSnapshot()
            self.state.last_case = None
            self.state.error = None
        else:
            log.info("Cihaz: %s (%s)", dev.name, dev.address_str)
        if self.settings.auto_detect and self.settings.device_address != dev.address_str:
            self.settings.device_address = dev.address_str
            try:
                self.settings.save()
            except Exception:
                pass
        self.state.device = dev
        return dev

    # ------------------------------------------------- Windows bağlantı olayı
    async def _subscribe(self, dev: PairedDevice) -> None:
        if self._bt_device is not None and self._bt_device.bluetooth_address == dev.address:
            return
        self._unsubscribe()
        from winrt.windows.devices.bluetooth import BluetoothDevice
        self._bt_device = await BluetoothDevice.from_bluetooth_address_async(dev.address)
        if self._bt_device is None:
            return
        loop = asyncio.get_running_loop()

        def on_change(sender, _args):
            loop.call_soon_threadsafe(self._on_acl_change)
        self._status_token = self._bt_device.add_connection_status_changed(on_change)

    def _unsubscribe(self) -> None:
        if self._bt_device is not None:
            try:
                if self._status_token is not None:
                    self._bt_device.remove_connection_status_changed(self._status_token)
                self._bt_device.close()
            except Exception:
                pass
        self._bt_device = None
        self._status_token = None

    def _is_connected(self) -> bool:
        from winrt.windows.devices.bluetooth import BluetoothConnectionStatus
        try:
            return self._bt_device is not None and \
                self._bt_device.connection_status == BluetoothConnectionStatus.CONNECTED
        except Exception:
            return False

    def _on_acl_change(self) -> None:
        connected = self._is_connected()
        log.info("Windows bağlantı durumu: %s", "BAĞLI" if connected else "KESİLDİ")
        if connected:
            self._gone_emitted = False
            self._any_in_use = None
            self.state.connected_since = None   # yeni bağlantı
            self._mark_connected()
            self._emit(acl_connected=True, status_text="Bağlandı")
            self._wake.set()
        else:
            if self._session:
                self._session.close()
            disc = self._make_disconnect(radio_off=False)
            self._emit(acl_connected=False, protocol_ready=False, fallback_active=False,
                       status_text="Bağlantı kesildi", last_disconnect=disc, connected_since=None)
            asyncio.ensure_future(self._confirm_gone(disc))

    # ------------------------------------------------- bağlantı süresi / kopma
    def _mark_connected(self) -> None:
        if self.state.connected_since is not None or not self.state.device:
            return
        if self._any_in_use is False:      # iki kulaklık da kutuda → süre işlemez
            return
        now = time.time()
        t = last_connected_time(self.state.device.address)
        # Windows zamanını yalnızca son kopmadan SONRAysa kullan (aksi halde eski, bayat kayıt)
        last = self.state.last_disconnect.time if self.state.last_disconnect else 0
        self.state.connected_since = t if t and max(last, now - 7 * 86400) < t <= now + 5 else now

    def _make_disconnect(self, radio_off: bool) -> Disconnect | None:
        since = self.state.connected_since
        if since is None:
            return self.state.last_disconnect
        snap = self.state.snapshot
        live = bool(snap.updated_at and time.time() - snap.updated_at < 600)
        reason, detail = session_history.infer_reason(snap.battery, live, radio_off)
        return Disconnect(time=time.time(), connected_at=since, reason=reason, detail=detail)

    async def _confirm_gone(self, disc: Disconnect | None = None) -> None:
        await asyncio.sleep(max(1, self.settings.disconnect_grace))
        if self._is_connected():
            return
        if disc is not None:
            ad = await adapter_info()
            if ad is None or ad.radio_on is False:   # adaptör çıkarıldı / Bluetooth kapatıldı
                disc.reason, disc.detail = session_history.REASON_RADIO, ""
            session_history.save_last(disc)
            self._emit(last_disconnect=disc)
            log.info("Kopma kaydedildi: %s (%s) · %d sn bağlı kaldı", disc.reason_text, disc.detail, disc.duration)
        if not self._gone_emitted and self.allow_exit_on_disconnect:
            self._gone_emitted = True
            log.info("Kulaklık %ss boyunca bağlı değil → uygulama kapanıyor", self.settings.disconnect_grace)
            self.device_gone.emit()

    # --------------------------------------------------------- veri geri çağrıları
    def _on_snapshot(self, snap: BudsSnapshot) -> None:
        case = snap.battery.case
        last_case = self.state.last_case
        if case.level is not None and snap.updated_at:
            last_case = (case.level, case.charging, snap.updated_at)
        b = snap.battery
        log.info("Pil: sol=%s%s sağ=%s%s kutu=%s%s (%s)",
                 b.left.level, "⚡" if b.left.charging else "", b.right.level, "⚡" if b.right.charging else "",
                 b.case.level, "⚡" if b.case.charging else "", snap.source)
        self._track_usage(b)
        self._emit(snapshot=snap, protocol_ready=True, fallback_active=False, last_case=last_case, error=None,
                   status_text="Bağlı")

    def _track_usage(self, battery) -> None:
        """Kapak açıkken bağlantı kopmasa da: hiçbir kulaklık kulakta değilse (birkaç saniye
        kesinleşince) oturumu bitir, biri çıkınca yeni oturum başlat."""
        use = session_history.buds_in_use(battery)
        if use is None:
            return
        cur, prev = any(use), self._any_in_use
        self._any_in_use = cur
        if cur:
            if self._case_timer and not self._case_timer.done():
                self._case_timer.cancel()        # anlık sapma: oturum sürüyor
                self._case_timer = None
                return
            if prev is False:
                self.state.connected_since = time.time()
                log.info("Kulaklık kutudan çıktı → yeni oturum")
            elif self.state.connected_since is None and self.state.acl_connected:
                self._mark_connected()
            return
        if prev is None:                         # açılışta zaten kutudaydı
            self.state.connected_since = None
        elif prev and self.state.connected_since is not None:
            self._case_timer = asyncio.ensure_future(self._end_session_in_case(time.time()))

    async def _end_session_in_case(self, at: float) -> None:
        await asyncio.sleep(8)
        if self._any_in_use is not False or self.state.connected_since is None:
            return
        disc = Disconnect(time=at, connected_at=self.state.connected_since,
                          reason=session_history.REASON_CASE,
                          detail=session_history.usage_text(self.state.snapshot.battery).lower())
        session_history.save_last(disc)
        log.info("Kulakta kulaklık yok → oturum bitti (%d sn)", disc.duration)
        self._emit(connected_since=None, last_disconnect=disc)

    def _on_packet(self, direction: str, msg, raw: bytes) -> None:
        if self.settings.diagnostic_mode:
            self.packet.emit(direction, f"{raw.hex(' ')}  {msg}")

    async def _update_aux(self) -> None:
        dev = self.state.device
        if dev:
            self._emit(windows_battery=hfp_battery(dev.address))


def describe_address(addr: int) -> str:
    return format_address(addr)
