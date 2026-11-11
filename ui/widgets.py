from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import theme
from .graphics import draw_case, draw_earbud


class Card(QFrame):
    """Modern yüzey kartı: keskin kenar çizgisi, yumuşak üst ışık ve hover vurgusu."""

    def __init__(self, accent: str = "blue", parent=None) -> None:
        super().__init__(parent)
        self.palette_ = theme.DARK
        self.accent = accent
        self._hover = 0.0
        self._anim = QPropertyAnimation(self, b"hover", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def set_palette(self, p: theme.Palette) -> None:
        self.palette_ = p
        self.update()

    def _get_hover(self) -> float:
        return self._hover

    def _set_hover(self, v: float) -> None:
        self._hover = v
        self.update()

    hover = Property(float, _get_hover, _set_hover)

    def enterEvent(self, e):
        self._anim.stop()
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._anim.stop()
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette_
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        p.setPen(QPen(QColor(pal.card_border), 1.0))
        p.setBrush(QColor(pal.card))
        p.drawRoundedRect(r, 16, 16)

        # hafif üst vurgu şeridi
        ac = QColor(getattr(pal, self.accent))
        wash = QLinearGradient(r.topLeft(), QPointF(r.left(), r.top() + 56))
        top_c = QColor(ac)
        top_c.setAlphaF((0.05 if pal.name == "dark" else 0.03) + 0.08 * self._hover)
        wash.setColorAt(0, top_c)
        wash.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(wash)
        p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 15, 15)

        if self._hover > 0.01:
            border_c = QColor(ac)
            border_c.setAlphaF(0.65 * self._hover)
            p.setPen(QPen(border_c, 1.3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, 16, 16)


class BatteryBar(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(8)
        self.palette_ = theme.DARK
        self._value = 0.0
        self._target: int | None = None
        self.charging = False
        self._shimmer = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(800)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    def set_palette(self, p):
        self.palette_ = p
        self.update()

    def _on_anim(self, v):
        self._value = float(v)
        self.update()

    def _tick(self):
        self._shimmer = (self._shimmer + 0.02) % 1.4
        self.update()

    def set_level(self, level: int | None, charging: bool) -> None:
        self.charging = charging and level is not None
        if level != self._target:
            self._target = level
            self._anim.stop()
            self._anim.setStartValue(self._value)
            self._anim.setEndValue(float(level or 0))
            self._anim.start()
        self._update_timer()
        self.update()

    def _update_timer(self):
        if self.charging and self.isVisible():
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def showEvent(self, e):
        self._update_timer()
        super().showEvent(e)

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette_
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(pal.track))
        p.drawRoundedRect(r, 4, 4)

        if self._target is None and self._value < 0.5:
            return
        w = r.width() * max(0.0, min(100.0, self._value)) / 100.0
        if w < 2:
            return

        fill = QRectF(r.left(), r.top(), w, r.height())
        base = QColor(theme.level_color(pal, self._target if self._target is not None else int(self._value)))
        g = QLinearGradient(fill.topLeft(), fill.topRight())
        g.setColorAt(0, base.darker(110))
        g.setColorAt(1, base.lighter(118))
        p.setBrush(g)
        p.drawRoundedRect(fill, 4, 4)

        if self.charging:
            x = r.left() + (self._shimmer - 0.2) * r.width()
            sg = QLinearGradient(x - 36, 0, x + 36, 0)
            sg.setColorAt(0, QColor(255, 255, 255, 0))
            sg.setColorAt(0.5, QColor(255, 255, 255, 130))
            sg.setColorAt(1, QColor(255, 255, 255, 0))
            p.setClipRect(fill)
            p.setBrush(sg)
            p.drawRoundedRect(fill, 4, 4)


class DeviceArt(QWidget):
    """Dairesel pil halkası içinde yüksek kaliteli kulaklık/kutu çizimi."""

    def __init__(self, kind: str, parent=None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.palette_ = theme.DARK
        self.active = False
        self.level: int | None = None
        self.charging = False
        self.setFixedSize(90, 90)

    def set_palette(self, p):
        self.palette_ = p
        self.update()

    def set_metrics(self, level: int | None, charging: bool) -> None:
        self.level = level
        self.charging = charging and level is not None
        self.active = level is not None
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette_
        channel_accent = {"left": pal.blue, "right": pal.purple, "case": pal.green}[self.kind]
        ring_color = theme.level_color(pal, self.level) if self.active else pal.track

        # arka halo
        halo = QColor(channel_accent)
        halo.setAlphaF(0.11 if self.active else 0.04)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QRectF(5, 5, 80, 80))

        # dış halka izi + canlı pil yayı
        ring = QRectF(5, 5, 80, 80)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(pal.track), 4.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(ring, -225 * 16, 270 * 16)
        if self.active and self.level is not None and self.level > 0:
            span = -int(270 * 16 * max(0, min(100, self.level)) / 100.0)
            p.setPen(QPen(QColor(ring_color), 4.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(ring, 225 * 16, span)

        dark = pal.name == "dark"
        if self.active:
            body = "#F1F5F9" if dark else "#FFFFFF"
            shade = "#94A3B8" if dark else "#CBD5E1"
        else:
            body, shade = ("#475569", "#334155") if dark else ("#CBD5E1", "#94A3B8")

        if self.kind == "case":
            draw_case(p, QRectF(13, 15, 64, 60), body, channel_accent if self.active else shade, shade)
        else:
            draw_earbud(p, QRectF(17, 13, 56, 62), self.kind == "right", body, channel_accent if self.active else shade, shade)

        if self.charging:
            # sağ üstte şarj şimşeği rozeti
            badge = QRectF(63, 6, 20, 20)
            p.setPen(QPen(QColor(pal.card), 2.0))
            p.setBrush(QColor(pal.amber))
            p.drawEllipse(badge)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#0F172A"))
            bolt = QPainterPath()
            bolt.moveTo(74.5, 10.5); bolt.lineTo(69.5, 16.5); bolt.lineTo(72.8, 16.5)
            bolt.lineTo(71.2, 21.5); bolt.lineTo(76.8, 15.2); bolt.lineTo(73.4, 15.2)
            bolt.closeSubpath()
            p.drawPath(bolt)


class BatteryCard(Card):
    TITLES = {"left": "SOL KULAKLIK", "right": "SAĞ KULAKLIK", "case": "ŞARJ KUTUSU"}
    ACCENT = {"left": "blue", "right": "purple", "case": "green"}

    def __init__(self, kind: str, parent=None) -> None:
        super().__init__(self.ACCENT[kind], parent)
        self.kind = kind
        self._level: int | None = None
        self._charging = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 15)
        lay.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(7)
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        self.title = QLabel(self.TITLES[kind])
        self.title.setProperty("role", "title")
        self.badge = QLabel("")
        self.badge.setVisible(False)
        head.addWidget(self.dot)
        head.addWidget(self.title)
        head.addStretch()
        head.addWidget(self.badge)
        lay.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(14)
        self.art = DeviceArt(kind)
        row.addWidget(self.art)
        vals = QVBoxLayout()
        vals.setSpacing(2)
        self.value = QLabel("--")
        f = QFont("Segoe UI Variable Display", 32)
        f.setWeight(QFont.Weight.Bold)
        self.value.setFont(f)
        self.state = QLabel("Veri yok")
        self.state.setProperty("role", "dim")
        self.state.setWordWrap(True)
        vals.addStretch()
        vals.addWidget(self.value)
        vals.addWidget(self.state)
        vals.addStretch()
        row.addLayout(vals, 1)
        lay.addLayout(row)

        self.bar = BatteryBar()
        lay.addWidget(self.bar)
        self.note = QLabel(" ")
        self.note.setProperty("role", "faint")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)

    def set_palette(self, p: theme.Palette):
        super().set_palette(p)
        ch_color = getattr(p, self.accent)
        self.dot.setStyleSheet(f"background: {ch_color}; border-radius: 4px;")
        self.bar.set_palette(p)
        self.art.set_palette(p)
        self._recolor()

    def _recolor(self):
        pal = self.palette_
        lvl = self._level
        col = theme.level_color(pal, lvl) if lvl is not None else pal.text_faint
        self.value.setStyleSheet(f"color: {col};")
        if self._charging:
            self._set_badge("ŞARJDA", pal.amber)
        elif lvl is not None and lvl <= 15:
            self._set_badge("DÜŞÜK", pal.red)
        else:
            self.badge.setVisible(False)

    def _set_badge(self, text: str, color: str) -> None:
        self.badge.setText(text)
        self.badge.setStyleSheet(
            f"color: {color}; background: {theme.rgba(color, 0.14)};"
            f"border: 1px solid {theme.rgba(color, 0.4)};"
            "border-radius: 9px; padding: 2px 8px; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;"
        )
        self.badge.setVisible(True)

    def set_data(self, level: int | None, charging: bool, note: str = "") -> None:
        self._level = level
        self._charging = charging and level is not None
        self.value.setText("--" if level is None else f"%{level}")
        self.art.set_metrics(level, self._charging)
        if level is None:
            self.state.setText("Veri bekleniyor")
        elif self._charging:
            self.state.setText("Şarj oluyor")
        elif self.kind == "case":
            self.state.setText("Şarjda değil")
        else:
            self.state.setText("Kullanımda")
        self.note.setText(note or " ")
        self.bar.set_level(level, self._charging)
        self._recolor()


class InfoCard(Card):
    def __init__(self, title: str, accent: str, rows: list[tuple[str, str]], parent=None) -> None:
        super().__init__(accent, parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 15, 16, 15)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(7)
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        t = QLabel(title)
        t.setProperty("role", "title")
        head.addWidget(self.dot)
        head.addWidget(t)
        head.addStretch()
        lay.addLayout(head)

        self.sep = QFrame()
        self.sep.setFixedHeight(1)
        lay.addWidget(self.sep)

        rows_lay = QVBoxLayout()
        rows_lay.setSpacing(6)
        self.values: dict[str, QLabel] = {}
        self.row_boxes: list[QFrame] = []
        for key, label in rows:
            box = QFrame()
            box.setObjectName("InfoRowBox")
            rl = QHBoxLayout(box)
            rl.setContentsMargins(11, 6, 11, 6)
            rl.setSpacing(10)
            l = QLabel(label)
            l.setProperty("role", "dim")
            v = QLabel("--")
            v.setProperty("role", "value")
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            rl.addWidget(l)
            rl.addWidget(v, 1)
            rows_lay.addWidget(box)
            self.row_boxes.append(box)
            self.values[key] = v
        lay.addLayout(rows_lay)
        lay.addStretch(1)

    def set_palette(self, p: theme.Palette) -> None:
        super().set_palette(p)
        self.dot.setStyleSheet(f"background: {getattr(p, self.accent)}; border-radius: 4px;")
        self.sep.setStyleSheet(f"background: {p.card_border};")

    def set(self, key: str, text: str, color: str | None = None, tooltip: str = "") -> None:
        v = self.values[key]
        v.setText(text)
        v.setToolTip(tooltip)
        v.setStyleSheet(f"color: {color};" if color else "")


class SessionPanel(Card):
    """Canlı bağlantı süresi, kullanım özeti ve son kopma kaydı."""

    def __init__(self, parent=None) -> None:
        super().__init__("blue", parent)
        self._mode = "idle"  # live | case | idle
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 15, 16, 15)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(7)
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        t = QLabel("OTURUM ÖZETİ")
        t.setProperty("role", "title")
        self.live_badge = QLabel("BEKLEMEDE")
        head.addWidget(self.dot)
        head.addWidget(t)
        head.addStretch()
        head.addWidget(self.live_badge)
        lay.addLayout(head)

        self.sep = QFrame()
        self.sep.setFixedHeight(1)
        lay.addWidget(self.sep)

        # ---- 1. Kronometre kutusu (SA : DK : SN)
        self.clock_box = QFrame()
        self.clock_box.setObjectName("ClockBox")
        c_lay = QVBoxLayout(self.clock_box)
        c_lay.setContentsMargins(11, 9, 11, 9)
        c_lay.setSpacing(7)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)
        self.cap1 = QLabel("BAĞLANTI SÜRESİ")
        self.cap1.setProperty("role", "title")
        self.since = QLabel("Bağlı değil")
        self.since.setProperty("role", "faint")
        self.since.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top_bar.addWidget(self.cap1)
        top_bar.addStretch()
        top_bar.addWidget(self.since)
        c_lay.addLayout(top_bar)

        seg_row = QHBoxLayout()
        seg_row.setSpacing(6)
        self.seg_vals: list[QLabel] = []
        self.colons: list[QLabel] = []
        num_font = QFont("Cascadia Mono", 18)
        num_font.setWeight(QFont.Weight.Bold)
        num_font.setStyleHint(QFont.StyleHint.Monospace)
        colon_font = QFont("Cascadia Mono", 16)
        colon_font.setWeight(QFont.Weight.Bold)

        for idx, unit_lbl in enumerate(("SA", "DK", "SN")):
            seg = QFrame()
            seg.setObjectName("ChronoSeg")
            sl = QVBoxLayout(seg)
            sl.setContentsMargins(4, 5, 4, 5)
            sl.setSpacing(0)
            num = QLabel("--")
            num.setFont(num_font)
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cap = QLabel(unit_lbl)
            cap.setProperty("role", "faint")
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sl.addWidget(num)
            sl.addWidget(cap)
            seg_row.addWidget(seg, 1)
            self.seg_vals.append(num)
            if idx < 2:
                col = QLabel(":")
                col.setFont(colon_font)
                col.setAlignment(Qt.AlignmentFlag.AlignCenter)
                col.setFixedWidth(10)
                seg_row.addWidget(col)
                self.colons.append(col)
        c_lay.addLayout(seg_row)
        lay.addWidget(self.clock_box)

        # ---- 2. Kullanım durumu satır kutusu
        self.usage_box = QFrame()
        self.usage_box.setObjectName("InfoRowBox")
        ul = QHBoxLayout(self.usage_box)
        ul.setContentsMargins(11, 6, 11, 6)
        ul.setSpacing(10)
        u_lbl = QLabel("Durum")
        u_lbl.setProperty("role", "dim")
        self.usage = QLabel("Bağlantı bekleniyor")
        self.usage.setProperty("role", "value")
        self.usage.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        ul.addWidget(u_lbl)
        ul.addWidget(self.usage, 1)
        lay.addWidget(self.usage_box)

        # ---- 3. Son kopma kart kutusu
        self.last_box = QFrame()
        self.last_box.setObjectName("InfoRowBox")
        l_lay = QVBoxLayout(self.last_box)
        l_lay.setContentsMargins(11, 8, 11, 8)
        l_lay.setSpacing(5)

        l_head = QHBoxLayout()
        l_head.setSpacing(6)
        self.cap2 = QLabel("SON KOPMA")
        self.cap2.setProperty("role", "title")
        self.badge = QLabel("Kayıt yok")
        l_head.addWidget(self.cap2)
        l_head.addStretch()
        l_head.addWidget(self.badge)
        l_lay.addLayout(l_head)

        r_time = QHBoxLayout()
        r_time.setSpacing(8)
        lt1 = QLabel("Zaman")
        lt1.setProperty("role", "dim")
        self.last = QLabel("Henüz kaydedilmedi")
        self.last.setProperty("role", "value")
        self.last.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        r_time.addWidget(lt1)
        r_time.addWidget(self.last, 1)
        l_lay.addLayout(r_time)

        r_dur = QHBoxLayout()
        r_dur.setSpacing(8)
        lt2 = QLabel("Detay")
        lt2.setProperty("role", "dim")
        self.lasted = QLabel("Koptuğunda otomatik işlenir")
        self.lasted.setProperty("role", "dim")
        self.lasted.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        r_dur.addWidget(lt2)
        r_dur.addWidget(self.lasted, 1)
        l_lay.addLayout(r_dur)
        lay.addWidget(self.last_box)
        lay.addStretch(1)

    def set_palette(self, p: theme.Palette) -> None:
        super().set_palette(p)
        self.dot.setStyleSheet(f"background: {p.blue}; border-radius: 4px;")
        self.sep.setStyleSheet(f"background: {p.card_border};")
        self.clock_box.setStyleSheet(
            f"QFrame#ClockBox {{ background: {p.card_alt}; border: 1px solid {p.card_border}; border-radius: 11px; }}"
        )
        self._refresh_clock_colors()
        self._refresh_live_badge()

    def _refresh_clock_colors(self) -> None:
        p = self.palette_
        num_col = p.blue if self._mode == "live" else p.text
        for lbl in self.seg_vals:
            lbl.setStyleSheet(f"color: {num_col}; background: transparent;")
        for col in self.colons:
            col.setStyleSheet(f"color: {p.text}; background: transparent;")

    def _refresh_live_badge(self) -> None:
        p = self.palette_
        if self._mode == "live":
            txt, col = "CANLI", p.green
        elif self._mode == "case":
            txt, col = "KUTUDA", p.blue
        else:
            txt, col = "BEKLEMEDE", p.red
        self.live_badge.setText(txt)
        self.live_badge.setStyleSheet(
            f"color: {col}; background: {theme.rgba(col, 0.14)};"
            f"border: 1px solid {theme.rgba(col, 0.45)};"
            "border-radius: 9px; padding: 2px 8px; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;"
        )
        self.live_badge.setVisible(True)

    def set_timer(self, text: str, mode: str | bool) -> None:
        if isinstance(mode, bool):
            self._mode = "live" if mode else "idle"
        else:
            self._mode = mode
        parts = text.split(":") if ":" in text else ["--", "--", "--"]
        for i, lbl in enumerate(self.seg_vals):
            lbl.setText(parts[i] if i < len(parts) else "--")
        self._refresh_clock_colors()
        self._refresh_live_badge()

    def set_badge(self, text: str, color: str) -> None:
        p = self.palette_
        col = color or p.text
        self.badge.setText(text or "Kayıt yok")
        if color:
            self.badge.setStyleSheet(
                f"color: {col}; background: {theme.rgba(col, 0.14)};"
                f"border: 1px solid {theme.rgba(col, 0.42)};"
                "border-radius: 8px; padding: 2px 8px; font-size: 10.5px; font-weight: 600;"
            )
        else:
            self.badge.setStyleSheet(
                f"color: {p.text}; background: {p.track};"
                f"border: 1px solid {p.card_border};"
                "border-radius: 8px; padding: 2px 8px; font-size: 10.5px; font-weight: 600;"
            )
        self.badge.setVisible(True)


class Toggle(QCheckBox):
    """Animasyonlu modern açma/kapama anahtarı."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.palette_ = theme.DARK
        self._pos = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_pos", float(v)), self.update()))
        self.toggled.connect(self._animate)
        self.setMinimumHeight(30)

    def set_palette(self, p):
        self.palette_ = p
        self.update()

    def setChecked(self, on: bool) -> None:  # noqa: N802
        super().setChecked(on)
        self._anim.stop()
        self._pos = 1.0 if on else 0.0
        self.update()

    def _animate(self, on: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def hitButton(self, pos) -> bool:  # noqa: N802
        return self.rect().contains(pos)

    def sizeHint(self):
        s = super().sizeHint()
        s.setWidth(self.fontMetrics().horizontalAdvance(self.text()) + 62)
        return s

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette_
        h = 22
        track = QRectF(0, (self.height() - h) / 2, 40, h)
        off, on = QColor(pal.track), QColor(pal.green)
        c = QColor(
            int(off.red() + (on.red() - off.red()) * self._pos),
            int(off.green() + (on.green() - off.green()) * self._pos),
            int(off.blue() + (on.blue() - off.blue()) * self._pos),
        )
        if not self.isEnabled():
            c.setAlphaF(0.45)
        p.setPen(QPen(QColor(pal.card_border), 1.0) if self._pos < 0.5 else Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(track, h / 2, h / 2)
        d = h - 6
        x = track.left() + 3 + (track.width() - d - 6) * self._pos
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FFFFFF") if self._pos > 0.5 or pal.name == "light" else QColor(pal.text_dim))
        p.drawEllipse(QRectF(x, track.top() + 3, d, d))
        p.setPen(QColor(pal.text if self.isEnabled() else pal.text_faint))
        p.drawText(
            QRectF(track.right() + 12, 0, self.width() - track.right() - 12, self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.text(),
        )


class StatusPill(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.palette_ = theme.DARK
        self.text = "Başlatılıyor"
        self.color = "#8E9DB5"
        self._pulse = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(1600)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_pulse", float(v)), self.update()))
        self.setFixedHeight(32)

    def set_palette(self, p):
        self.palette_ = p
        self.update()

    def set_status(self, text: str, color: str, pulsing: bool) -> None:
        self.text, self.color = text, color
        fm = self.fontMetrics()
        self.setFixedWidth(fm.horizontalAdvance(text) + 46)
        if pulsing and self.isVisible():
            if self._anim.state() != QVariantAnimation.State.Running:
                self._anim.start()
        else:
            self._anim.stop()
            self._pulse = 0.0
        self.update()

    def hideEvent(self, e):
        self._anim.stop()
        super().hideEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        bg = QColor(self.color)
        bg.setAlphaF(0.13)
        border = QColor(self.color)
        border.setAlphaF(0.55)
        p.setPen(QPen(border, 1.0))
        p.setBrush(bg)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)

        c = QRectF(13, r.center().y() - 4, 8, 8)
        if self._pulse:
            halo = QColor(self.color)
            halo.setAlphaF(0.55 * (1 - self._pulse))
            d = 8 + 10 * self._pulse
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            p.drawEllipse(QRectF(17 - d / 2, r.center().y() - d / 2, d, d))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.color))
        p.drawEllipse(c)
        p.setPen(QColor(self.palette_.text))
        f = self.font()
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.drawText(r.adjusted(29, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text)

