"""Protokol testleri. Örnek paketler gerçek REDMI Buds 8 Active'ten (fw 3.0.6.5) yakalanmıştır."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bluetooth.protocol import (  # noqa: E402
    BatteryUnit,
    FrameParser,
    Message,
    MsgType,
    Opcode,
    compute_challenge_response,
    parse_device_info,
    parse_status_report,
)

# Gerçek cihazdan alınan ham baytlar
RX_AUTH_RESP = bytes.fromhex("fedcba04500013000001 0a06b409619a27a56ec73d2d57e1ce16ef".replace(" ", ""))
RX_AUTH_CONFIRM = bytes.fromhex("fedcba0451000300 0101ef".replace(" ", ""))
RX_BUDS_CHALLENGE = bytes.fromhex("fedcbac45000120101150a0529b72474a30d29a31cd63b347aef")
RX_DEVICE_INFO = bytes.fromhex(
    "fedcba0402004b00021400524544 4d49204275647320382041637469 7665050130653065050327 1750e2"
    "02040102050003063065040 75f5fff020801020900020c00020d0202 0e0009101001 5f5fff003065ef"
    .replace(" ", ""))


def test_encode_request():
    m = Message(MsgType.PHONE_REQUEST, Opcode.GET_DEVICE_INFO, 2, b"\xff\xff\xff\xff")
    assert m.encode().hex() == "fedcbac402000502ffffffffef"


def test_encode_response():
    m = Message(MsgType.RESPONSE, Opcode.REPORT_STATUS, 7, b"")
    assert m.encode().hex() == "fedcba040e00020007ef"


def test_parser_handles_split_and_merged_frames():
    stream = RX_AUTH_RESP + RX_AUTH_CONFIRM + RX_BUDS_CHALLENGE + RX_DEVICE_INFO
    p = FrameParser()
    msgs = []
    for i in range(0, len(stream), 7):          # 7 baytlık parçalar halinde besle
        msgs += p.feed(stream[i:i + 7])
    assert [m.opcode for m in msgs] == [Opcode.AUTH_CHALLENGE, Opcode.AUTH_CONFIRM, Opcode.AUTH_CHALLENGE,
                                        Opcode.GET_DEVICE_INFO]
    assert msgs[0].type == MsgType.RESPONSE and msgs[0].seq == 0
    assert msgs[2].type == MsgType.PHONE_REQUEST and msgs[2].seq == 1
    assert msgs[2].payload[1:17].hex() == "150a0529b72474a30d29a31cd63b347a"


def test_parser_skips_garbage():
    p = FrameParser()
    msgs = p.feed(b"\x00\x11garbage" + RX_AUTH_CONFIRM + b"\xfe\xdc")
    assert len(msgs) == 1 and msgs[0].opcode == Opcode.AUTH_CONFIRM


def test_device_info_real_capture():
    msg = FrameParser().feed(RX_DEVICE_INFO)[0]
    info = parse_device_info(msg.payload)
    assert info.model == "REDMI Buds 8 Active"
    assert info.firmware == "3.0.6.5"
    assert info.vid_pid == "VID 0x2717 / PID 0x50E2"
    bat = info.battery
    assert bat is not None
    assert bat.left.level == 95 and not bat.left.charging
    assert bat.right.level == 95
    assert bat.case.level is None      # 0xFF: kulaklıklar kutu dışında


def test_battery_byte_decoding():
    assert BatteryUnit.from_byte(0xFF).level is None
    u = BatteryUnit.from_byte(0x80 | 64)
    assert u.level == 64 and u.charging
    assert BatteryUnit.from_byte(100).level == 100


def test_status_report():
    b = parse_status_report(bytes([0x04, 0x00, 0x50, 0xD5, 0x3C]))
    assert b is not None
    assert (b.left.level, b.right.level, b.right.charging, b.case.level) == (80, 85, True, 60)


def test_auth_response_shape_and_determinism():
    ch = bytes.fromhex("150a0529b72474a30d29a31cd63b347a")
    r1 = compute_challenge_response(ch)
    assert len(r1) == 16 and r1 == compute_challenge_response(ch)
    assert r1 != compute_challenge_response(bytes(16))
    # Girdiyi değiştirmemeli
    assert ch.hex() == "150a0529b72474a30d29a31cd63b347a"
