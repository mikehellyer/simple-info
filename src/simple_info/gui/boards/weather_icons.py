"""Weather icons, drawn rather than shipped as images."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen

from simple_info.core import weather as wx
from simple_info.gui.paint import radial, rgb, vgrad

SUN = rgb(255, 200, 60)
MOON = rgb(236, 232, 210)


def draw_icon(p: QPainter, c: QPointF, size: float, code: int, is_day: bool = True) -> None:
    """A weather icon for a WMO code, centred on c, roughly size across."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(c)
    p.scale(size / 100, size / 100)  # drawn in a 100×100 box centred on 0,0
    cond = wx.condition_for(code)
    heavy = code in (65, 67, 75, 82, 86, 99)

    if cond == wx.CLEAR:
        _sun(p, QPointF(0, 0), 24) if is_day else _moon(p, QPointF(0, 0), 26)
    elif cond == wx.PARTLY_CLOUDY:
        _sun(p, QPointF(-14, -14), 18) if is_day else _moon(p, QPointF(-14, -14), 20)
        _cloud(p, QPointF(8, 10), 0.8, rgb(236, 240, 246))
    elif cond == wx.CLOUDY:
        _cloud(p, QPointF(-14, -8), 0.62, rgb(170, 178, 192))
        _cloud(p, QPointF(6, 6), 0.85, rgb(220, 226, 236))
    elif cond == wx.FOG:
        _cloud(p, QPointF(0, -12), 0.8, rgb(200, 206, 216))
        p.setPen(QPen(rgb(200, 206, 216), 6, Qt.SolidLine, Qt.RoundCap))
        for i, y in enumerate((18, 30, 42)):
            p.drawLine(QPointF(-36 + i * 6, y), QPointF(34 - i * 4, y))
    elif cond in (wx.DRIZZLE, wx.RAIN):
        dark = cond == wx.RAIN
        _cloud(p, QPointF(0, -12), 0.9, rgb(150, 160, 178) if dark else rgb(200, 208, 220))
        drops = 5 if heavy else 3 if dark else 3
        p.setPen(QPen(rgb(96, 170, 255), 5 if dark else 3.5, Qt.SolidLine, Qt.RoundCap))
        for i in range(drops):
            x = -26 + i * (52 / max(1, drops - 1))
            p.drawLine(QPointF(x + 4, 18), QPointF(x - 4, 36 if dark else 30))
    elif cond == wx.SNOW:
        _cloud(p, QPointF(0, -12), 0.9, rgb(206, 214, 228))
        p.setPen(QPen(rgb(255, 255, 255), 3, Qt.SolidLine, Qt.RoundCap))
        for i, (x, y) in enumerate(((-22, 26), (0, 36), (22, 26)) + (((-11, 44), (11, 44)) if heavy else ())):
            for a in range(3):
                ang = math.radians(a * 60)
                d = QPointF(math.cos(ang) * 6, math.sin(ang) * 6)
                p.drawLine(QPointF(x, y) - d, QPointF(x, y) + d)
    elif cond == wx.THUNDER:
        _cloud(p, QPointF(0, -14), 0.92, rgb(110, 116, 136))
        bolt = QPainterPath()
        for i, (x, y) in enumerate(((4, 6), (-10, 28), (0, 28), (-8, 48), (14, 20), (3, 20), (10, 6))):
            bolt.moveTo(x, y) if i == 0 else bolt.lineTo(x, y)
        bolt.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(rgb(255, 214, 60))
        p.drawPath(bolt)
        p.setPen(QPen(rgb(96, 170, 255), 4, Qt.SolidLine, Qt.RoundCap))
        for x in (-28, 26):
            p.drawLine(QPointF(x + 3, 20), QPointF(x - 3, 34))
    p.restore()


def _sun(p: QPainter, c: QPointF, r: float) -> None:
    p.setPen(QPen(SUN, 5, Qt.SolidLine, Qt.RoundCap))
    for i in range(8):
        a = i * math.pi / 4
        p.drawLine(QPointF(c.x() + math.cos(a) * r * 1.35, c.y() + math.sin(a) * r * 1.35),
                   QPointF(c.x() + math.cos(a) * r * 1.75, c.y() + math.sin(a) * r * 1.75))
    p.setPen(Qt.NoPen)
    p.setBrush(radial(c.x() - r * 0.3, c.y() - r * 0.3, r * 1.3, rgb(255, 236, 140), SUN))
    p.drawEllipse(c, r, r)


def _moon(p: QPainter, c: QPointF, r: float) -> None:
    path = QPainterPath()
    path.addEllipse(c, r, r)
    bite = QPainterPath()
    bite.addEllipse(QPointF(c.x() + r * 0.55, c.y() - r * 0.35), r * 0.9, r * 0.9)
    p.setPen(Qt.NoPen)
    p.setBrush(MOON)
    p.drawPath(path.subtracted(bite))


def _cloud(p: QPainter, c: QPointF, scale: float, colour) -> None:
    path = QPainterPath()
    path.setFillRule(Qt.WindingFill)
    for x, y, r in ((-22, 6, 18), (0, -6, 24), (22, 4, 18)):
        path.addEllipse(QPointF(c.x() + x * scale, c.y() + y * scale), r * scale, r * scale)
    path.addRoundedRect(QRectF(c.x() - 40 * scale, c.y() + 2 * scale, 80 * scale, 22 * scale), 11 * scale, 11 * scale)
    path = path.simplified()
    p.setPen(Qt.NoPen)
    p.setBrush(vgrad(c.y() - 30 * scale, c.y() + 24 * scale, colour, colour.darker(118)))
    p.drawPath(path)
