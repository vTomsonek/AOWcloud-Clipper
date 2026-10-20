"""Logo programu rysowane w kodzie: z białej taśmy filmowej wycięty pomarańczowy kwadrat.

Styl rodziny AOWcloud (jak Reelmaker): ciemny kafel #141414, gradient #FF7A18 → #FFC21A.
Rysunek w układzie 512x512, skalowany do żądanego rozmiaru.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

DARK = "#141414"
STRIP = "#EDEDED"
GRAD = ("#FF7A18", "#FFC21A")


def _grad(r: QRectF) -> QLinearGradient:
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, QColor(GRAD[0]))
    g.setColorAt(1, QColor(GRAD[1]))
    return g


def _play(p: QPainter, cx: float, cy: float, h: float) -> None:
    w = h * 0.86
    x0 = cx - w / 3                       # środek ciężkości trójkąta w (cx, cy)
    p.setBrush(QColor(DARK))
    p.drawPolygon(QPolygonF([QPointF(x0, cy - h / 2), QPointF(x0, cy + h / 2),
                             QPointF(x0 + w, cy)]))


def _paint(p: QPainter, small: bool) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(DARK))
    p.drawRoundedRect(QRectF(0, 0, 512, 512), 112, 112)
    if small:
        # 16 i 24 px: sam kwadrat z odtwarzaniem, taśma byłaby nieczytelna
        r = QRectF(126, 126, 260, 260)
        p.setBrush(_grad(r))
        p.drawRoundedRect(r, 40, 40)
        _play(p, 262, 256, 104)
        return
    # dwa końce taśmy z perforacją, przerwa pośrodku
    y0, h = 196, 150
    for x0, x1 in ((40, 158), (354, 472)):
        p.setBrush(QColor(STRIP))
        p.drawRoundedRect(QRectF(x0, y0, x1 - x0, h), 18, 18)
        p.setBrush(QColor(DARK))
        for k in range(3):
            hx = x0 + 18 + k * 34
            if hx + 18 > x1 - 8:
                break
            p.drawRoundedRect(QRectF(hx, y0 + 14, 18, 18), 4, 4)
            p.drawRoundedRect(QRectF(hx, y0 + h - 32, 18, 18), 4, 4)
    # wycięty kwadrat: uniesiony i lekko obrócony
    p.save()
    p.translate(256, 238)
    p.rotate(-9)
    r = QRectF(-108, -108, 216, 216)
    p.setBrush(_grad(r))
    p.drawRoundedRect(r, 30, 30)
    _play(p, 6, 0, 92)
    p.restore()


def draw(size: int = 256) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 512, size / 512)
    _paint(p, size <= 24)
    p.end()
    return pm


def gear(color: str, size: int = 32) -> QPixmap:
    """Zębatka liniowa (8 zębów) do przycisku Opcje; rysowana w układzie 24x24."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 24, size / 24)
    path = QPainterPath()
    teeth, r_out, r_in = 8, 10.2, 7.6
    for i in range(teeth * 4):
        # każdy ząb: dwa punkty na obwodzie zewnętrznym, dwa na wewnętrznym
        a = math.radians(i * 360 / (teeth * 4) - 90 + 360 / (teeth * 8))
        r = r_out if (i % 4) in (0, 1) else r_in
        pt = QPointF(12 + r * math.cos(a), 12 + r * math.sin(a))
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    path.closeSubpath()
    hole = QPainterPath()
    hole.addEllipse(QPointF(12, 12), 3.2, 3.2)
    p.setPen(QPen(QColor(color), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.drawPath(hole)
    p.end()
    return pm


def gear_icon(normal: str, hover: str) -> QIcon:
    icon = QIcon()
    for sz in (16, 20, 24, 32, 48):
        icon.addPixmap(gear(normal, sz), QIcon.Normal)
        icon.addPixmap(gear(hover, sz), QIcon.Active)
    return icon


def app_icon() -> QIcon:
    icon = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(draw(sz))
    return icon
