"""Xiaomi / Redmi Buds kontrol protokolü (RFCOMM, servis UUID 0000FD2D).

Protokol bilgisi Gadgetbridge projesinin (AGPL-3.0, Jonathan Gobbo) açık kaynak
analizine dayanır; bu dosya bağımsız bir Python uygulamasıdır.

Çerçeve formatı (big endian):
    İstek  : FE DC BA | type | opcode | len(2) | seq | payload | EF      (len = payload + 1)
    Yanıt  : FE DC BA | type | opcode | len(2) | 00 | seq | payload | EF (len = payload + 2)

İstek türleri 0x40 bitini taşır (0xC4 telefon isteği, 0xC0 kulaklık isteği,
0xC7 kulaklık bildirimi); 0x04 yanıttır.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import IntEnum

SERVICE_UUID = "0000fd2d-0000-1000-8000-00805f9b34fb"

HEADER = b"\xfe\xdc\xba"
TRAILER = 0xEF


class MsgType(IntEnum):
    PHONE_REQUEST = 0xC4
    RESPONSE = 0x04
    EARBUDS_REQUEST = 0xC0
    EARBUDS_NOTIFY = 0xC7


class Opcode(IntEnum):
    GET_DEVICE_INFO = 0x02
    ANC = 0x08
    GET_DEVICE_RUN_INFO = 0x09
    REPORT_STATUS = 0x0E
    AUTH_CHALLENGE = 0x50
    AUTH_CONFIRM = 0x51
    SET_CONFIG = 0xF2
    GET_CONFIG = 0xF3
    NOTIFY_CONFIG = 0xF4


class FindTarget(IntEnum):
    """'Kulaklığınızı bulun' hedefi (SET_CONFIG yapılandırma 0x09)."""
    LEFT = 0x01
    RIGHT = 0x02
    BOTH = 0x03


CONFIG_FIND_EARBUDS = 0x09


def find_earbuds_payload(start: bool, target: FindTarget = FindTarget.BOTH) -> bytes:
    """SET_CONFIG (0xF2) yükü: [len=4] 00 [cfg=09] [1=çal / 0=dur] [hedef].

    Durdurma her zaman 'her ikisi' hedefiyle gönderilir (Gadgetbridge RedmiBudsProtocol
    encodeFindDevice ile aynı davranış).
    """
    if not start:
        target = FindTarget.BOTH
    return bytes([0x04, 0x00, CONFIG_FIND_EARBUDS, 0x01 if start else 0x00, int(target)])


def is_request(msg_type: int) -> bool:
    return bool(msg_type & 0x40)


@dataclass
class Message:
    type: int
    opcode: int
    seq: int
    payload: bytes = b""

    def encode(self) -> bytes:
        req = is_request(self.type)
        length = len(self.payload) + (1 if req else 2)
        out = bytearray(HEADER)
        out += bytes([self.type & 0xFF, self.opcode & 0xFF, (length >> 8) & 0xFF, length & 0xFF])
        if not req:
            out.append(0x00)
        out.append(self.seq & 0xFF)
        out += self.payload
        out.append(TRAILER)
        return bytes(out)

    def __str__(self) -> str:
        try:
            t = MsgType(self.type).name
        except ValueError:
            t = f"0x{self.type:02X}"
        try:
            o = Opcode(self.opcode).name
        except ValueError:
            o = f"0x{self.opcode:02X}"
        return f"<{t} {o} seq={self.seq} payload={self.payload.hex(' ')}>"


class FrameParser:
    """Akış halinde gelen baytlardan çerçeveleri ayıklar (parçalı/birleşik paketlere dayanıklı)."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Message]:
        self._buf += data
        msgs: list[Message] = []
        while True:
            start = self._buf.find(HEADER)
            if start < 0:
                # başlığın yarısı gelmiş olabilir, son 2 baytı tut
                del self._buf[:-2]
                break
            if start:
                del self._buf[:start]
            if len(self._buf) < 7:
                break
            length = (self._buf[5] << 8) | self._buf[6]
            total = 7 + length + 1
            if length > 2048:  # bozuk veri: başlığı atla
                del self._buf[:3]
                continue
            if len(self._buf) < total:
                break
            frame = bytes(self._buf[:total])
            del self._buf[:total]
            if frame[-1] != TRAILER:
                continue
            msg_type, opcode = frame[3], frame[4]
            body = frame[7:-1]
            if is_request(msg_type):
                seq, payload = body[0], body[1:]
            else:
                seq, payload = body[1], body[2:]
            msgs.append(Message(msg_type, opcode, seq, payload))
        return msgs


# --------------------------------------------------------------------------
# Pil verisi
# --------------------------------------------------------------------------
@dataclass
class BatteryUnit:
    level: int | None = None      # 0..100, None = bilinmiyor
    charging: bool = False

    @classmethod
    def from_byte(cls, b: int) -> "BatteryUnit":
        if b == 0xFF:
            return cls(None, False)
        return cls(b & 0x7F, bool(b & 0x80))


@dataclass
class BatteryState:
    left: BatteryUnit = field(default_factory=BatteryUnit)
    right: BatteryUnit = field(default_factory=BatteryUnit)
    case: BatteryUnit = field(default_factory=BatteryUnit)

    @classmethod
    def from_bytes(cls, b: bytes) -> "BatteryState":
        return cls(BatteryUnit.from_byte(b[0]), BatteryUnit.from_byte(b[1]), BatteryUnit.from_byte(b[2]))


def iter_tlv(payload: bytes):
    """[len][tag][len-1 bayt veri] biçimindeki TLV kayıtlarını döndürür."""
    i = 0
    while i + 1 < len(payload):
        ln = payload[i]
        if ln == 0:
            break
        tag = payload[i + 1]
        yield tag, payload[i + 2:i + 1 + ln]
        i += ln + 1


@dataclass
class DeviceInfo:
    model: str | None = None
    firmware: str | None = None
    vid_pid: str | None = None
    battery: BatteryState | None = None


def _bcd_version(b: bytes) -> str:
    return ".".join(str(x) for x in (b[0] >> 4, b[0] & 0xF, b[1] >> 4, b[1] & 0xF))


def parse_device_info(payload: bytes) -> DeviceInfo:
    info = DeviceInfo()
    for tag, data in iter_tlv(payload):
        if tag == 0x00 and data:
            info.model = data.decode("utf-8", "replace").strip("\x00 ")
        elif tag == 0x01 and len(data) >= 2:
            info.firmware = _bcd_version(data[:2])
        elif tag == 0x03 and len(data) >= 4:
            info.vid_pid = f"VID 0x{data[0]:02X}{data[1]:02X} / PID 0x{data[2]:02X}{data[3]:02X}"
        elif tag == 0x07 and len(data) >= 3:
            info.battery = BatteryState.from_bytes(data[:3])
    return info


def parse_status_report(payload: bytes) -> BatteryState | None:
    for tag, data in iter_tlv(payload):
        if tag == 0x00 and len(data) >= 3:
            return BatteryState.from_bytes(data[:3])
    return None


# --------------------------------------------------------------------------
# Kimlik doğrulama: Bluetooth SAFER+ (E1/Ar) varyantı, 128 bit anahtar, 8 tur
# --------------------------------------------------------------------------
_PATTERN = 0x9999
_SEQ = bytes([0x11, 0x22, 0x33, 0x33, 0x22, 0x11, 0x11, 0x22, 0x33, 0x33, 0x22, 0x11, 0x11, 0x22, 0x33, 0x33])
_COEF = (
    (2, 1, 1, 1, 4, 2, 1, 1, 2, 2, 4, 2, 4, 4, 16, 8),
    (2, 1, 1, 1, 4, 2, 1, 1, 1, 1, 2, 1, 2, 2, 8, 4),
    (1, 1, 4, 2, 2, 2, 4, 2, 16, 8, 4, 4, 2, 1, 1, 1),
    (1, 1, 4, 2, 1, 1, 2, 1, 8, 4, 2, 2, 2, 1, 1, 1),
    (16, 8, 2, 2, 4, 2, 4, 4, 1, 1, 4, 2, 1, 1, 2, 1),
    (8, 4, 1, 1, 2, 1, 2, 2, 1, 1, 4, 2, 1, 1, 2, 1),
    (2, 2, 4, 2, 4, 4, 16, 8, 2, 1, 1, 1, 4, 2, 1, 1),
    (1, 1, 2, 1, 2, 2, 8, 4, 2, 1, 1, 1, 4, 2, 1, 1),
    (4, 2, 4, 4, 16, 8, 2, 2, 1, 1, 2, 1, 1, 1, 4, 2),
    (2, 1, 2, 2, 8, 4, 1, 1, 1, 1, 2, 1, 1, 1, 4, 2),
    (4, 4, 16, 8, 1, 1, 2, 1, 4, 2, 1, 1, 4, 2, 2, 2),
    (2, 2, 8, 4, 1, 1, 2, 1, 4, 2, 1, 1, 2, 1, 1, 1),
    (1, 1, 2, 1, 1, 1, 4, 2, 4, 4, 16, 8, 2, 2, 4, 2),
    (1, 1, 2, 1, 1, 1, 4, 2, 2, 2, 8, 4, 1, 1, 2, 1),
    (4, 2, 1, 1, 2, 1, 1, 1, 4, 2, 2, 2, 16, 8, 4, 4),
    (4, 2, 1, 1, 2, 1, 1, 1, 2, 1, 1, 1, 8, 4, 2, 2),
)

_EXP = [0 if i == 128 else pow(45, i, 257) for i in range(256)]
_LOG = [0] * 256
_LOG[0] = 128
for _i in range(1, 256):
    _m = pow(45, _i, 257)
    if _m != 256:
        _LOG[_m] = _i
_BIAS = [
    [(lambda v: 0 if v == 256 else v)(pow(45, pow(45, 17 * (i + 2) + (j + 1), 257), 257)) for j in range(16)]
    for i in range(16)
]


def _xor_lane(i: int) -> bool:
    return bool((1 << i) & _PATTERN)


def _key_schedule(challenge: bytes) -> list[list[int]]:
    key = list(challenge)
    key[15] ^= 6
    keys = [key[:]]
    reg = key[:] + [0]
    for b in key:
        reg[16] ^= b
    for k in range(1, 17):
        reg = [((r << 3) | (r >> 5)) & 0xFF for r in reg]
        keys.append([(reg[(k + i) % 17] + _BIAS[k - 1][i]) & 0xFF for i in range(16)])
    return keys


def _encrypt(plain: bytes, keys: list[list[int]]) -> bytes:
    c = list(plain)
    for rnd in range(8):
        if rnd == 2:
            c = [(c[i] ^ plain[i]) if _xor_lane(i) else (c[i] + plain[i]) & 0xFF for i in range(16)]
        k1, k2 = keys[rnd * 2], keys[rnd * 2 + 1]
        c = [(c[i] ^ k1[i]) if _xor_lane(i) else (c[i] + k1[i]) & 0xFF for i in range(16)]
        c = [_EXP[c[i]] if _xor_lane(i) else _LOG[c[i]] for i in range(16)]
        c = [(c[i] + k2[i]) & 0xFF if _xor_lane(i) else (c[i] ^ k2[i]) for i in range(16)]
        c = [sum(_COEF[i][j] * c[j] for j in range(16)) & 0xFF for i in range(16)]
    k = keys[16]
    return bytes((c[i] ^ k[i]) if _xor_lane(i) else (c[i] + k[i]) & 0xFF for i in range(16))


def compute_challenge_response(challenge: bytes) -> bytes:
    if len(challenge) != 16:
        raise ValueError("challenge 16 bayt olmalı")
    return _encrypt(_SEQ, _key_schedule(challenge))


def random_challenge() -> bytes:
    return os.urandom(16)
