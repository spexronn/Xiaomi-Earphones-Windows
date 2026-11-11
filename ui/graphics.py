"""Vektör çizimler: kulaklık, şarj kutusu, arayüz simgeleri ve tepsi simgesi."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)


def _grad(rect: QRectF, c1: str, c2: str) -> QLinearGradient:
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0, QColor(c1))
    g.setColorAt(1, QColor(c2))
    return g


def draw_earbud(p: QPainter, rect: QRectF, mirrored: bool, body: str, accent: str, shade: str) -> None:
    """Ergonomik, derinlik gölgeli kulak içi kulaklık vektör çizimi."""
    p.save()
    p.translate(rect.center())
    s = min(rect.width(), rect.height()) / 100.0
    p.scale(-s if mirrored else s, s)

    head = QPainterPath()
    head.addEllipse(QPointF(-5, -18), 28, 25)
    stem = QPainterPath()
    stem.addRoundedRect(QRectF(5, -12, 15.5, 58), 7.75, 7.75)
    shape = head.united(stem)

    # yumuşak düşme gölgesi
    p.save()
    p.translate(1.5, 2.5)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 38))
    p.drawPath(shape)
    p.restore()

    # ana gövde gradyanı + ince kenar konturu
    p.setPen(QPen(QColor(255, 255, 255, 55), 1.4))
    p.setBrush(QBrush(_grad(QRectF(-33, -43, 56, 94), body, shade)))
    p.drawPath(shape)

    # silikon kulak ucu
    tip = QPainterPath()
    tip.addEllipse(QPointF(-26, -19), 11.5, 13.5)
    p.setPen(QPen(QColor(0, 0, 0, 35), 1.0))
    p.setBrush(QBrush(_grad(QRectF(-38, -32, 23, 27), shade, body)))
    p.drawPath(tip)

    # kök üzerinde metalik dokunmatik şerit
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 58))
    p.drawRoundedRect(QRectF(9.5, -2, 6, 36), 3, 3)

    # vurgu LED / akustik sensör
    glow = QRadialGradient(QPointF(-2, -23), 8)
    ac = QColor(accent)
    ac.setAlpha(110)
    glow.setColorAt(0, ac)
    glow.setColorAt(1, QColor(0, 0, 0, 0))
    p.setBrush(glow)
    p.drawEllipse(QPointF(-2, -23), 8, 8)
    p.setBrush(QColor(accent))
    p.drawEllipse(QPointF(-2, -23), 4.2, 4.2)

    # üst specular parlama
    p.setBrush(QColor(255, 255, 255, 52))
    p.drawEllipse(QPointF(0, -33), 13, 5.5)
    p.restore()


def draw_case(p: QPainter, rect: QRectF, body: str, accent: str, shade: str) -> None:
    """Modern pebble şarj kutusu vektör çizimi."""
    p.save()
    p.translate(rect.center())
    s = min(rect.width(), rect.height()) / 100.0
    p.scale(s, s)
    r = QRectF(-44, -30, 88, 62)

    # alt düşme gölgesi
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 40))
    p.drawRoundedRect(r.adjusted(1.5, 3, 1.5, 3), 29, 29)

    # gövde + kenar konturu
    p.setPen(QPen(QColor(255, 255, 255, 52), 1.4))
    p.setBrush(QBrush(_grad(r, body, shade)))
    p.drawRoundedRect(r, 29, 29)

    # kapak ayrım çizgisi ve üst kenar ışığı
    p.setPen(QPen(QColor(0, 0, 0, 75), 1.8))
    p.drawLine(QPointF(-41, -7), QPointF(41, -7))
    p.setPen(QPen(QColor(255, 255, 255, 50), 1.0))
    p.drawLine(QPointF(-39, -5.5), QPointF(39, -5.5))

    # durum LED halkası + parlak çekirdek
    glow = QRadialGradient(QPointF(0, 9), 11)
    ac = QColor(accent)
    ac.setAlpha(120)
    glow.setColorAt(0, ac)
    glow.setColorAt(1, QColor(0, 0, 0, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawEllipse(QPointF(0, 9), 11, 11)
    p.setBrush(QColor(accent))
    p.drawRoundedRect(QRectF(-7, 7, 14, 4.2), 2.1, 2.1)

    # kapak parlaması
    p.setBrush(QColor(255, 255, 255, 48))
    p.drawRoundedRect(QRectF(-28, -25, 56, 8.5), 4.2, 4.2)
    p.restore()


def ui_icon(kind: str, color: str, size: int = 16) -> QIcon:
    """Buton ve durum çubukları için keskin HiDPI vektör ikon."""
    scale = 2
    px = size * scale
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(scale)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24.0, size / 24.0)
    c = QColor(color)
    pen = QPen(c, 2.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    if kind == "refresh":
        p.drawArc(QRectF(4, 4, 16, 16), 35 * 16, 285 * 16)
        head = QPainterPath()
        head.moveTo(19.5, 4.5)
        head.lineTo(19.5, 9.5)
        head.lineTo(14.5, 9.5)
        p.drawPath(head)
    elif kind == "sound":
        spk = QPainterPath()
        spk.moveTo(4, 9.5); spk.lineTo(8, 9.5); spk.lineTo(13, 5.5)
        spk.lineTo(13, 18.5); spk.lineTo(8, 14.5); spk.lineTo(4, 14.5); spk.closeSubpath()
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 45))
        p.drawPath(spk)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(12.5, 8.5, 6, 7), -55 * 16, 110 * 16)
        p.drawArc(QRectF(13.5, 5.5, 9, 13), -55 * 16, 110 * 16)
    elif kind == "diag":
        wave = QPainterPath()
        wave.moveTo(2.5, 12); wave.lineTo(6.5, 12); wave.lineTo(9.5, 5)
        wave.lineTo(14, 19); wave.lineTo(17.5, 12); wave.lineTo(21.5, 12)
        p.drawPath(wave)
    elif kind == "settings":
        p.drawLine(4, 7, 20, 7)
        p.drawLine(4, 17, 20, 17)
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 45))
        p.drawEllipse(QPointF(9, 7), 2.7, 2.7)
        p.drawEllipse(QPointF(15, 17), 2.7, 2.7)
    elif kind == "play":
        tri = QPainterPath()
        tri.moveTo(7, 5); tri.lineTo(19, 12); tri.lineTo(7, 19); tri.closeSubpath()
        p.setBrush(c)
        p.drawPath(tri)
    elif kind == "stop":
        p.setBrush(c)
        p.drawRoundedRect(QRectF(6, 6, 12, 12), 2.2, 2.2)
    elif kind == "logs":
        p.drawRoundedRect(QRectF(5, 3.5, 14, 17), 2.5, 2.5)
        p.drawLine(8.5, 8.5, 15.5, 8.5)
        p.drawLine(8.5, 12, 15.5, 12)
        p.drawLine(8.5, 15.5, 13, 15.5)
    elif kind == "folder":
        fld = QPainterPath()
        fld.moveTo(3.5, 7); fld.lineTo(9.5, 7); fld.lineTo(11.5, 9.5); fld.lineTo(20.5, 9.5)
        fld.lineTo(20.5, 18.5); fld.lineTo(3.5, 18.5); fld.closeSubpath()
        p.drawPath(fld)
    elif kind == "check":
        chk = QPainterPath()
        chk.moveTo(5, 12.5); chk.lineTo(10, 17.5); chk.lineTo(19.5, 7)
        p.drawPath(chk)
    p.end()
    return QIcon(pm)


def app_icon(size: int = 256) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92)
    p.setPen(QPen(QColor("#38BDF8"), max(1.5, size * 0.015)))
    p.setBrush(QBrush(_grad(r, "#1E293B", "#0F172A")))
    p.drawRoundedRect(r, size * 0.24, size * 0.24)
    # üst stüdyo parıltısı
    shine = QLinearGradient(r.topLeft(), QPointF(r.left(), r.center().y()))
    shine.setColorAt(0, QColor(56, 189, 248, 55))
    shine.setColorAt(1, QColor(0, 0, 0, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(shine)
    p.drawRoundedRect(r, size * 0.24, size * 0.24)

    draw_earbud(p, QRectF(size * 0.13, size * 0.18, size * 0.48, size * 0.68), False, "#F8FAFC", "#38BDF8", "#CBD5E1")
    draw_earbud(p, QRectF(size * 0.39, size * 0.18, size * 0.48, size * 0.68), True, "#F8FAFC", "#A78BFA", "#CBD5E1")
    p.end()
    icon = QIcon()
    for s in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(pm.scaled(s, s, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    return icon


def tray_icon(level: int | None, connected: bool, charging: bool, color: str) -> QIcon:
    """Tepsi simgesi: kulaklık + seviyeyi gösteren keskin halka."""
    size = 64
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    ring = QRectF(5, 5, 54, 54)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(9, 13, 22, 242))
    p.drawEllipse(QRectF(2, 2, 60, 60))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(148, 163, 184, 85), 6.5))
    p.drawEllipse(ring)
    if connected and level is not None:
        p.setPen(QPen(QColor(color), 6.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(ring, 90 * 16, -int(360 * 16 * max(0, min(100, level)) / 100))
    if level is not None and connected:
        p.setPen(QColor("#FFFFFF"))
        f = QFont("Segoe UI", 22 if level < 100 else 17)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, str(level))
    else:
        draw_earbud(p, QRectF(14, 12, 36, 42), False, "#F1F5F9", "#38BDF8", "#94A3B8")
    if charging:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FBBF24"))
        bolt = QPainterPath()
        bolt.moveTo(50, 36); bolt.lineTo(42, 50); bolt.lineTo(48, 50)
        bolt.lineTo(45, 62); bolt.lineTo(56, 46); bolt.lineTo(50, 46); bolt.closeSubpath()
        p.drawPath(bolt)
    p.end()
    return QIcon(pm)

