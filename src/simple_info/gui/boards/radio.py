"""The radio board: what's on your radio stations over the next four hours,
in the same guide grid as the TV board, on an old valve radio.

The background is the front of a 1950s radio set: a walnut cabinet, woven
speaker cloth, and along the top the glowing amber tuning dial with its
frequency scale, and a needle drifting slowly along it.
The cabinet and dial are drawn once for each window size and kept; only
the needle and the dial's glow move.
"""
from __future__ import annotations

import math
import random
import time
import zlib
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

from simple_info.core import bauer, tv
from simple_info.gui.boards.station import cover
from simple_info.gui.boards.tv import TvBoard
from simple_info.gui.paint import H, W, alpha, radial, rgb, vgrad

DIAL = QRectF(0, H - 44, W, 44)  # the tuning dial's glass, a slim strip along the bottom
NEEDLE_SECONDS = 90.0  # one slow drift across the dial and back
AMBER = rgb(255, 196, 110)

# Station badges in the stations' own colours, roughly; the rest get a steady colour from their name.
STATIONS = [
    ("BBC Radio 1", rgb(230, 30, 110)), ("BBC Radio 2", rgb(236, 110, 20)), ("BBC Radio 3", rgb(186, 28, 40)),
    ("BBC Radio 4", rgb(0, 120, 140)), ("BBC Radio 5", rgb(0, 140, 200)), ("BBC Radio 6", rgb(0, 160, 140)),
    ("BBC Radio Scotland", rgb(40, 90, 180)), ("BBC Radio nan", rgb(20, 120, 90)), ("BBC World", rgb(170, 30, 30)),
    ("BBC", rgb(60, 60, 70)), ("Classic FM", rgb(30, 60, 130)), ("Capital", rgb(30, 110, 200)),
    ("Smooth", rgb(120, 40, 120)), ("Heart", rgb(210, 20, 50)), ("Planet Rock", rgb(30, 30, 30)),
    ("Radio X", rgb(40, 40, 40)), ("talkSPORT", rgb(200, 30, 40)), ("LBC", rgb(20, 70, 160)),
    ("Virgin", rgb(200, 0, 30)), ("MFR 2", rgb(0, 150, 190)), ("MFR", rgb(150, 30, 120)),
    ("Northsound", rgb(230, 80, 20)),
]


def station_colour(name: str) -> QColor:
    for prefix, colour in STATIONS:
        if name.startswith(prefix):
            return colour
    c = QColor()
    c.setHsl(zlib.crc32(name.encode()) % 360, 120, 80)
    return c


class ValveRadio:
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
            self._paint_cabinet(cp)
            self._paint_dial(cp)
            cp.end()
        p.drawImage(target.topLeft(), self._cache)

        s, x, y = cover(target)
        p.save()
        p.translate(x, y)
        p.scale(s, s)
        p.setRenderHint(QPainter.Antialiasing)
        # the dial lamps' glow breathes a little
        glow = 0.85 + 0.15 * math.sin(self.t * 0.6)
        p.setPen(Qt.NoPen)
        p.setBrush(radial(W / 2, DIAL.center().y(), W * 0.6, (0, rgb(255, 170, 70, 40 * glow)), (1, rgb(255, 170, 70, 0))))
        p.drawRect(DIAL)
        # the needle, drifting slowly along the dial
        phase = (math.sin(self.t * 2 * math.pi / NEEDLE_SECONDS) + 1) / 2
        nx = 140 + phase * (W - 280)
        p.setPen(QPen(rgb(200, 30, 20, 230), 3))
        p.drawLine(QPointF(nx, DIAL.top() + 6), QPointF(nx, DIAL.bottom() - 8))
        p.setPen(QPen(rgb(255, 120, 90, 80), 9))
        p.drawLine(QPointF(nx, DIAL.top() + 6), QPointF(nx, DIAL.bottom() - 8))
        p.restore()

    def _paint_cabinet(self, p: QPainter) -> None:
        full = QRectF(-400, -400, W + 800, H + 800)
        # walnut: a warm gradient with long wavy grain lines
        p.fillRect(full, vgrad(0, H, rgb(92, 52, 28), rgb(52, 28, 14)))
        rng = random.Random(3)
        for i in range(140):
            y0 = rng.uniform(-50, H + 50)
            amp, freq, phase = rng.uniform(4, 22), rng.uniform(0.002, 0.008), rng.uniform(0, 6.3)
            shade = rng.choice((rgb(40, 20, 8, 70), rgb(130, 80, 44, 50), rgb(60, 30, 12, 60)))
            p.setPen(QPen(shade, rng.uniform(0.8, 2.6)))
            last = None
            for xi in range(-400, int(W) + 401, 20):
                pt = QPointF(xi, y0 + math.sin(xi * freq + phase) * amp + math.sin(xi * freq * 3.1) * amp * 0.25)
                if last is not None:
                    p.drawLine(last, pt)
                last = pt
        # the speaker cloth, behind the guide: a woven panel in a carved frame
        cloth = QRectF(28, 128, W - 56, DIAL.top() - 128 - 6)
        p.setPen(QPen(rgb(30, 14, 6), 6))
        p.setBrush(rgb(70, 52, 34))
        p.drawRoundedRect(cloth, 26, 26)
        p.save()
        p.setClipRect(cloth.adjusted(3, 3, -3, -3))
        for i in range(int(cloth.width() // 5) + 2):  # the weave
            x = cloth.left() + i * 5
            p.setPen(QPen(rgb(100, 78, 52, 110) if i % 2 else rgb(50, 36, 22, 120), 2))
            p.drawLine(QPointF(x, cloth.top()), QPointF(x, cloth.bottom()))
        for j in range(int(cloth.height() // 5) + 2):
            y = cloth.top() + j * 5
            p.setPen(QPen(rgb(90, 68, 44, 70) if j % 2 else rgb(40, 28, 16, 90), 2))
            p.drawLine(QPointF(cloth.left(), y), QPointF(cloth.right(), y))
        # darker towards the cloth's edges, as if the speaker sits behind its middle
        p.setPen(Qt.NoPen)
        p.setBrush(radial(cloth.center().x(), cloth.center().y(), cloth.width() * 0.6,
                          (0, rgb(0, 0, 0, 0)), (0.7, rgb(0, 0, 0, 60)), (1, rgb(0, 0, 0, 150))))
        p.drawRect(cloth)
        p.restore()

    def _paint_dial(self, p: QPainter) -> None:
        glass = DIAL.adjusted(28, 2, -28, -6)
        p.setPen(QPen(rgb(180, 140, 70), 3))
        p.setBrush(vgrad(glass.top(), glass.bottom(), rgb(70, 40, 16), rgb(40, 22, 8)))
        p.drawRoundedRect(glass, 12, 12)
        # the scales: FM along the bottom, with ticks and numbers
        left, right = glass.left() + 110, glass.right() - 110
        base = glass.bottom() - 4
        f = QFont("serif")
        f.setPixelSize(12)
        p.setFont(f)
        for k in range(0, 41):
            mhz = 88 + k * 0.5
            x = left + (right - left) * k / 40
            tall = k % 4 == 0
            p.setPen(QPen(alpha(AMBER, 200 if tall else 110), 2 if tall else 1))
            p.drawLine(QPointF(x, base), QPointF(x, base - (10 if tall else 5)))
            if tall:
                p.setPen(alpha(AMBER, 210))
                p.drawText(QRectF(x - 30, glass.top() + 2, 60, 16), Qt.AlignCenter, f"{mhz:g}")
        p.setPen(alpha(AMBER, 170))
        f.setPixelSize(13)
        f.setItalic(True)
        p.setFont(f)
        p.drawText(QRectF(glass.left() + 16, glass.top(), 90, glass.height()), Qt.AlignLeft | Qt.AlignVCenter, "FM  MHz")


class RadioBoard(TvBoard):
    key = "radio"
    title = "Radio"
    accent = rgb(255, 170, 80)
    heading = "Radio guide"
    window_minutes = 240  # radio programmes run longer: four hours across
    channels_setting = "radio_channels"
    default_channels = tv.DEFAULT_RADIO
    panel = (rgb(26, 14, 6, 205), rgb(16, 8, 4, 220))  # dark walnut
    on_now = rgb(214, 128, 40)  # amber, like the dial

    def make_background(self):
        return ValveRadio()

    def fetch_job(self):
        """The Freeview guide's stations, plus the local ones it hasn't (MFR…)
        from Bauer's schedules."""
        if not self.channel_ids:
            return None
        cache_dir, ids = self.cache_dir, list(self.channel_ids)

        def job():
            freeview = [i for i in ids if not bauer.is_bauer(i)]
            listings = tv.fetch(cache_dir, freeview) if freeview else tv.Listings([], {}, time.time())
            local = {i: bauer.fetch_schedule(i) for i in ids if bauer.is_bauer(i)}
            if listings is None and all(v is None for v in local.values()):
                return None
            listings = listings or tv.Listings([], {}, time.time())
            by_id = {c.id: c for c in listings.channels}
            for cid, programmes in local.items():
                if programmes is not None and cid in bauer.NAMES:
                    by_id[cid] = tv.Channel(cid, bauer.NAMES[cid])
                    listings.programmes[cid] = programmes
            listings.channels = [by_id[i] for i in ids if i in by_id]
            return listings

        return job

    def badge_for(self, name: str) -> QColor:
        return station_colour(name)
