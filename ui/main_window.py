from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services import session_history
from services.backend import LinkState
from services.config import Settings
from services.paths import APP_NAME, APP_VERSION, DEVELOPER

from . import theme
from .graphics import app_icon, ui_icon
from .widgets import BatteryCard, InfoCard, SessionPanel, StatusPill


def hms(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def human(seconds: float) -> str:
    s = max(0, int(seconds))
    h, m = s // 3600, s % 3600 // 60
    if h:
        return f"{h} sa {m} dk"
    if m:
        return f"{m} dk {s % 60} sn"
    return f"{s} sn"


def stamp(ts: float) -> str:
    d = datetime.fromtimestamp(ts)
    if d.date() == datetime.now().date():
        return d.strftime("%H:%M:%S") + " · bugün"
    months = "Oca Şub Mar Nis May Haz Tem Ağu Eyl Eki Kas Ara".split()
    return d.strftime("%H:%M:%S") + f" · {d.day} {months[d.month - 1]}"


def ago(ts: float | None) -> str:
    if not ts:
        return "--"
    sec = int(datetime.now().timestamp() - ts)
    t = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    if sec < 5:
        return f"{t} (az önce)"
    if sec < 60:
        return f"{t} ({sec} sn)"
    if sec < 3600:
        return f"{t} ({sec // 60} dk)"
    return datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")


class MainWindow(QMainWindow):
    refresh_requested = Signal()
    settings_requested = Signal()
    diagnostics_requested = Signal()
    find_requested = Signal()
    close_requested = Signal()

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.state = LinkState()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(940, 640)
        self.resize(980, 670)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 20, 24, 15)
        outer.setSpacing(16)

        # ---- üst bar
        head = QHBoxLayout()
        head.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(40, 40))
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.brand = QLabel()
        self.brand.setTextFormat(Qt.TextFormat.RichText)
        self.subtitle = QLabel("Xiaomi Bluetooth kulaklık pil & oturum monitörü")
        self.subtitle.setProperty("role", "dim")
        titles.addWidget(self.brand)
        titles.addWidget(self.subtitle)
        head.addWidget(logo)
        head.addLayout(titles)
        head.addStretch()

        self.pill = StatusPill()
        head.addWidget(self.pill)

        self.btn_refresh = QPushButton("Yenile")
        self.btn_refresh.setProperty("accent", True)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setIconSize(QSize(15, 15))
        self.btn_refresh.clicked.connect(self._on_refresh)

        self.btn_find = QPushButton("Kulaklığı bul")
        self.btn_find.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_find.setToolTip("Kulaklıktan bulma sesi çaldırır (Xiaomi Earbuds uyumlu)")
        self.btn_find.setIconSize(QSize(15, 15))
        self.btn_find.clicked.connect(self.find_requested)

        self.btn_diag = QPushButton("Tanılama")
        self.btn_diag.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_diag.setIconSize(QSize(15, 15))
        self.btn_diag.clicked.connect(self.diagnostics_requested)

        self.btn_settings = QPushButton("Ayarlar")
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setIconSize(QSize(15, 15))
        self.btn_settings.clicked.connect(self.settings_requested)

        for b in (self.btn_refresh, self.btn_find, self.btn_diag, self.btn_settings):
            head.addWidget(b)
        outer.addLayout(head)

        # ---- 3 sütunlu simetrik ana ızgara
        grid = QGridLayout()
        grid.setSpacing(16)
        self.card_left = BatteryCard("left")
        self.card_right = BatteryCard("right")
        self.card_case = BatteryCard("case")
        grid.addWidget(self.card_left, 0, 0)
        grid.addWidget(self.card_right, 0, 1)
        grid.addWidget(self.card_case, 0, 2)

        self.session = SessionPanel()
        self.card_bt = InfoCard(
            "BLUETOOTH BAĞLANTISI",
            "blue",
            [
                ("status", "Durum"),
                ("device", "Model"),
                ("address", "MAC Adresi"),
                ("firmware", "Firmware"),
                ("adapter", "Adaptör"),
                ("winbat", "Windows Pil"),
            ],
        )
        self.card_sys = InfoCard(
            "SİSTEM & PROTOKOL",
            "purple",
            [
                ("updated", "Son Okuma"),
                ("source", "Kaynak"),
                ("protocol", "Protokol"),
                ("auto", "Algılama"),
                ("interval", "Yenileme"),
            ],
        )
        grid.addWidget(self.session, 1, 0)
        grid.addWidget(self.card_bt, 1, 1)
        grid.addWidget(self.card_sys, 1, 2)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        grid.setRowStretch(1, 1)
        outer.addLayout(grid, 1)

        foot = QHBoxLayout()
        self.footer = QLabel(f"{DEVELOPER}  ·  v{APP_VERSION}")
        self.footer.setProperty("role", "faint")
        self.hint = QLabel("")
        self.hint.setProperty("role", "faint")
        foot.addWidget(self.footer)
        foot.addStretch()
        foot.addWidget(self.hint)
        outer.addLayout(foot)

        self._ticker = QTimer(self)
        self._ticker.setInterval(5000)
        self._ticker.timeout.connect(self._tick)
        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._update_session)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(240)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.apply_theme()

    # ------------------------------------------------------------------ tema
    def apply_theme(self) -> None:
        p = theme.get(self.settings.theme)
        self.setStyleSheet(theme.stylesheet(p))
        self.brand.setText(
            f"<span style='font-size:19px;font-weight:800;color:{p.text};letter-spacing:0.6px'>SPEXRON</span>"
            f"<span style='font-size:19px;font-weight:400;color:{p.blue}'> Buds Monitor</span>"
        )
        self.btn_refresh.setIcon(ui_icon("refresh", "#FFFFFF", 15))
        self._sync_find_button(self.state.finding)
        self.btn_diag.setIcon(ui_icon("diag", p.text, 15))
        self.btn_settings.setIcon(ui_icon("settings", p.text, 15))
        for w in (self.card_left, self.card_right, self.card_case, self.card_bt, self.card_sys, self.pill, self.session):
            w.set_palette(p)
        self.update_state(self.state)

    def _sync_find_button(self, finding: str | None) -> None:
        p = theme.get(self.settings.theme)
        if finding:
            self.btn_find.setText("Çalıyor…")
            self.btn_find.setIcon(ui_icon("sound", p.blue, 15))
            self.btn_find.setProperty("subtle", True)
        else:
            self.btn_find.setText("Kulaklığı bul")
            self.btn_find.setIcon(ui_icon("sound", p.text, 15))
            self.btn_find.setProperty("subtle", False)
        self.btn_find.style().unpolish(self.btn_find)
        self.btn_find.style().polish(self.btn_find)

    # ------------------------------------------------------------- olaylar
    def showEvent(self, e):
        self._ticker.start()
        self._clock.start()
        self.setWindowOpacity(0.0)
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self.update_state(self.state)
        super().showEvent(e)

    def hideEvent(self, e):
        self._ticker.stop()
        self._clock.stop()
        super().hideEvent(e)

    def closeEvent(self, e):
        e.ignore()
        self.close_requested.emit()

    def changeEvent(self, e):
        if e.type() == e.Type.WindowStateChange and self.isMinimized() and self.settings.minimize_to_tray:
            QTimer.singleShot(0, self.hide)
        super().changeEvent(e)

    def _on_refresh(self):
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("Yenileniyor…")
        QTimer.singleShot(1500, lambda: (self.btn_refresh.setEnabled(True), self.btn_refresh.setText("Yenile")))
        self.refresh_requested.emit()

    def _tick(self):
        s = self.state.snapshot
        self.card_sys.set("updated", ago(s.updated_at))
        self._update_case_note()

    # ------------------------------------------------------------- oturum
    def _update_session(self) -> None:
        st = self.state
        p = theme.get(self.settings.theme)
        now = datetime.now().timestamp()
        live = (st.protocol_ready or st.fallback_active) and st.acl_connected
        usage = session_history.usage_text(st.snapshot.battery) if live else ""
        if st.acl_connected and st.connected_since:
            self.session.set_timer(hms(now - st.connected_since), "live")
            self.session.since.setText(stamp(st.connected_since))
            self.session.usage.setText(usage or "Aktif kullanım")
        elif st.acl_connected and live and session_history.buds_in_use(st.snapshot.battery) == (False, False):
            self.session.set_timer("--:--:--", "case")
            self.session.since.setText("Beklemede")
            self.session.usage.setText(usage or "İki kulaklık da kutuda")
        else:
            self.session.set_timer("--:--:--", "idle")
            self.session.since.setText("Bağlı değil")
            self.session.usage.setText("Bağlantı bekleniyor")

        d = st.last_disconnect
        if d is None:
            self.session.set_badge("Kayıt yok", "")
            self.session.last.setText("Henüz kaydedilmedi")
            self.session.lasted.setText("Koptuğunda otomatik işlenir")
            return
        self.session.last.setText(stamp(d.time))
        summary = f"{human(d.duration)} kaldı"
        if d.detail:
            summary += f" · {d.detail}"
        self.session.lasted.setText(summary)
        color = {"battery_empty": p.red, "in_case": p.blue, "radio_off": p.amber}.get(d.reason, p.amber)
        self.session.set_badge(d.reason_text, color)

    # ------------------------------------------------------------- veri
    def _update_case_note(self):
        st = self.state
        case = st.snapshot.battery.case
        note = ""
        if case.level is None and st.protocol_ready:
            note = "Kutu verisi kapak açıkken okunur."
            if st.last_case:
                lvl, _ch, ts = st.last_case
                note = f"Son bilinen: %{lvl} · {ago(ts)}"
        self.card_case.note.setText(note or " ")

    def update_state(self, st: LinkState) -> None:
        self.state = st
        p = theme.get(self.settings.theme)
        b = st.snapshot.battery
        live = (st.protocol_ready or st.fallback_active) and st.acl_connected
        if live:
            self.card_left.set_data(b.left.level, b.left.charging)
            self.card_right.set_data(b.right.level, b.right.charging)
            self.card_case.set_data(b.case.level, b.case.charging)
        else:
            for c in (self.card_left, self.card_right, self.card_case):
                c.set_data(None, False)
        self._update_case_note()

        dev = st.device
        model_label = st.snapshot.model or (dev.name if dev else "")
        self.subtitle.setText(
            f"{model_label} · Canlı pil & oturum telemetrisi" if model_label else "Xiaomi Bluetooth kulaklık pil & oturum monitörü"
        )

        if st.acl_connected and st.protocol_ready:
            self.pill.set_status("Bağlı", p.green, True)
        elif st.acl_connected and st.fallback_active:
            self.pill.set_status("Bağlı · yedek", p.amber, True)
        elif st.acl_connected:
            self.pill.set_status("Veri bekleniyor" if not st.error else "Pil verisi yok", p.amber, True)
        else:
            self.pill.set_status("Bağlı değil", p.red, False)

        self.card_bt.set("status", st.status_text, p.green if live else (p.amber if st.acl_connected else p.red))
        self.card_bt.set("device", model_label or "--")
        self.card_bt.set("address", dev.address_str if dev else "--")
        self.card_bt.set("firmware", st.snapshot.firmware or "--")
        ad = st.adapter
        self.card_bt.set("adapter", ad.name if ad else "--", tooltip=f"{ad.name} ({ad.address})" if ad else "")
        self.card_bt.set("winbat", f"%{st.windows_battery} (birleşik)" if st.windows_battery is not None else "--")

        self.card_sys.set("updated", ago(st.snapshot.updated_at))
        src = {
            "device_info": "Cihaz sorgusu",
            "status_report": "Anlık bildirim",
            "fastpair": "Fast Pair BLE",
        }
        self.card_sys.set("source", src.get(st.snapshot.source, "--"))
        if st.protocol_ready:
            self.card_sys.set("protocol", "Xiaomi FD2D · Aktif", p.green)
        elif st.fallback_active:
            self.card_sys.set("protocol", "Fast Pair (yedek)", p.amber)
        elif st.error:
            self.card_sys.set("protocol", st.error, p.red)
        else:
            self.card_sys.set("protocol", "--")
        self.card_sys.set(
            "auto",
            "Otomatik · olay tabanlı" if self.settings.auto_detect else f"Sabit · {self.settings.device_address or '--'}",
        )
        self.card_sys.set("interval", f"{self.settings.refresh_interval} sn + anlık")
        self.hint.setText("Bağlantı kesilince otomatik kapanır")
        self._sync_find_button(st.finding)
        self._update_session()

