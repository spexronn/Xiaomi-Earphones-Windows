"""JSON tabanlı kalıcı ayarlar."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields

from .paths import config_dir

log = logging.getLogger(__name__)

REFRESH_CHOICES = (15, 30, 60, 120, 300)


@dataclass
class Settings:
    run_at_startup: bool = True         # izleyici oturum açılışında başlar (otomatik algılama için gerekli)
    minimize_to_tray: bool = True
    auto_detect: bool = True            # Eşleşmiş cihazlar arasından REDMI Buds'ı otomatik bul
    device_address: str = ""            # auto_detect kapalıysa / son bulunan adres "AA:BB:CC:DD:EE:FF"
    device_name_pattern: str = "auto"   # "auto" tüm Xiaomi/Redmi/POCO kulaklıkları tanır
    refresh_interval: int = 60          # saniye
    theme: str = "dark"                 # dark | light
    diagnostic_mode: bool = False       # ham paket logu
    show_window_on_connect: bool = False
    disconnect_grace: int = 6           # saniye; kısa kopmalarda kapanmayı önler
    find_duration: int = 60             # saniye; "Kulaklığı bul" sesi bu süre sonunda kendiliğinden durur

    @staticmethod
    def path():
        return config_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
            names = {f.name for f in fields(cls)}
            for k, v in data.items():
                if k in names and isinstance(v, type(getattr(s, k))):
                    setattr(s, k, v)
        except FileNotFoundError:
            pass
        except Exception as e:  # bozuk dosya: varsayılanlarla devam
            log.warning("Ayar dosyası okunamadı (%s), varsayılanlar kullanılıyor", e)
        if s.device_name_pattern.strip().lower() in ("", "redmi buds 8"):
            s.device_name_pattern = "auto"
        if s.refresh_interval not in REFRESH_CHOICES:
            s.refresh_interval = 60
        s.find_duration = min(300, max(10, s.find_duration))
        return s

    def save(self) -> None:
        p = self.path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
