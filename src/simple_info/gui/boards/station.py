"""The train board's background: inside a Victorian train shed, looking
down the platforms under the glazed iron arches, with lamps lit.

It hardly moves, so it's drawn once for each window size and kept. Only
the lamps' glow breathes a little, drawn on top each frame. It's drawn on
the 1600×900 virtual canvas, scaled to cover the window (cropping rather
than stretching, so the arches stay round).
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPen

from simple_info.gui.paint import H, W, alpha, mix, poly, radial, rgb, vgrad

VP = QPointF(800, 520)  # where the platforms meet, far away
DEPTHS = [0.0, 0.55, 1.2, 2.1, 3.4, 5.4, 8.5, 13.0]  # where the arches stand, nearest first
NEAR_HALF_SPAN = 760.0  # half the width of the nearest arch, where it springs from its columns
NEAR_RISE = 720.0  # how far the nearest arch's crown is above its springing
FLOOR = 470.0  # how far below the vanishing point the near platform surface is
IRON = rgb(26, 44, 40)  # Victorian station green, in shadow
LAMP = rgb(255, 196, 120)


def _k(depth: float) -> float:
    """How big things are at a depth (1 for the nearest arch)."""
    return 1 / (1 + depth * 0.55)


def cover(target: QRectF) -> tuple[float, float, float]:
    """Scale and offset that make the 1600×900 canvas cover target."""
    s = max(target.width() / W, target.height() / H)
    return s, target.x() + (target.width() - W * s) / 2, target.y() + (target.height() - H * s) / 2


class StationHall:
    def __init__(self):
        self._cache: Optional[QImage] = None
        self._cache_size = None
        self.t = 0.0
        # lamps: (x, y, size), hanging from the arches on both sides
        self._lamps = []
        for d in DEPTHS[1:6]:
            k = _k(d)
            for side in (-1, 1):
                self._lamps.append((VP.x() + side * 420 * k, VP.y() - 210 * k, 26 * k))

    def step(self, dt: float) -> None:
        self.t += dt

    def paint(self, p: QPainter, target: QRectF) -> None:
        size = (int(target.width()), int(target.height()))
        if self._cache is None or self._cache_size != size:
            self._cache = QImage(max(1, size[0]), max(1, size[1]), QImage.Format_RGB32)
            self._cache_size = size
            cp = QPainter(self._cache)
            s, x, y = cover(QRectF(0, 0, *size))
            cp.translate(x, y)
            cp.scale(s, s)
            cp.setRenderHint(QPainter.Antialiasing)
            self._paint_hall(cp)
            cp.end()
        p.drawImage(target.topLeft(), self._cache)

        # the lamps' glow breathes a little
        s, x, y = cover(target)
        p.save()
        p.translate(x, y)
        p.scale(s, s)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for i, (lx, ly, r) in enumerate(self._lamps):
            k = 0.85 + 0.15 * math.sin(self.t * 0.7 + i * 1.3)
            p.setBrush(radial(lx, ly, r * 5, (0, alpha(LAMP, 70 * k)), (1, alpha(LAMP, 0))))
            p.drawEllipse(QPointF(lx, ly), r * 5, r * 5)
        p.restore()

    # --- the hall, drawn once

    def _paint_hall(self, p: QPainter) -> None:
        p.fillRect(QRectF(-400, -400, W + 800, H + 800), rgb(12, 16, 22))
        self._paint_walls(p)
        self._paint_roof(p)
        self._paint_far_opening(p)
        self._paint_floor(p)
        self._paint_columns(p)
        self._paint_lamps(p)
        # dim it all, darker at the edges: the board is what matters
        p.setPen(Qt.NoPen)
        p.setBrush(radial(VP.x(), VP.y() - 100, 1100, (0, rgb(0, 0, 0, 40)), (0.7, rgb(0, 0, 0, 110)), (1, rgb(0, 0, 0, 170))))
        p.drawRect(QRectF(-400, -400, W + 800, H + 800))

    def _paint_walls(self, p: QPainter) -> None:
        """Brick side walls beyond the columns."""
        p.setPen(Qt.NoPen)
        p.setBrush(vgrad(0, H, rgb(58, 36, 30), rgb(30, 20, 18)))
        p.drawRect(QRectF(-400, -400, W + 800, H + 800))
        p.setPen(QPen(rgb(0, 0, 0, 60), 2))
        for y in range(-400, int(H) + 400, 14):  # mortar courses, converging a little
            p.drawLine(QPointF(-400, y), QPointF(VP.x(), VP.y() + (y - VP.y()) * 0.15))
            p.drawLine(QPointF(W + 400, y), QPointF(VP.x(), VP.y() + (y - VP.y()) * 0.15))

    def _arch(self, depth: float) -> QPainterPath:
        """One arch rib as a curve from left springing to right springing."""
        k = _k(depth)
        half, rise, spring = NEAR_HALF_SPAN * k, NEAR_RISE * k, VP.y() - 40 * k
        path = QPainterPath()
        steps = 48
        for i in range(steps + 1):
            a = math.pi * i / steps
            pt = QPointF(VP.x() - math.cos(a) * half, spring - math.sin(a) * rise)
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        return path

    def _paint_roof(self, p: QPainter) -> None:
        # the glazing: a soft dusk-blue light coming through, brightest far away
        glass = QPainterPath(self._arch(DEPTHS[0]))
        glass.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(radial(VP.x(), VP.y() - 120, 900, (0, rgb(96, 120, 150)), (0.5, rgb(52, 66, 88)), (1, rgb(26, 32, 46))))
        p.drawPath(glass)
        # glazing bars: lines running along the roof, towards the far end…
        p.setPen(QPen(rgb(20, 28, 34), 3))
        near, far = DEPTHS[0], DEPTHS[-1]
        for i in range(1, 24):
            a = math.pi * i / 24
            def at(depth):
                k = _k(depth)
                return QPointF(VP.x() - math.cos(a) * NEAR_HALF_SPAN * k, VP.y() - 40 * k - math.sin(a) * NEAR_RISE * k)
            p.drawLine(at(near), at(far))
        # …and the iron arch ribs across it, far ones thinner
        for d in reversed(DEPTHS):
            k = _k(d)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(mix(IRON, rgb(10, 14, 16), 0.2), max(2.0, 34 * k), Qt.SolidLine, Qt.FlatCap))
            p.drawPath(self._arch(d))
            p.setPen(QPen(rgb(70, 96, 88, 120), max(1.0, 4 * k)))  # a lit lower edge
            arch = self._arch(d)
            p.save()
            p.translate(0, 14 * k)
            p.drawPath(arch)
            p.restore()

    def _paint_far_opening(self, p: QPainter) -> None:
        k = _k(DEPTHS[-1] + 4)
        half, rise = NEAR_HALF_SPAN * k, NEAR_RISE * k
        opening = QRectF(VP.x() - half, VP.y() - 40 * k - rise, half * 2, rise + 40 * k + 10)
        p.setPen(Qt.NoPen)
        p.setBrush(radial(VP.x(), VP.y() - rise * 0.4, half * 2.2, (0, rgb(200, 190, 170)), (0.4, rgb(120, 130, 150, 160)), (1, rgb(60, 70, 90, 0))))
        p.drawEllipse(opening.center(), half * 2.2, half * 1.6)

    def _paint_floor(self, p: QPainter) -> None:
        y_near = VP.y() + FLOOR
        def toward(x_near: float, t: float) -> QPointF:
            return QPointF(x_near + (VP.x() - x_near) * t, y_near + (VP.y() - y_near) * t)
        # the platforms either side, and the tracks between
        edge = 330.0  # platform edges at the near end, either side of the middle
        far = 0.985
        p.setPen(Qt.NoPen)
        p.setBrush(vgrad(VP.y(), y_near, rgb(40, 40, 44), rgb(70, 68, 66)))
        for side in (-1, 1):
            p.drawPolygon(poly((VP.x() + side * 2200, y_near), (VP.x() + side * edge, y_near),
                               (toward(VP.x() + side * edge, far).x(), toward(VP.x() + side * edge, far).y()),
                               (toward(VP.x() + side * 2200, far).x(), toward(VP.x() + side * 2200, far).y())))
        p.setBrush(vgrad(VP.y(), y_near, rgb(16, 16, 18), rgb(30, 28, 26)))
        a, b = toward(VP.x() - edge, far), toward(VP.x() + edge, far)
        p.drawPolygon(poly((VP.x() - edge, y_near), (VP.x() + edge, y_near), (b.x(), b.y()), (a.x(), a.y())))
        # yellow lines along each platform edge, and the rails
        for side in (-1, 1):
            p.setPen(QPen(rgb(220, 180, 40, 200), 9))
            x = VP.x() + side * (edge + 40)
            p.drawLine(QPointF(x, y_near), toward(x, far))
            p.setPen(QPen(rgb(150, 150, 160, 200), 4))
            for rail in (-1, 1):
                x = VP.x() + side * 165 + rail * 75
                p.drawLine(QPointF(x, y_near), toward(x, far))

    def _paint_columns(self, p: QPainter) -> None:
        for d in reversed(DEPTHS[1:]):
            k = _k(d)
            y_floor = VP.y() + FLOOR * k
            top = VP.y() - 40 * k
            for side in (-1, 1):
                x = VP.x() + side * NEAR_HALF_SPAN * k
                w = 26 * k
                p.setPen(Qt.NoPen)
                p.setBrush(vgrad(top, y_floor, mix(IRON, rgb(60, 90, 80), 0.3), IRON))
                p.drawRect(QRectF(x - w / 2, top, w, y_floor - top))
                # a capital, and a bracket up into the arch
                p.drawRect(QRectF(x - w * 1.4, top - 6 * k, w * 2.8, 14 * k))
                p.setPen(QPen(IRON, max(1.0, 8 * k)))
                p.drawLine(QPointF(x, top), QPointF(x - side * 120 * k, top - 90 * k))

    def _paint_lamps(self, p: QPainter) -> None:
        for lx, ly, r in self._lamps:
            p.setPen(QPen(rgb(20, 24, 26), max(1.0, r * 0.12)))
            p.drawLine(QPointF(lx, ly - r * 6), QPointF(lx, ly - r))
            p.setPen(Qt.NoPen)
            p.setBrush(radial(lx - r * 0.3, ly - r * 0.3, r * 1.2, (0, rgb(255, 240, 210)), (1, LAMP)))
            p.drawEllipse(QPointF(lx, ly), r, r)
