"""Ayarlar, tanılama ve log görüntüleme pencereleri."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services import autostart
from services.config import REFRESH_CHOICES, Settings
from services.paths import logs_dir

from . import theme
from .graphics import app_icon, ui_icon
from .widgets import Toggle


def _style(dlg: QDialog, settings: Settings) -> theme.Palette:
    pal = theme.get(settings.theme)
    dlg.setStyleSheet(theme.stylesheet(pal))
    dlg.setWindowIcon(app_icon())
    for t in dlg.findChildren(Toggle):
        t.set_palette(pal)
    return pal


class SettingsDialog(QDialog):
    saved = Signal()
    open_logs = Signal()
    find_requested = Signal(str)       # LEFT | RIGHT | BOTH
    stop_find_requested = Signal()

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Ayarlar — SPEXRON Buds Monitor")
        self.setMinimumWidth(540)
        pal = _style(self, settings)

        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(20, 18, 20, 18)

        # başlık bandı
        head = QVBoxLayout()
        head.setSpacing(2)
        h1 = QLabel("Ayarlar")
        h1.setProperty("role", "h1")
        sub = QLabel("İzleyici davranışını, cihaz eşlemesini ve görünüm tercihlerini yönetin.")
        sub.setProperty("role", "dim")
        head.addWidget(h1)
        head.addWidget(sub)
        lay.addLayout(head)

        tabs = QTabWidget()

        # ---- Sekme 1: Genel & Cihaz
        tab_general = QWidget()
        lg = QVBoxLayout(tab_general)
        lg.setContentsMargins(14, 14, 14, 14)
        lg.setSpacing(12)

        g1 = QGroupBox("Arka Plan ve Pencere")
        f1 = QVBoxLayout(g1)
        f1.setSpacing(6)
        self.cb_startup = Toggle("Windows başlangıcında çalıştır (bağlantı izleyicisi)")
        self.cb_tray = Toggle("Kapatınca / küçültünce sistem tepsisine gönder")
        self.cb_show = Toggle("Kulaklık bağlanınca pencereyi otomatik göster")
        for w in (self.cb_startup, self.cb_tray, self.cb_show):
            f1.addWidget(w)
        hint = QLabel(
            "İzleyici yalnızca Windows Bluetooth bağlantı olayını dinler; sürekli tarama yapmaz. "
            "Bağlantı kesildiğinde arayüz bellekten tamamen kapanır."
        )
        hint.setWordWrap(True)
        hint.setProperty("role", "faint")
        f1.addWidget(hint)
        lg.addWidget(g1)

        g2 = QGroupBox("Cihaz ve Telemetri")
        f2 = QFormLayout(g2)
        f2.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        f2.setVerticalSpacing(10)
        f2.setHorizontalSpacing(14)
        self.cb_auto = Toggle("Otomatik cihaz algılama (tüm Xiaomi / REDMI / POCO kulaklıklar)")
        f2.addRow(self.cb_auto)
        self.device_combo = QComboBox()
        self.device_combo.addItem("Liste yükleniyor…", "")
        f2.addRow("Cihaz", self.device_combo)
        self.interval = QComboBox()
        for s in REFRESH_CHOICES:
            self.interval.addItem(f"{s} saniye" if s < 60 else f"{s // 60} dakika", s)
        f2.addRow("Pil yenileme aralığı", self.interval)
        self.grace = QSpinBox()
        self.grace.setRange(2, 60)
        self.grace.setSuffix(" sn")
        f2.addRow("Kopma toleransı", self.grace)
        lg.addWidget(g2)
        lg.addStretch(1)
        tabs.addTab(tab_general, "Genel ve Cihaz")

        # ---- Sekme 2: Kulaklığı Bul
        tab_find = QWidget()
        lf = QVBoxLayout(tab_find)
        lf.setContentsMargins(14, 14, 14, 14)
        lf.setSpacing(12)

        warn_box = QFrame()
        warn_box.setObjectName("BannerWarn")
        wb = QVBoxLayout(warn_box)
        wb.setContentsMargins(12, 10, 12, 10)
        fhint = QLabel(
            "Seçilen kulaklık yüksek sesle çalar. Başlatmadan önce kulaklığı kulağınızdan çıkarın. "
            "Kulaklık bu PC'ye bağlı ve şarj kutusunun dışında olmalıdır."
        )
        fhint.setWordWrap(True)
        fhint.setProperty("role", "dim")
        wb.addWidget(fhint)
        lf.addWidget(warn_box)

        g4 = QGroupBox("Ses Kontrolü")
        f4 = QVBoxLayout(g4)
        f4.setSpacing(10)
        frow = QHBoxLayout()
        frow.setSpacing(8)
        self.find_btns: dict[str, QPushButton] = {}
        for key, text in (("LEFT", "Sol"), ("RIGHT", "Sağ"), ("BOTH", "İki kulaklık")):
            b = QPushButton(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setIcon(ui_icon("sound", pal.text, 14))
            b.setIconSize(QSize(14, 14))
            b.clicked.connect(lambda _c=False, k=key: self.find_requested.emit(k))
            self.find_btns[key] = b
            frow.addWidget(b)
        self.btn_stop_find = QPushButton("Durdur")
        self.btn_stop_find.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop_find.setIcon(ui_icon("stop", pal.red, 14))
        self.btn_stop_find.setIconSize(QSize(14, 14))
        self.btn_stop_find.clicked.connect(self.stop_find_requested)
        frow.addWidget(self.btn_stop_find)
        f4.addLayout(frow)

        self.find_status = QLabel("")
        self.find_status.setProperty("role", "dim")
        f4.addWidget(self.find_status)
        fd = QFormLayout()
        self.find_dur = QSpinBox()
        self.find_dur.setRange(10, 300)
        self.find_dur.setSingleStep(10)
        self.find_dur.setSuffix(" sn")
        fd.addRow("Otomatik durdurma", self.find_dur)
        f4.addLayout(fd)
        lf.addWidget(g4)
        lf.addStretch(1)
        tabs.addTab(tab_find, "Kulaklığı Bul")

        # ---- Sekme 3: Görünüm & Tanılama
        tab_adv = QWidget()
        la = QVBoxLayout(tab_adv)
        la.setContentsMargins(14, 14, 14, 14)
        la.setSpacing(12)

        g3 = QGroupBox("Tema ve Günlükler")
        f3 = QFormLayout(g3)
        f3.setVerticalSpacing(10)
        f3.setHorizontalSpacing(14)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Koyu", "dark")
        self.theme_combo.addItem("Açık", "light")
        f3.addRow("Arayüz teması", self.theme_combo)
        self.cb_diag = Toggle("Bluetooth tanılama modu (ham paketleri logla)")
        f3.addRow(self.cb_diag)
        btn_logs = QPushButton("Logları görüntüle")
        btn_logs.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_logs.setIcon(ui_icon("logs", pal.text, 14))
        btn_logs.setIconSize(QSize(14, 14))
        btn_logs.clicked.connect(self.open_logs)
        f3.addRow("Sistem kayıtları", btn_logs)
        la.addWidget(g3)
        la.addStretch(1)
        tabs.addTab(tab_adv, "Görünüm ve Kayıtlar")

        lay.addWidget(tabs)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch()
        cancel = QPushButton("İptal")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Kaydet")
        ok.setProperty("accent", True)
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setIcon(ui_icon("check", "#FFFFFF", 14))
        ok.setIconSize(QSize(14, 14))
        ok.clicked.connect(self._save)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

        s = settings
        self.cb_startup.setChecked(autostart.is_enabled())
        self.cb_tray.setChecked(s.minimize_to_tray)
        self.cb_show.setChecked(s.show_window_on_connect)
        self.cb_auto.setChecked(s.auto_detect)
        self.cb_diag.setChecked(s.diagnostic_mode)
        self.interval.setCurrentIndex(max(0, self.interval.findData(s.refresh_interval)))
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(s.theme)))
        self.grace.setValue(s.disconnect_grace)
        self.find_dur.setValue(s.find_duration)
        self.cb_auto.toggled.connect(lambda on: self.device_combo.setEnabled(not on))
        self.device_combo.setEnabled(not s.auto_detect)
        _style(self, settings)

    def set_find_state(self, st) -> None:
        """Kulaklığı bul düğmelerini bağlantı / çalma durumuna göre güncelle."""
        self._find_state = st
        if not hasattr(self, "_find_tick"):
            self._find_tick = QTimer(self)
            self._find_tick.setInterval(1000)
            self._find_tick.timeout.connect(lambda: self.set_find_state(self._find_state))
        if st.finding and not self._find_tick.isActive():
            self._find_tick.start()
        elif not st.finding:
            self._find_tick.stop()
        ready = bool(st.acl_connected and st.protocol_ready)
        pal = theme.get(self.settings.theme)
        names = {"LEFT": "Sol kulaklık", "RIGHT": "Sağ kulaklık", "BOTH": "İki kulaklık"}
        for k, b in self.find_btns.items():
            active = st.finding == k
            b.setEnabled(ready)
            b.setProperty("accent", active)
            b.setIcon(ui_icon("sound", "#FFFFFF" if active else pal.text, 14))
            b.style().unpolish(b)
            b.style().polish(b)
        self.btn_stop_find.setEnabled(bool(st.finding))
        if st.finding:
            left = max(0, int((st.finding_until or 0) - datetime.now().timestamp()))
            self.find_status.setText(f"{names.get(st.finding, '')} çalıyor… ({left} sn sonra otomatik durur)")
        elif st.find_error:
            self.find_status.setText(f"Komut gönderilemedi: {st.find_error}")
        elif not ready:
            self.find_status.setText("Kulaklık bağlanınca kullanılabilir.")
        else:
            self.find_status.setText("Hazır.")

    def set_paired(self, devices) -> None:
        self.device_combo.clear()
        if not devices:
            self.device_combo.addItem("Eşleşmiş cihaz yok", "")
        for d in devices:
            self.device_combo.addItem(f"{d.name}  ({d.address_str}){'  · bağlı' if d.connected else ''}", d.address_str)
        i = self.device_combo.findData(self.settings.device_address)
        if i >= 0:
            self.device_combo.setCurrentIndex(i)

    def _save(self) -> None:
        s = self.settings
        s.run_at_startup = self.cb_startup.isChecked()
        s.minimize_to_tray = self.cb_tray.isChecked()
        s.show_window_on_connect = self.cb_show.isChecked()
        s.auto_detect = self.cb_auto.isChecked()
        if not s.auto_detect and self.device_combo.currentData():
            s.device_address = self.device_combo.currentData()
        s.refresh_interval = int(self.interval.currentData())
        s.theme = self.theme_combo.currentData()
        s.diagnostic_mode = self.cb_diag.isChecked()
        s.disconnect_grace = self.grace.value()
        s.find_duration = self.find_dur.value()
        s.save()
        autostart.sync(s.run_at_startup)
        self.saved.emit()
        self.accept()


class DiagnosticsDialog(QDialog):
    start_requested = Signal(int)

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bluetooth Tanılama — SPEXRON Buds Monitor")
        self.resize(900, 650)
        pal = _style(self, settings)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        h1 = QLabel("Bluetooth Tanılama")
        h1.setProperty("role", "h1")
        lay.addWidget(h1)

        banner = QFrame()
        banner.setObjectName("BannerInfo")
        bl = QVBoxLayout(banner)
        bl.setContentsMargins(12, 10, 12, 10)
        info = QLabel(
            "Tanılama; Windows pil servisini, SDP profillerini, Xiaomi FD2D protokolünü (ham paketlerle), "
            "BLE reklamlarını ve GATT Battery Service'i analiz eder. Dinleme sırasında kapağı açıp kapatarak "
            "kutu verisi akışını gözlemleyebilirsiniz."
        )
        info.setWordWrap(True)
        info.setProperty("role", "dim")
        bl.addWidget(info)
        lay.addWidget(banner)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("Dinleme süresi"))
        self.secs = QSpinBox()
        self.secs.setRange(5, 300)
        self.secs.setValue(30)
        self.secs.setSuffix(" sn")
        row.addWidget(self.secs)
        row.addStretch()
        self.status = QLabel("")
        self.status.setProperty("role", "dim")
        row.addWidget(self.status)
        self.btn = QPushButton("Tanılamayı başlat")
        self.btn.setProperty("accent", True)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setIcon(ui_icon("play", "#FFFFFF", 14))
        self.btn.setIconSize(QSize(14, 14))
        self.btn.clicked.connect(self._start)
        row.addWidget(self.btn)
        self.btn_open = QPushButton("Rapor klasörü")
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setIcon(ui_icon("folder", pal.text, 14))
        self.btn_open.setIconSize(QSize(14, 14))
        self.btn_open.clicked.connect(lambda: os.startfile(logs_dir()))
        row.addWidget(self.btn_open)
        lay.addLayout(row)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        lay.addWidget(self.text, 1)

        live_lbl = QLabel("CANLI PAKET AKIŞI (TANILAMA MODU AÇIKKEN)")
        live_lbl.setProperty("role", "title")
        lay.addWidget(live_lbl)
        self.live = QPlainTextEdit()
        self.live.setReadOnly(True)
        self.live.setMaximumBlockCount(500)
        self.live.setFixedHeight(130)
        lay.addWidget(self.live)

    def _start(self):
        self.btn.setEnabled(False)
        self.text.setPlainText("Tanılama çalışıyor…\n")
        self.start_requested.emit(self.secs.value())

    def on_progress(self, msg: str):
        self.status.setText(msg)
        self.text.appendPlainText(f"» {msg}")

    def on_done(self, report: str, path: str):
        self.btn.setEnabled(True)
        self.status.setText(f"Rapor kaydedildi: {Path(path).name}")
        self.text.setPlainText(report)

    def on_packet(self, direction: str, text: str):
        self.live.appendPlainText(f"{direction}  {text}")


class LogViewer(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Loglar — SPEXRON Buds Monitor")
        self.resize(940, 620)
        pal = _style(self, settings)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        h1 = QLabel("Uygulama Kayıtları")
        h1.setProperty("role", "h1")
        lay.addWidget(h1)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.which = QComboBox()
        self.which.addItem("Arayüz (gui.log)", "gui.log")
        self.which.addItem("Bağlantı izleyicisi (watcher.log)", "watcher.log")
        self.which.currentIndexChanged.connect(self.reload)
        row.addWidget(self.which)
        row.addStretch()
        b1 = QPushButton("Yenile")
        b1.setCursor(Qt.CursorShape.PointingHandCursor)
        b1.setIcon(ui_icon("refresh", pal.text, 14))
        b1.setIconSize(QSize(14, 14))
        b1.clicked.connect(self.reload)
        b2 = QPushButton("Klasörü aç")
        b2.setCursor(Qt.CursorShape.PointingHandCursor)
        b2.setIcon(ui_icon("folder", pal.text, 14))
        b2.setIconSize(QSize(14, 14))
        b2.clicked.connect(lambda: os.startfile(logs_dir()))
        row.addWidget(b1)
        row.addWidget(b2)
        lay.addLayout(row)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont("Cascadia Mono", 9))
        lay.addWidget(self.text, 1)
        self.reload()

    def reload(self):
        p = logs_dir() / self.which.currentData()
        try:
            data = p.read_text(encoding="utf-8", errors="replace")[-200_000:]
        except FileNotFoundError:
            data = "(log dosyası henüz yok)"
        self.text.setPlainText(data)
        self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())

