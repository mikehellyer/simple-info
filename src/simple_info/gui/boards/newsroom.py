"""The news board's background: a newsroom's slowly turning globe.

A deep blue going to crimson at the edges, like a news studio, with a big
wireframe globe turning slowly behind everything, a glowing ring round it,
and faint streaks of light drifting across. The backdrop is drawn once for
each window size and kept; the globe and streaks are drawn each frame.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPen

from simple_info.gui.boards.station import cover
from simple_info.gui.paint import H, W, alpha, hgrad, radial, rgb, vgrad

CENTRE = QPointF(1060, 470)
RADIUS = 520.0
TILT = math.radians(18)  # the globe leans towards us a little
TURN_SECONDS = 240.0  # one full turn
LINE = rgb(120, 170, 255)


class Newsroom:
    def __init__(self):
        self._cache: Optional[QImage] = None
        self._cache_size = None
        self.t = 0.0

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
            self._paint_backdrop(cp)
            cp.end()
        p.drawImage(target.topLeft(), self._cache)
        s, x, y = cover(target)
        p.save()
        p.translate(x, y)
        p.scale(s, s)
        p.setRenderHint(QPainter.Antialiasing)
        self._paint_globe(p)
        self._paint_streaks(p)
        p.restore()

    def _paint_backdrop(self, p: QPainter) -> None:
        full = QRectF(-400, -400, W + 800, H + 800)
        p.fillRect(full, hgrad(-400, W + 400, (0, rgb(70, 8, 22)), (0.35, rgb(12, 18, 52)), (0.75, rgb(8, 14, 40)),
                               (1, rgb(60, 6, 20))))
        p.setPen(Qt.NoPen)
        p.setBrush(radial(CENTRE.x(), CENTRE.y(), RADIUS * 1.5, (0, rgb(40, 80, 170, 120)), (0.6, rgb(20, 40, 110, 40)), (1, rgb(0, 0, 0, 0))))
        p.drawEllipse(CENTRE, RADIUS * 1.5, RADIUS * 1.5)
        # a fine studio grid on the floor and walls
        p.setPen(QPen(rgb(255, 255, 255, 10), 1))
        for i in range(-10, 40):
            x = i * 60
            p.drawLine(QPointF(x, -400), QPointF(x, H + 400))
        for j in range(-10, 30):
            p.drawLine(QPointF(-400, j * 60), QPointF(W + 400, j * 60))
        # the globe's ring, like a set piece
        p.setPen(QPen(alpha(LINE, 60), 3))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(CENTRE, RADIUS * 1.08, RADIUS * 1.08 * 0.32)
        p.fillRect(full, vgrad(0, H, (0, rgb(0, 0, 0, 40)), (0.6, rgb(0, 0, 0, 90)), (1, rgb(0, 0, 0, 170))))

    def _project(self, lat: float, lon: float, spin: float) -> tuple[QPointF, bool]:
        """A point on the globe to the screen, and whether it's on the near side."""
        x = math.cos(lat) * math.sin(lon + spin)
        y = math.sin(lat)
        z = math.cos(lat) * math.cos(lon + spin)
        # tilt about the x axis
        y, z = y * math.cos(TILT) - z * math.sin(TILT), y * math.sin(TILT) + z * math.cos(TILT)
        return QPointF(CENTRE.x() + x * RADIUS, CENTRE.y() - y * RADIUS), z > 0

    def _paint_globe(self, p: QPainter) -> None:
        spin = (self.t / TURN_SECONDS) * 2 * math.pi
        p.setBrush(Qt.NoBrush)
        near, far = QPainterPath(), QPainterPath()
        steps = 48

        def trace(points) -> None:
            last = None
            for pt, front in points:
                path = near if front else far
                if last is not None and last[1] == front:
                    path.lineTo(pt)
                else:
                    path.moveTo(pt)
                last = (pt, front)

        for m in range(12):  # meridians
            lon = m * math.pi / 12
            trace(self._project(-math.pi / 2 + math.pi * i / steps, lon, spin) for i in range(steps + 1))
            trace(self._project(-math.pi / 2 + math.pi * i / steps, lon + math.pi, spin) for i in range(steps + 1))
        for k in range(-4, 5):  # parallels
            lat = k * math.pi / 10
            trace(self._project(lat, 2 * math.pi * i / (steps * 2), spin) for i in range(steps * 2 + 1))
        p.setPen(QPen(alpha(LINE, 26), 1.2))
        p.drawPath(far)
        p.setPen(QPen(alpha(LINE, 70), 1.6))
        p.drawPath(near)
        # the rim
        p.setPen(QPen(alpha(LINE, 90), 2))
        p.drawEllipse(CENTRE, RADIUS, RADIUS)

    def _paint_streaks(self, p: QPainter) -> None:
        p.setPen(Qt.NoPen)
        for i in range(4):
            speed = 40 + i * 17
            x = ((self.t * speed + i * 530) % (W + 900)) - 450
            y = 160 + i * 190
            p.setBrush(hgrad(x, x + 420, (0, rgb(255, 255, 255, 0)), (0.5, rgb(200, 220, 255, 22)), (1, rgb(255, 255, 255, 0))))
            p.drawRect(QRectF(x, y, 420, 2))
