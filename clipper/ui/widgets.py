"""Własne kontrolki: kadrowanie, kafelek, oś czasu, pasek wagi, kroki."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QImage, QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from .. import standard as S
from ..core import Crop, fmt_mb
from . import theme as T


def fmt_time(ms: float, decimals: bool = True) -> str:
    s = max(0.0, ms / 1000.0)
    m = int(s // 60)
    rest = s - m * 60
    if decimals:
        return f"{m}:{rest:04.1f}".replace(".", ",")
    return f"{m}:{int(rest):02d}"


# ------------------------------------------------------------------ kadr

class CropView(QWidget):
    """Podgląd klatki z kwadratową ramką kadru (przesuwanie, skalowanie)."""
    cropChanged = Signal(object)        # Crop, w trakcie przeciągania
    cropFinished = Signal(object)       # Crop, po puszczeniu myszy

    HANDLE = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(360, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image: Optional[QImage] = None
        self.src_w = 0
        self.src_h = 0
        self.crop: Optional[Crop] = None
        self._drag = None   # ("move", start_pt, start_crop) | ("resize", anchor, dir)
        self.setToolTip("Przeciągnij ramkę, żeby przesunąć kadr. Ciągnij za róg, żeby zmienić "
                        "rozmiar. Kółko myszy: rozmiar. Dwuklik: największy możliwy kadr.")

    def set_source(self, w: int, h: int) -> None:
        self.src_w, self.src_h = w, h
        self.crop = Crop.centered(w, h)
        self.image = None
        self.update()

    def set_image(self, img: QImage) -> None:
        self.image = img
        self.update()

    def set_crop(self, c: Crop) -> None:
        self.crop = c.clamp(self.src_w, self.src_h)
        self.update()

    # geometria
    def _rect(self) -> QRectF:
        if not self.src_w:
            return QRectF()
        m = 10
        aw, ah = self.width() - 2 * m, self.height() - 2 * m
        k = min(aw / self.src_w, ah / self.src_h)
        w, h = self.src_w * k, self.src_h * k
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _k(self) -> float:
        r = self._rect()
        return r.width() / self.src_w if self.src_w else 1.0

    def _crop_rect(self) -> QRectF:
        r, k, c = self._rect(), self._k(), self.crop
        return QRectF(r.x() + c.x * k, r.y() + c.y * k, c.size * k, c.size * k)

    def _to_src(self, p: QPointF) -> QPointF:
        r, k = self._rect(), self._k()
        return QPointF((p.x() - r.x()) / k, (p.y() - r.y()) / k)

    def _corner_at(self, p: QPointF) -> Optional[tuple[int, int]]:
        cr = self._crop_rect()
        for sx, sy, pt in ((-1, -1, cr.topLeft()), (1, -1, cr.topRight()),
                           (-1, 1, cr.bottomLeft()), (1, 1, cr.bottomRight())):
            if abs(p.x() - pt.x()) <= self.HANDLE and abs(p.y() - pt.y()) <= self.HANDLE:
                return sx, sy
        return None

    # rysowanie
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(T.BG))
        if not self.src_w:
            return
        r = self._rect()
        if self.image is not None and not self.image.isNull():
            p.drawImage(r, self.image)
        else:
            p.fillRect(r, QColor("#0d0e11"))
        if self.crop is None:
            return
        cr = self._crop_rect()
        shade = QPainterPath()
        shade.addRect(r)
        hole = QPainterPath()
        hole.addRect(cr)
        p.fillPath(shade.subtracted(hole), QColor(0, 0, 0, 150))
        # trójpodział
        p.setPen(QPen(QColor(255, 255, 255, 50), 1))
        for i in (1, 2):
            x = cr.x() + cr.width() * i / 3
            y = cr.y() + cr.height() * i / 3
            p.drawLine(QPointF(x, cr.top()), QPointF(x, cr.bottom()))
            p.drawLine(QPointF(cr.left(), y), QPointF(cr.right(), y))
        p.setPen(QPen(QColor(T.ACCENT), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(cr)
        p.setBrush(QColor("white"))
        p.setPen(QPen(QColor(T.ACCENT), 2))
        hs = 9
        for pt in (cr.topLeft(), cr.topRight(), cr.bottomLeft(), cr.bottomRight()):
            p.drawRect(QRectF(pt.x() - hs / 2, pt.y() - hs / 2, hs, hs))
        # rozmiar kadru
        label = f"{self.crop.size} x {self.crop.size} px"
        f = QFont(self.font())
        f.setPointSizeF(9)
        p.setFont(f)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(label) + 12
        box = QRectF(cr.x() + 6, cr.y() + 6, tw, fm.height() + 4)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(box, 4, 4)
        p.setPen(QColor("white"))
        p.drawText(box, Qt.AlignCenter, label)

    # mysz
    def mousePressEvent(self, e):
        if self.crop is None or e.button() != Qt.LeftButton:
            return
        pos = e.position()
        corner = self._corner_at(pos)
        c = self.crop
        if corner:
            sx, sy = corner
            ax = c.x + (c.size if sx < 0 else 0)
            ay = c.y + (c.size if sy < 0 else 0)
            self._drag = ("resize", (ax, ay), (sx, sy))
        elif self._crop_rect().contains(pos):
            self._drag = ("move", self._to_src(pos), Crop(c.x, c.y, c.size))
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._drag is None:
            corner = self._corner_at(pos) if self.crop else None
            if corner:
                self.setCursor(Qt.SizeFDiagCursor if corner[0] == corner[1] else Qt.SizeBDiagCursor)
            elif self.crop and self._crop_rect().contains(pos):
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.unsetCursor()
            return
        sp = self._to_src(pos)
        if self._drag[0] == "move":
            _, p0, c0 = self._drag
            nc = Crop(int(round(c0.x + sp.x() - p0.x())), int(round(c0.y + sp.y() - p0.y())), c0.size)
        else:
            _, (ax, ay), (sx, sy) = self._drag
            size = max(sx * (sp.x() - ax), sy * (sp.y() - ay))
            max_x = (self.src_w - ax) if sx > 0 else ax
            max_y = (self.src_h - ay) if sy > 0 else ay
            size = int(round(max(min(size, max_x, max_y), min(S.MIN_CROP, self.src_w, self.src_h))))
            nx = ax if sx > 0 else ax - size
            ny = ay if sy > 0 else ay - size
            nc = Crop(int(nx), int(ny), size)
        self.crop = nc.clamp(self.src_w, self.src_h)
        self.update()
        self.cropChanged.emit(self.crop)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.unsetCursor()
            self.cropFinished.emit(self.crop)

    def mouseDoubleClickEvent(self, e):
        if self.crop is not None:
            self.crop = Crop.centered(self.src_w, self.src_h)
            self.update()
            self.cropChanged.emit(self.crop)
            self.cropFinished.emit(self.crop)

    def wheelEvent(self, e):
        if self.crop is None:
            return
        c = self.crop
        step = 1.05 if e.angleDelta().y() < 0 else 1 / 1.05
        size = int(round(c.size * step))
        size = max(min(size, self.src_w, self.src_h), min(S.MIN_CROP, self.src_w, self.src_h))
        cx, cy = c.x + c.size / 2, c.y + c.size / 2
        self.crop = Crop(int(round(cx - size / 2)), int(round(cy - size / 2)), size).clamp(
            self.src_w, self.src_h)
        self.update()
        self.cropChanged.emit(self.crop)
        self.cropFinished.emit(self.crop)


class TileView(QWidget):
    """Kafelek sklepu: wycinek bieżącej klatki przeskalowany do zadanego rozmiaru."""

    def __init__(self, side: int, parent=None):
        super().__init__(parent)
        self.side = side
        self.setFixedSize(side + 2, side + 2)
        self.image: Optional[QImage] = None
        self.src_w = 0
        self.crop: Optional[Crop] = None

    def set_state(self, img: Optional[QImage], src_w: int, crop: Optional[Crop]) -> None:
        self.image, self.src_w, self.crop = img, src_w, crop
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        target = QRectF(1, 1, self.side, self.side)
        p.fillRect(target, QColor("#0d0e11"))
        if self.image is not None and not self.image.isNull() and self.crop and self.src_w:
            k = self.image.width() / self.src_w
            c = self.crop
            src = QRectF(c.x * k, c.y * k, c.size * k, c.size * k)
            p.drawImage(target, self.image, src)
        p.setPen(QPen(QColor(T.BORDER), 1))
        p.drawRect(QRectF(0.5, 0.5, self.side + 1, self.side + 1))


# ------------------------------------------------------------------ oś czasu

class Timeline(QWidget):
    rangeChanged = Signal(int, int)     # start_ms, end_ms
    seekRequested = Signal(int)
    interacted = Signal()

    M = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.duration = 0
        self.start = 0
        self.end = 0
        self.pos_ms = 0
        self.alert = False
        self._drag = None
        self.setToolTip("Oś czasu: przeciągnij uchwyty, żeby wybrać początek i koniec fragmentu. "
                        "Kliknij w pasek, żeby przewinąć.")

    def set_duration(self, ms: int) -> None:
        self.duration = max(1, ms)
        self.update()

    def set_range(self, start: int, end: int) -> None:
        self.start, self.end = start, end
        self.update()

    def set_position(self, ms: int) -> None:
        self.pos_ms = ms
        self.update()

    def set_alert(self, on: bool) -> None:
        self.alert = on
        self.update()

    def _track(self) -> QRectF:
        return QRectF(self.M, 8, self.width() - 2 * self.M, 30)

    def _x(self, ms: float) -> float:
        t = self._track()
        return t.x() + t.width() * ms / self.duration

    def _ms(self, x: float) -> int:
        t = self._track()
        return int(round(max(0.0, min(1.0, (x - t.x()) / t.width())) * self.duration))

    def sizeHint(self):
        return QSize(600, 64)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self._track()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.PANEL_2))
        p.drawRoundedRect(t, 6, 6)
        if not self.duration:
            return
        xs, xe = self._x(self.start), self._x(self.end)
        sel = QRectF(xs, t.y(), xe - xs, t.height())
        col = QColor(T.BAD if self.alert else T.ACCENT)
        fill = QColor(col)
        fill.setAlpha(70)
        p.setBrush(fill)
        p.drawRect(sel)
        p.setPen(QPen(col, 2))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(xs, t.top()), QPointF(xe, t.top()))
        p.drawLine(QPointF(xs, t.bottom()), QPointF(xe, t.bottom()))
        # uchwyty
        for x in (xs, xe):
            h = QRectF(x - 5, t.y() - 4, 10, t.height() + 8)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(h, 3, 3)
            p.setPen(QPen(QColor(255, 255, 255, 200), 1))
            for dy in (-4, 0, 4):
                cy = h.center().y() + dy
                p.drawLine(QPointF(x - 2, cy), QPointF(x + 2, cy))
        # głowica
        xp = self._x(self.pos_ms)
        p.setPen(QPen(QColor("white"), 2))
        p.drawLine(QPointF(xp, t.top() - 2), QPointF(xp, t.bottom() + 2))
        # podziałka
        f = QFont(self.font())
        f.setPointSizeF(8)
        p.setFont(f)
        p.setPen(QColor(T.MUTED))
        dur_s = self.duration / 1000
        step = next((s for s in (1, 2, 5, 10, 15, 30, 60, 120, 300)
                     if t.width() / max(dur_s / s, 1) >= 50), 600)
        s = 0
        while s <= dur_s + 1e-6:
            x = self._x(s * 1000)
            p.drawLine(QPointF(x, t.bottom() + 4), QPointF(x, t.bottom() + 7))
            p.drawText(QRectF(x - 30, t.bottom() + 8, 60, 14), Qt.AlignHCenter, fmt_time(s * 1000, False))
            s += step

    def _hit(self, x: float) -> Optional[str]:
        ds, de = abs(x - self._x(self.start)), abs(x - self._x(self.end))
        if min(ds, de) <= 9:
            return "start" if ds < de or (ds == de and x < self._x(self.start)) else "end"
        return None

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or not self.duration:
            return
        x = e.position().x()
        self._drag = self._hit(x) or "seek"
        self._apply(x)
        self.interacted.emit()

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._drag is None:
            self.setCursor(Qt.SizeHorCursor if self._hit(x) else Qt.PointingHandCursor)
            return
        self._apply(x)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def _apply(self, x: float) -> None:
        ms = self._ms(x)
        min_len = int(S.MIN_FRAGMENT_S * 1000)
        if self._drag == "start":
            self.start = max(0, min(ms, self.end - min_len))
            self.rangeChanged.emit(self.start, self.end)
            self.seekRequested.emit(self.start)
        elif self._drag == "end":
            self.end = min(self.duration, max(ms, self.start + min_len))
            self.rangeChanged.emit(self.start, self.end)
            self.seekRequested.emit(max(self.start, self.end - 34))
        else:
            self.seekRequested.emit(ms)
        self.update()


# ------------------------------------------------------------------ pasek wagi

class SizeBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.value: Optional[int] = None
        self.text_override = "Szacunek wagi pojawi się po analizie"
        self.state = "pending"     # pending | ok | warn | bad
        self.setToolTip("Szacowana waga gotowego pliku na tle limitu sklepu (0,5 MB). "
                        "Liczona z próbnego kodowania bieżącego kadru.")

    def set_pending(self, text: str) -> None:
        self.value, self.state, self.text_override = None, "pending", text
        self.update()

    def set_value(self, value: int, state: str) -> None:
        self.value, self.state, self.text_override = value, state, ""
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bar = QRectF(0, 24, self.width(), 12)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.PANEL_2))
        p.drawRoundedRect(bar, 6, 6)
        col = {"ok": T.OK, "warn": T.WARN, "bad": T.BAD}.get(self.state, T.MUTED)
        if self.value is not None:
            frac = min(1.0, self.value / S.MAX_BYTES)
            p.setBrush(QColor(col))
            p.drawRoundedRect(QRectF(0, 24, max(12.0, self.width() * frac), 12), 6, 6)
            text = f"≈ {fmt_mb(self.value)} / {fmt_mb(S.MAX_BYTES)} MB"
        else:
            text = self.text_override
        f = QFont(self.font())
        f.setPointSizeF(10.5 if self.value is not None else 9.5)
        f.setBold(self.value is not None)
        p.setFont(f)
        p.setPen(QColor(col if self.value is not None else T.MUTED))
        p.drawText(QRectF(0, 0, self.width(), 20), Qt.AlignLeft | Qt.AlignVCenter, text)


# ------------------------------------------------------------------ kroki

class StepHeader(QWidget):
    STEPS = ["Wczytaj", "Kadr", "Fragment", "Eksport", "Wynik"]

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.labels = []
        for i, name in enumerate(self.STEPS, 1):
            lb = QLabel(f"{i}. {name}")
            lb.setObjectName("step")
            self.labels.append(lb)
            lay.addWidget(lb)
        self.set_step(1)

    def set_step(self, n: int) -> None:
        for i, lb in enumerate(self.labels, 1):
            lb.setProperty("active", "true" if i == n else "false")
            lb.setProperty("done", "true" if i < n else "false")
            lb.style().unpolish(lb)
            lb.style().polish(lb)
