"""Fast Pair reklam çözümleme testleri (gerçek REDMI Buds 8 Active yakalamaları)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bluetooth.fastpair import parse_service_data  # noqa: E402

REAL_1 = bytes.fromhex("2cfe004061200c811156345a5aff")
REAL_2 = bytes.fromhex("2cfe0040400498801124345a5aff")


def test_real_captures():
    for raw in (REAL_1, REAL_2):
        b = parse_service_data(raw)
        assert b is not None
        assert b.left.level == 90 and b.right.level == 90
        assert not b.left.charging and not b.right.charging
        assert b.case.level is None and not b.case.charging   # 0xFF → bilinmiyor


def test_charging_and_case():
    b = parse_service_data(bytes.fromhex("2cfe00400000000011003" + "3d5d4c8"))
    assert b is not None
    assert (b.left.level, b.left.charging) == (85, True)
    assert (b.right.level, b.right.charging) == (84, True)
    assert (b.case.level, b.case.charging) == (72, True)


def test_discoverable_and_foreign():
    assert parse_service_data(bytes.fromhex("2cfe123456")) is None      # yalnızca model kimliği
    assert parse_service_data(bytes.fromhex("2dfd0011223344")) is None  # başka UUID
    assert parse_service_data(bytes.fromhex("2cfe0040000000001100")) is None  # pil alanı yok
