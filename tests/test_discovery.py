"""Xiaomi / Redmi / POCO / Mi Bluetooth kulaklık otomatik tanıma ve ayar göçü testleri."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bluetooth.discovery import is_xiaomi_audio_name, matches  # noqa: E402


def test_matches_all_xiaomi_earbuds():
    models = (
        "REDMI Buds 8 Active",
        "Redmi Buds 5 Pro",
        "Redmi Buds 4 Lite",
        "Redmi Buds 6 Play",
        "Xiaomi Buds 5",
        "Xiaomi Buds 4 Pro",
        "Xiaomi OpenWear Stereo",
        "Xiaomi FlipBuds Pro",
        "Mi True Wireless Earphones 2",
        "Mi AirDots Pro 2",
        "Mi Air 2 SE",
        "POCO Pods",
        "Xiaomi_Buds_4",
    )
    for m in models:
        assert is_xiaomi_audio_name(m), f"Tanınmalıydı: {m}"
        assert matches(m, "auto")
        assert matches(m, "")


def test_rejects_non_audio_and_other_brands():
    rejected = (
        "Xiaomi 14 Pro",
        "Redmi Note 13 Pro",
        "Xiaomi Smart Band 8",
        "Redmi Watch 4",
        "Xiaomi Pad 6",
        "Mi Notebook Air 13",
        "AirPods Pro",
        "Samsung Galaxy Buds2",
        "Sony WH-1000XM5",
    )
    for dev in rejected:
        assert not is_xiaomi_audio_name(dev), f"Hariç tutulmalıydı: {dev}"
        assert not matches(dev, "auto")


def test_custom_comma_pattern():
    assert matches("Samsung Galaxy Buds2", "galaxy buds, poco pods")
    assert matches("POCO Pods", "galaxy buds, poco pods")
    assert not matches("Sony XM5", "galaxy buds, poco pods")

