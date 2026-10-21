"""Small painting helpers shared by the boards."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPolygonF, QRadialGradient

# Every board is drawn on this virtual canvas and scaled to the window.
W, H = 1600.0, 900.0


def rgb(r, g, b, a=255) -> QColor:
    return QColor(int(r), int(g), int(b), int(a))


def mix(c1: QColor, c2: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue() + (c2.blue() - c1.blue()) * t),
        int(c1.alpha() + (c2.alpha() - c1.alpha()) * t),
    )


def scaled(c: QColor, f: float) -> QColor:
    return QColor(
        min(255, int(c.red() * f)), min(255, int(c.green() * f)), min(255, int(c.blue() * f)), c.alpha()
    )


def alpha(c: QColor, a: float) -> QColor:
    out = QColor(c)
    out.setAlpha(max(0, min(255, int(a))))
    return out


def vgrad(y0: float, y1: float, *stops) -> QLinearGradient:
    """A vertical gradient; stops are (position, QColor) or just colours."""
    g = QLinearGradient(0, y0, 0, y1)
    _stops(g, stops)
    return g


def hgrad(x0: float, x1: float, *stops) -> QLinearGradient:
    g = QLinearGradient(x0, 0, x1, 0)
    _stops(g, stops)
    return g


def _stops(g, stops) -> None:
    if stops and isinstance(stops[0], QColor):
        n = len(stops)
        for i, c in enumerate(stops):
            g.setColorAt(i / (n - 1), c)
    else:
        for pos, c in stops:
            g.setColorAt(pos, c)


def radial(cx: float, cy: float, r: float, *stops) -> QRadialGradient:
    g = QRadialGradient(cx, cy, r)
    _stops(g, stops)
    return g


def poly(*points) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in points])


def soft_blob(size: int, color: QColor) -> QImage:
    """A round, soft-edged sprite (clouds, smoke, fog)."""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    r = size / 2
    p.setPen(Qt.NoPen)
    p.setBrush(radial(r, r, r, (0.0, color), (0.55, alpha(color, color.alpha() * 0.6)), (1.0, alpha(color, 0))))
    p.drawEllipse(QRectF(0, 0, size, size))
    p.end()
    return img


def wobble(t: float, *freqs: float) -> float:
    """A smooth pseudo-random wiggle in -1..1 from a few sines."""
    return sum(math.sin(t * f + i * 1.7) for i, f in enumerate(freqs)) / max(1, len(freqs))
