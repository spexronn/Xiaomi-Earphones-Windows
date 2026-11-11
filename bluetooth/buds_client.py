"""REDMI Buds kontrol oturumu: bağlan → kimlik doğrula → bilgi al → bildirimleri dinle."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from .protocol import (
    SERVICE_UUID,
    BatteryState,
    FrameParser,
    FindTarget,
    Message,
    MsgType,
    Opcode,
    compute_challenge_response,
    find_earbuds_payload,
    is_request,
    parse_device_info,
    parse_status_report,
    random_challenge,
)
from .rfcomm import RfcommConnection, RfcommError

log = logging.getLogger(__name__)
raw_log = logging.getLogger("bluetooth.raw")


class SessionError(Exception):
    pass


@dataclass
class BudsSnapshot:
    model: str | None = None
    firmware: str | None = None
    vid_pid: str | None = None
    battery: BatteryState = field(default_factory=BatteryState)
    updated_at: float | None = None
    source: str = ""   # "device_info" | "status_report"


class BudsSession:
    """Tek bir RFCOMM oturumu. run() bağlantı kopana kadar döner."""

    AUTH_TIMEOUT = 10.0
    INFO_TIMEOUT = 8.0

    def __init__(
        self,
        address: int,
        on_update: Callable[[BudsSnapshot], None],
        packet_tap: Callable[[str, Message, bytes], None] | None = None,
        prefer_cache: bool = True,
    ) -> None:
        self.address = address
        self.prefer_cache = prefer_cache
        self.on_update = on_update
        self.packet_tap = packet_tap
        self.snapshot = BudsSnapshot()
        self._conn: RfcommConnection | None = None
        self._seq = 0
        self._parser = FrameParser()
        self._authed = asyncio.Event()
        self._info = asyncio.Event()
        self._refresh_now = asyncio.Event()
        self._closed = False
        self.extra_listeners: list[Callable[[Message], None]] = []

    # ------------------------------------------------------------------ I/O
    def _next_seq(self) -> int:
        s = self._seq
        self._seq = (self._seq + 1) & 0xFF
        return s

    async def send(self, msg: Message) -> None:
        data = msg.encode()
        raw_log.debug("TX %s | %s", data.hex(" "), msg)
        if self.packet_tap:
            self.packet_tap("TX", msg, data)
        assert self._conn is not None
        await self._conn.write(data)

    async def request(self, opcode: int, payload: bytes) -> None:
        await self.send(Message(MsgType.PHONE_REQUEST, opcode, self._next_seq(), payload))

    async def request_device_info(self) -> None:
        await self.request(Opcode.GET_DEVICE_INFO, b"\xff\xff\xff\xff")

    @property
    def ready(self) -> bool:
        return self._authed.is_set() and self._conn is not None and not self._closed

    async def find_earbuds(self, start: bool, target: FindTarget = FindTarget.BOTH) -> None:
        """Kulaklıktan bulma sesi çaldırır / durdurur.

        Başlatmadan önce her zaman 'dur' gönderilir: hedef değiştirilirken (ör. sol → sağ)
        önceki kulaklığın çalmaya devam etmesini önler.
        """
        if not self.ready:
            raise SessionError("Protokol oturumu hazır değil")
        await self.request(Opcode.SET_CONFIG, find_earbuds_payload(False))
        if start:
            await self.request(Opcode.SET_CONFIG, find_earbuds_payload(True, target))
        log.info("Kulaklığı bul: %s (%s)", "BAŞLAT" if start else "DURDUR", target.name if start else "-")

    def refresh(self) -> None:
        self._refresh_now.set()

    def close(self) -> None:
        self._closed = True
        if self._conn:
            self._conn.close()

    # ------------------------------------------------------------- handling
    async def _handle(self, m: Message) -> None:
        op = m.opcode
        if op == Opcode.AUTH_CHALLENGE:
            if m.type == MsgType.RESPONSE:
                # Kulaklığın bizim challenge'ımıza yanıtı → ilk adımı onayla
                await self.request(Opcode.AUTH_CONFIRM, b"\x01\x00")
            elif len(m.payload) >= 17:
                resp = compute_challenge_response(bytes(m.payload[1:17]))
                await self.send(Message(MsgType.RESPONSE, Opcode.AUTH_CHALLENGE, m.seq, b"\x01" + resp))
        elif op == Opcode.AUTH_CONFIRM:
            if is_request(m.type):
                await self.send(Message(MsgType.RESPONSE, Opcode.AUTH_CONFIRM, m.seq, b"\x01"))
                log.info("Kimlik doğrulama tamamlandı")
                self._authed.set()
        elif op == Opcode.GET_DEVICE_INFO and m.type == MsgType.RESPONSE:
            info = parse_device_info(m.payload)
            s = self.snapshot
            s.firmware = info.firmware or s.firmware
            s.vid_pid = info.vid_pid or s.vid_pid
            s.model = info.model or s.model
            if info.battery:
                s.battery = info.battery
                s.updated_at = time.time()
                s.source = "device_info"
            self._info.set()
            self.on_update(s)
        elif op == Opcode.REPORT_STATUS and is_request(m.type):
            bat = parse_status_report(m.payload)
            await self.send(Message(MsgType.RESPONSE, Opcode.REPORT_STATUS, m.seq, b""))
            if bat:
                self.snapshot.battery = bat
                self.snapshot.updated_at = time.time()
                self.snapshot.source = "status_report"
                self.on_update(self.snapshot)
        elif op == Opcode.NOTIFY_CONFIG and is_request(m.type):
            await self.send(Message(MsgType.RESPONSE, Opcode.NOTIFY_CONFIG, m.seq, b""))
        for cb in list(self.extra_listeners):
            try:
                cb(m)
            except Exception:
                log.exception("Dinleyici hatası")

    async def _reader(self) -> None:
        assert self._conn is not None
        while not self._closed:
            try:
                data = await self._conn.read()
            except Exception as e:
                raise SessionError(f"Okuma hatası: {e}") from e
            if not data:
                raise SessionError("RFCOMM bağlantısı kulaklık tarafından kapatıldı")
            for m in self._parser.feed(data):
                raw_log.debug("RX %s", m)
                if self.packet_tap:
                    self.packet_tap("RX", m, m.encode())
                await self._handle(m)

    async def _refresher(self, interval_getter: Callable[[], int]) -> None:
        while not self._closed:
            try:
                await asyncio.wait_for(self._refresh_now.wait(), interval_getter())
            except asyncio.TimeoutError:
                pass
            self._refresh_now.clear()
            await self.request_device_info()

    # ------------------------------------------------------------------ run
    async def run(self, interval_getter: Callable[[], int] = lambda: 60) -> None:
        self._conn = RfcommConnection(self.address, SERVICE_UUID, self.prefer_cache)
        try:
            await self._conn.open()
        except RfcommError as e:
            raise SessionError(str(e)) from e
        log.info("RFCOMM %s bağlandı, kimlik doğrulanıyor", SERVICE_UUID)
        reader = asyncio.create_task(self._reader())
        try:
            await self.request(Opcode.AUTH_CHALLENGE, b"\x01" + random_challenge())
            await self._wait_or_fail(self._authed, reader, self.AUTH_TIMEOUT, "Kimlik doğrulama zaman aşımı")
            await self.request_device_info()
            await self.request(Opcode.GET_DEVICE_RUN_INFO, b"\xff\xff\xff\xff")
            await self._wait_or_fail(self._info, reader, self.INFO_TIMEOUT, "Cihaz bilgisi yanıtı gelmedi")
            refresher = asyncio.create_task(self._refresher(interval_getter))
            try:
                await reader  # bağlantı kopana kadar
            finally:
                refresher.cancel()
        finally:
            if not reader.done():
                reader.cancel()
            self.close()

    @staticmethod
    async def _wait_or_fail(ev: asyncio.Event, reader: asyncio.Task, timeout: float, msg: str) -> None:
        waiter = asyncio.create_task(ev.wait())
        done, _ = await asyncio.wait({waiter, reader}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        if waiter not in done:
            waiter.cancel()
            if reader in done and reader.exception():
                raise reader.exception()  # type: ignore[misc]
            raise SessionError(msg)
