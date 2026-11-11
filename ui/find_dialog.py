"""'Kulaklığınızı bulun' penceresi — Xiaomi Earbuds uygulamasındaki özelliğin PC sürümü.

Komut: FD2D SET_CONFIG (0xF2), yapılandırma 0x09 → [1=çal/0=dur][1=sol, 2=sağ, 3=ikisi].
"""
from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from services.config import Settings

from . import theme
from .graphics import app_icon, draw_earbud, ui_icon
from .widgets import Card


class PulseRing(QWidget):
    """Çalma sırasında dışa doğru yayılan halkalar; ortada sol + sağ kulaklık silüeti."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(260, 188)
        self.palette_ = theme.DARK
        self.target: str | None = None
        self.selected = "BOTH"
        self._phase = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(1500)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._on_anim)

    def set_palette(self, p: theme.Palette) -> None:
        self.palette_ = p
        self.update()

    def set_state(self, target: str | None, selected: str) -> None:
        self.target, self.selected = target, selected
        if target and self.isVisible():
            if self._anim.state() != QVariantAnimation.State.Running:
                self._anim.start()
        elif not target:
            self._anim.stop()
            self._phase = 0.0
        self.update()

    def _on_anim(self, v) -> None:
        self._phase = float(v)
        self.update()

    def showEvent(self, e):
        if self.target:
            self._anim.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._anim.stop()
        super().hideEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette_
        dark = pal.name == "dark"
        w, h = self.width(), self.height()
        spots = {"LEFT": QPointF(w * 0.30, h * 0.46), "RIGHT": QPointF(w * 0.70, h * 0.46)}

        def lit(side: str) -> bool:
            t = self.target or self.selected
            return t in (side, "BOTH")

        if self.target:
            for side, c in spots.items():
                if not lit(side):
                    continue
                accent = QColor(pal.blue if side == "LEFT" else pal.purple)
                for k in range(3):
                    t = (self._phase + k / 3) % 1.0
                    col = QColor(accent)
                    col.setAlphaF(0.55 * (1 - t))
                    p.setPen(QPen(col, 2.0))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    r = 34 + t * 44
                    p.drawEllipse(c, r, r)

        f = self.font()
        f.setPointSize(9)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)

        for side, c in spots.items():
            on = lit(side)
            accent = pal.blue if side == "LEFT" else pal.purple
            halo = QColor(accent)
            halo.setAlphaF((0.20 if self.target else 0.12) if on else 0.04)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            p.drawEllipse(c, 38, 38)
            if on:
                body, shade = ("#F1F5F9", "#94A3B8") if dark else ("#FFFFFF", "#CBD5E1")
            else:
                body, shade = ("#475569", "#334155") if dark else ("#CBD5E1", "#94A3B8")
            draw_earbud(p, QRectF(c.x() - 26, c.y() - 28, 52, 56), side == "RIGHT", body,
                        accent if on else shade, shade)
            p.setPen(QColor(pal.text if on else pal.text_faint))
            p.drawText(QRectF(c.x() - 32, c.y() + 44, 64, 20), Qt.AlignmentFlag.AlignCenter,
                       "SOL" if side == "LEFT" else "SAĞ")


class FindDialog(QDialog):
    find_requested = Signal(str)   # LEFT | RIGHT | BOTH
    stop_requested = Signal()

    TARGETS = (("LEFT", "Sol"), ("BOTH", "Her ikisi"), ("RIGHT", "Sağ"))

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Kulaklığınızı bulun — SPEXRON Buds Monitor")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(480)
        self._target = "BOTH"
        self._finding: str | None = None
        self._until: float | None = None
        self._available = False
        self._pending = False

        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(22, 20, 22, 20)

        head = QVBoxLayout()
        head.setSpacing(2)
        title = QLabel("Kulaklığınızı bulun")
        title.setProperty("role", "h1")
        head.addWidget(title)
        lay.addLayout(head)

        warn_box = QFrame()
        warn_box.setObjectName("BannerWarn")
        wl = QVBoxLayout(warn_box)
        wl.setContentsMargins(12, 9, 12, 9)
        warn = QLabel(
            "Kulaklık yüksek sesle çalar. Başlatmadan önce kulaklığı kulağınızdan çıkarın ve kutunun dışına alın."
        )
        warn.setWordWrap(True)
        warn.setProperty("role", "dim")
        wl.addWidget(warn)
        lay.addWidget(warn_box)

        self.stage = Card("blue")
        st_lay = QVBoxLayout(self.stage)
        st_lay.setContentsMargins(14, 12, 14, 12)
        st_lay.setSpacing(6)
        self.ring = PulseRing()
        rr = QHBoxLayout()
        rr.addStretch()
        rr.addWidget(self.ring)
        rr.addStretch()
        st_lay.addLayout(rr)
        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setProperty("role", "value")
        st_lay.addWidget(self.status)
        lay.addWidget(self.stage)

        seg_wrap = QFrame()
        seg_wrap.setObjectName("SegContainer")
        seg = QHBoxLayout(seg_wrap)
        seg.setContentsMargins(5, 5, 5, 5)
        seg.setSpacing(6)
        self.target_btns: dict[str, QPushButton] = {}
        for key, text in self.TARGETS:
            b = QPushButton(text)
            b.setObjectName("SegBtn")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self._select(k))
            self.target_btns[key] = b
            seg.addWidget(b, 1)
        lay.addWidget(seg_wrap)

        self.btn_main = QPushButton()
        self.btn_main.setMinimumHeight(42)
        self.btn_main.setIconSize(QSize(15, 15))
        self.btn_main.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_main.clicked.connect(self._on_main)
        lay.addWidget(self.btn_main)

        self.hint = QLabel("")
        self.hint.setProperty("role", "faint")
        self.hint.setWordWrap(True)
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.hint)

        self._countdown = QTimer(self)
        self._countdown.setInterval(1000)
        self._countdown.timeout.connect(self._refresh)
        self.apply_theme()
        self._select("BOTH")

    def apply_theme(self) -> None:
        pal = theme.get(self.settings.theme)
        self.setStyleSheet(theme.stylesheet(pal))
        self.stage.set_palette(pal)
        self.ring.set_palette(pal)
        self._refresh()

    # ------------------------------------------------------------ eylemler
    def _select(self, key: str) -> None:
        self._target = key
        for k, b in self.target_btns.items():
            b.setChecked(k == key)
        if self._finding and self._finding != key:
            self._send_find(key)
        self._refresh()

    def _send_find(self, target: str) -> None:
        self._pending = True
        self.find_requested.emit(target)
        QTimer.singleShot(2500, self._clear_pending)

    def _clear_pending(self) -> None:
        self._pending = False
        self._refresh()

    def _on_main(self) -> None:
        if self._finding:
            self._pending = True
            self.stop_requested.emit()
            QTimer.singleShot(2500, self._clear_pending)
        else:
            self._send_find(self._target)
        self._refresh()

    def start_now(self, target: str = "BOTH") -> None:
        """Tepsi menüsü / komut satırından doğrudan başlatma."""
        self._target = target
        for k, b in self.target_btns.items():
            b.setChecked(k == target)
        if self._finding != target:
            self._send_find(target)
        self._refresh()

    # ------------------------------------------------------------ durum
    def update_state(self, st) -> None:
        self._available = bool(st.acl_connected and st.protocol_ready)
        changed = st.finding != self._finding
        self._finding = st.finding
        self._until = st.finding_until
        if changed:
            self._pending = False
        if st.finding in self.target_btns:
            self._target = st.finding
            for k, b in self.target_btns.items():
                b.setChecked(k == st.finding)
        if st.find_error and not st.finding:
            self._pending = False
            self.hint.setText(f"Komut gönderilemedi: {st.find_error}")
        elif not self._available:
            self.hint.setText(
                "Kulaklık PC'ye bağlı değil ya da Xiaomi FD2D oturumu açık değil. "
                "Telefonda Xiaomi Earbuds uygulaması açıksa kapatıp tekrar deneyin."
            )
        else:
            self.hint.setText(f"Ses {self.settings.find_duration} sn sonra kendiliğinden durur (Ayarlar'dan değiştirilebilir).")
        self._refresh()

    def _refresh(self) -> None:
        pal = theme.get(self.settings.theme)
        names = dict(self.TARGETS)
        finding = self._finding
        self.ring.set_state(finding, self._target)
        if finding:
            left = max(0, int((self._until or 0) - time.time()))
            which = "İki kulaklık" if finding == "BOTH" else f"{names[finding]} kulaklık"
            self.status.setText(f"{which} çalıyor…  {left} sn")
            self.status.setStyleSheet(f"color: {pal.blue};")
            self.btn_main.setText("Durdur")
            self.btn_main.setIcon(ui_icon("stop", "#FFFFFF", 15))
            self.btn_main.setProperty("accent", False)
            self.btn_main.setProperty("danger", True)
            self.btn_main.setEnabled(not self._pending)
            if not self._countdown.isActive():
                self._countdown.start()
        else:
            self._countdown.stop()
            self.status.setText("Gönderiliyor…" if self._pending else ("Hazır" if self._available else "Bağlı değil"))
            self.status.setStyleSheet(f"color: {pal.green if self._available else pal.text_faint};")
            self.btn_main.setText("Çalmaya başla")
            self.btn_main.setIcon(ui_icon("play", "#FFFFFF" if self._available else pal.text_faint, 15))
            self.btn_main.setProperty("accent", True)
            self.btn_main.setProperty("danger", False)
            self.btn_main.setEnabled(self._available and not self._pending)
        self.btn_main.style().unpolish(self.btn_main)
        self.btn_main.style().polish(self.btn_main)

