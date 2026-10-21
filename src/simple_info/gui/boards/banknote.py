"""The currency board's background: the engraved look of a banknote.

Deep green paper with fine wavy guilloché lines across it, faint currency
signs as watermarks, a metallic security thread, and two large rosettes
(the spirograph patterns printed on notes to stop forgers) turning very
slowly. The paper is drawn once for each window size and kept; only the
rosettes move. Drawn on the 1600×900 virtual canvas, scaled to cover.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QImage, QPainter, QPainterPath, QPen

from simple_info.gui.boards.station import cover
from simple_info.gui.paint import H, W, alpha, hgrad, radial, rgb, vgrad

PAPER_TOP = rgb(18, 62, 50)
PAPER_BOTTOM = rgb(8, 34, 30)
INK = rgb(170, 220, 190)
GOLD = rgb(222, 190, 110)
ROSETTE_SIZE = 760
# (centre, size, turns a minute, colour)
ROSETTES = [
    (QPointF(250, 210), 1.0, 0.25, GOLD),
    (QPointF(1380, 700), 1.15, -0.18, INK),
]


def rosette_path(size: float, petals: int = 18, loops: int = 7, phase: float = 0.0) -> QPainterPath:
    """An epitrochoid: the looping, petalled curve of a banknote rosette."""
    R = size * 0.30
    r = R / petals
    d = size * 0.17
    path = QPainterPath()
    steps = 1400
    for i in range(steps + 1):
        t = 2 * math.pi * i / steps
        x = (R + r) * math.cos(t) - d * math.cos((R + r) / r * t + phase)
        y = (R + r) * math.sin(t) - d * math.sin((R + r) / r * t + phase)
        # a gentle breathing in and out, `loops` times round, so the petals vary
        k = 1 + 0.06 * math.sin(loops * t)
        pt = QPointF(x * k, y * k)
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    return path


def _rosette_sprite(colour) -> QImage:
    img = QImage(ROSETTE_SIZE, ROSETTE_SIZE, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(ROSETTE_SIZE / 2, ROSETTE_SIZE / 2)
    p.setBrush(Qt.NoBrush)
    for i in range(6):  # a few curves, each turned a little, make the woven look
        p.setPen(QPen(alpha(colour, 60 - i * 6), 1.1))
        p.drawPath(rosette_path(ROSETTE_SIZE * (1 - i * 0.07), 18 + i * 2, 7, i * 0.5))
    p.setPen(QPen(alpha(colour, 55), 1.2))
    for i in range(3):
        p.drawEllipse(QPointF(0, 0), ROSETTE_SIZE * (0.47 - i * 0.012), ROSETTE_SIZE * (0.47 - i * 0.012))
    p.end()
    return img


class Banknote:
    def __init__(self):
        self._cache: Optional[QImage] = None
        self._cache_size = None
        self._sprites: list[QImage] = []
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
            self._paint_paper(cp)
            cp.end()
        if not self._sprites:
            self._sprites = [_rosette_sprite(colour) for *_, colour in ROSETTES]
        p.drawImage(target.topLeft(), self._cache)

        s, x, y = cover(target)
        p.save()
        p.translate(x, y)
        p.scale(s, s)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        for (centre, scale, turns, _), sprite in zip(ROSETTES, self._sprites):
            p.save()
            p.translate(centre)
            p.rotate(self.t * turns * 6)  # turns a minute -> degrees a second
            p.scale(scale, scale)
            p.drawImage(QPointF(-ROSETTE_SIZE / 2, -ROSETTE_SIZE / 2), sprite)
            p.restore()
        p.restore()

    def _paint_paper(self, p: QPainter) -> None:
        full = QRectF(-400, -400, W + 800, H + 800)
        p.fillRect(full, vgrad(0, H, PAPER_TOP, PAPER_BOTTOM))
        # a soft lighter area, as if lit from above
        p.setPen(Qt.NoPen)
        p.setBrush(radial(W * 0.45, H * 0.2, 1100, (0, rgb(80, 140, 110, 60)), (1, rgb(80, 140, 110, 0))))
        p.drawRect(full)

        # guilloché waves: fine lines whose ripples swell and fade across the note
        p.setBrush(Qt.NoBrush)
        for band, (top, gap, lines, colour) in enumerate(((60, 7, 14, INK), (780, 7, 12, GOLD))):
            for i in range(lines):
                path = QPainterPath()
                for j in range(0, 361):
                    x = -400 + j * (W + 800) / 360
                    swell = 0.5 + 0.5 * math.sin(x * 0.004 + band)
                    y = top + i * gap + math.sin(x * 0.035 + i * 0.45) * 16 * swell + math.sin(x * 0.011 + i) * 6
                    path.moveTo(x, y) if j == 0 else path.lineTo(x, y)
                p.setPen(QPen(alpha(colour, 34), 1.0))
                p.drawPath(path)

        # a fine diagonal hatch over everything, like engraved paper
        p.setPen(QPen(rgb(255, 255, 255, 7), 1))
        for k in range(-60, 160):
            x = k * 14
            p.drawLine(QPointF(x, -400), QPointF(x - 700, H + 400))

        # watermarks: big faint currency signs
        f = QFont("serif")
        f.setPixelSize(420)
        f.setBold(True)
        p.setFont(f)
        for sign, x, y, a in (("£", 560, 640, 16), ("€", 980, 420, 12), ("$", 120, 860, 10), ("¥", 1300, 330, 10)):
            p.setPen(rgb(255, 255, 255, a))
            p.drawText(QPointF(x, y), sign)

        # a security thread, broken into "windowed" dashes
        x = W - 22
        p.setPen(Qt.NoPen)
        p.setBrush(hgrad(x - 7, x + 7, rgb(120, 110, 80, 90), rgb(240, 225, 170, 140), rgb(120, 110, 80, 90)))
        for y in range(-20, int(H) + 20, 64):
            p.drawRect(QRectF(x - 6, y, 12, 40))
