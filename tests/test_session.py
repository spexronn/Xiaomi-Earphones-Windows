import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bluetooth.protocol import BatteryState, BatteryUnit  # noqa: E402
from services.session_history import (  # noqa: E402
    REASON_BATTERY,
    REASON_CASE,
    REASON_LINK,
    REASON_RADIO,
    Disconnect,
    infer_reason,
)


def bat(l, lc, r, rc):
    return BatteryState(BatteryUnit(l, lc), BatteryUnit(r, rc), BatteryUnit(None, False))


def test_battery_empty():
    assert infer_reason(bat(3, False, 40, False), True, False)[0] == REASON_BATTERY


def test_put_in_case():
    assert infer_reason(bat(80, True, 82, True), True, False)[0] == REASON_CASE


def test_normal_link_loss():
    assert infer_reason(bat(80, False, 82, False), True, False)[0] == REASON_LINK


def test_stale_data_is_not_trusted():
    # Eski veriyle "şarj bitti" denmemeli
    assert infer_reason(bat(2, False, 2, False), False, False)[0] == REASON_LINK


def test_radio_off_wins():
    assert infer_reason(bat(2, False, 2, False), True, True)[0] == REASON_RADIO


def test_duration():
    assert Disconnect(time=1000, connected_at=400, reason=REASON_LINK).duration == 600


def test_usage_text():
    from services.session_history import usage_text
    assert usage_text(bat(80, True, 70, False)) == "Sağ kulaklık kullanımda · sol kutuda"
    assert usage_text(bat(None, False, 70, False)) == "Sadece sağ kulaklık kullanımda"
    assert usage_text(bat(80, False, 70, True)) == "Sol kulaklık kullanımda · sağ kutuda"
    assert usage_text(bat(80, False, 70, False)) == "İki kulaklık kullanımda"
    assert usage_text(bat(80, True, 70, True)) == "İki kulaklık da kutuda"
    assert usage_text(bat(80, True, None, False)) == "Sol kulaklık kutuda · sağ bağlı değil"
    assert usage_text(bat(None, False, None, False)) == ""
