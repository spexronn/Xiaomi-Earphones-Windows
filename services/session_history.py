"""Bağlantı oturumu geçmişi.

Arayüz bağlantı kopunca kapandığı için son kopma bilgisi diske yazılır ve
bir sonraki açılışta gösterilir.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass

from bluetooth.protocol import BatteryState

from .paths import config_dir

log = logging.getLogger(__name__)

REASON_BATTERY = "battery_empty"
REASON_CASE = "in_case"
REASON_RADIO = "radio_off"
REASON_LINK = "link_lost"

REASON_TEXT = {
    REASON_BATTERY: "Şarj bitti",
    REASON_CASE: "Kulaklıklar kutuya kondu",
    REASON_RADIO: "Bilgisayarın Bluetooth'u kapatıldı",
    REASON_LINK: "Bluetooth bağlantısı kesildi",
}


@dataclass
class Disconnect:
    time: float            # kopma anı (Unix)
    connected_at: float    # o oturumun başlangıcı
    reason: str
    detail: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.time - self.connected_at)

    @property
    def reason_text(self) -> str:
        return REASON_TEXT.get(self.reason, self.reason)


def _path():
    return config_dir() / "session_history.json"


def load_last() -> Disconnect | None:
    try:
        d = json.loads(_path().read_text(encoding="utf-8"))["last_disconnect"]
        return Disconnect(**d)
    except FileNotFoundError:
        return None
    except Exception as e:
        log.debug("Oturum geçmişi okunamadı: %s", e)
        return None


def save_last(d: Disconnect) -> None:
    try:
        tmp = _path().with_suffix(".tmp")
        tmp.write_text(json.dumps({"last_disconnect": asdict(d)}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, _path())
    except Exception as e:
        log.warning("Oturum geçmişi yazılamadı: %s", e)


def buds_in_use(battery: BatteryState | None) -> tuple[bool, bool] | None:
    """(sol, sağ) kulaklık kutu dışında mı? Şarj biti = kutuda. Veri yoksa None."""
    if battery is None:
        return None
    l, r = battery.left, battery.right
    if l.level is None and r.level is None:
        return None
    return (l.level is not None and not l.charging, r.level is not None and not r.charging)


def bud_states(battery: BatteryState | None) -> tuple[str, str] | None:
    """(sol, sağ) için "use" (kulakta), "case" (kutuda, şarj oluyor) ya da "off" (veri yok)."""
    if battery is None:
        return None
    st = tuple("off" if u.level is None else ("case" if u.charging else "use")
               for u in (battery.left, battery.right))
    return None if st == ("off", "off") else st  # type: ignore[return-value]


def usage_text(battery: BatteryState | None) -> str:
    st = bud_states(battery)
    if st is None:
        return ""
    l, r = st
    if l == r == "use":
        return "İki kulaklık kullanımda"
    if l == r == "case":
        return "İki kulaklık da kutuda"
    names = {0: ("Sol", "sol"), 1: ("Sağ", "sağ")}
    for i, j in ((0, 1), (1, 0)):
        if st[i] == "use":
            if st[j] == "case":
                return f"{names[i][0]} kulaklık kullanımda · {names[j][1]} kutuda"
            return f"Sadece {names[i][1]} kulaklık kullanımda"
    i, j = (0, 1) if st[0] == "case" else (1, 0)
    return f"{names[i][0]} kulaklık kutuda · {names[j][1]} bağlı değil"


def infer_reason(battery: BatteryState | None, had_live_data: bool, radio_off: bool) -> tuple[str, str]:
    """Kopma nedenini son GERÇEK verilere göre çıkarır. (neden, ayrıntı)"""
    if radio_off:
        return REASON_RADIO, ""
    if battery is not None and had_live_data:
        buds = [u for u in (battery.left, battery.right) if u.level is not None]
        if buds and all(u.charging for u in buds):
            return REASON_CASE, "kulaklıklar şarj oluyordu"
        empty = [u for u in buds if not u.charging and u.level is not None and u.level <= 5]
        if empty:
            return REASON_BATTERY, f"son pil %{min(u.level for u in empty)}"  # type: ignore[type-var]
    return REASON_LINK, "menzil dışı ya da kulaklık kapatıldı"
