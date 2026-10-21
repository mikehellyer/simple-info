"""The TV board's background: the glow of an old television.

A deep indigo screen with soft, blurred colour bars (the test signal every
TV set has shown at some time) glowing along the top and reflected along
the bottom, fine scanlines, a vignette, and now and then the slow bright
roll of a CRT's refresh sweeping down the screen. The still part is drawn
once for each window size and kept; only the sweep moves.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter

from simple_info.gui.boards.station import cover
from simple_info.gui.paint import H, W, radial, rgb, vgrad

# the bars, left to right, at 75% like the classic test signal
BARS = [(191, 191, 191), (191, 191, 0), (0, 191, 191), (0, 191, 0), (191, 0, 191), (191, 0, 0), (0, 0, 191)]
SWEEP_SECONDS = 9.0  # how long one roll of the sweep takes, top to bottom and a pause


def _blurred_bars(width: int, height: int) -> QImage:
    """The colour bars, soft-edged: drawn tiny and scaled up smoothly."""
    small = QImage(len(BARS) * 4, 6, QImage.Format_ARGB32_Premultiplied)
    small.fill(Qt.transparent)
    p = QPainter(small)
    for i, (r, g, b) in enumerate(BARS):
        p.fillRect(QRectF(i * 4 + 0.5, 1, 3, 4), rgb(r, g, b))
    p.end()
    return small.scaled(width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


class Broadcast:
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
            cp.setRenderHint(QPainter.SmoothPixmapTransform)
            self._paint_screen(cp)
            cp.end()
        p.drawImage(target.topLeft(), self._cache)

        # the refresh sweep: a soft bright band rolling down, then a pause
        phase = (self.t % SWEEP_SECONDS) / SWEEP_SECONDS
        if phase < 0.6:
            s, x, y = cover(target)
            p.save()
            p.translate(x, y)
            p.scale(s, s)
            yy = -160 + (H + 320) * phase / 0.6
            p.fillRect(QRectF(0, yy - 160, W, 320), vgrad(yy - 160, yy + 160, (0, rgb(170, 190, 255, 0)), (0.5, rgb(170, 190, 255, 16)),
                                                           (1, rgb(170, 190, 255, 0))))
            p.restore()

    def _paint_screen(self, p: QPainter) -> None:
        full = QRectF(-400, -400, W + 800, H + 800)
        p.fillRect(full, vgrad(0, H, rgb(20, 16, 44), rgb(8, 8, 20)))
        # the bars glowing along the top, fading down…
        bars = _blurred_bars(int(W), 420)
        p.setOpacity(0.38)
        p.drawImage(QRectF(0, -120, W, 420), bars)
        # …and their reflection along the bottom, fainter
        p.setOpacity(0.16)
        flipped = bars.flipped(Qt.Vertical) if hasattr(bars, "flipped") else bars.mirrored(False, True)  # (flipped: Qt 6.9+)
        p.drawImage(QRectF(0, H - 170, W, 340), flipped)
        p.setOpacity(1.0)
        # darken the middle, where the guide sits
        p.fillRect(full, vgrad(0, H, (0, rgb(10, 8, 24, 70)), (0.3, rgb(10, 8, 24, 200)), (0.8, rgb(10, 8, 24, 200)),
                                (1, rgb(10, 8, 24, 110))))
        # scanlines
        for y in range(0, int(H), 4):
            p.fillRect(QRectF(0, y, W, 1.6), rgb(0, 0, 0, 46))
        # the curved-glass vignette
        p.setPen(Qt.NoPen)
        p.setBrush(radial(W / 2, H / 2, W * 0.75, (0, rgb(0, 0, 0, 0)), (0.7, rgb(0, 0, 0, 60)), (1, rgb(0, 0, 0, 190))))
        p.drawRect(full)
