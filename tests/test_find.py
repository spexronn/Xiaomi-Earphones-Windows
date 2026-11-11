"""'Kulaklığınızı bulun' komut kodlaması (Gadgetbridge RedmiBudsProtocol.encodeFindDevice ile aynı)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bluetooth.protocol import FindTarget, Message, MsgType, Opcode, find_earbuds_payload  # noqa: E402


def test_start_payloads():
    assert find_earbuds_payload(True, FindTarget.LEFT) == bytes([4, 0, 9, 1, 1])
    assert find_earbuds_payload(True, FindTarget.RIGHT) == bytes([4, 0, 9, 1, 2])
    assert find_earbuds_payload(True, FindTarget.BOTH) == bytes([4, 0, 9, 1, 3])


def test_stop_always_targets_both():
    assert find_earbuds_payload(False, FindTarget.LEFT) == bytes([4, 0, 9, 0, 3])


def test_full_frame():
    m = Message(MsgType.PHONE_REQUEST, Opcode.SET_CONFIG, 0x10, find_earbuds_payload(True, FindTarget.BOTH))
    assert m.encode().hex() == "fedcbac4f2000610040009" "0103ef"
