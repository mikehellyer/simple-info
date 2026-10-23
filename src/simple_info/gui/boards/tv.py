"""The TV board: a TV guide grid of your channels for the next couple of
hours, with a line for "now", over the glow of an old television set.

If you follow more channels than fit, they go onto further pages, which
take turns like the sport board's.
"""
from __future__ import annotations

import math
import zlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen

from simple_info.core import tv
from simple_info.core.settings import Settings
from simple_info.gui.boards.base import Board
from simple_info.gui.boards.broadcast import Broadcast
from simple_info.gui.paint import W, alpha, rgb, vgrad

WHITE = rgb(255, 255, 255)
DIM = rgb(255, 255, 255, 165)
FAINT = rgb(255, 255, 255, 105)
NOW_LINE = rgb(255, 92, 92)
ON_NOW = rgb(92, 104, 230)
LATER = rgb(255, 255, 255, 20)

GRID = QRectF(50, 150, 1500, 705)
CHANNEL_W = 250.0
TIMES_H = 38.0
WINDOW_MINUTES = 150  # how much of the schedule fits across
ROWS_PER_PAGE = 10

# Channel badges in their channels' own colours, roughly; the rest get a steady colour from their name.
BADGES = [
    ("BBC One", rgb(190, 30, 45)), ("BBC Two", rgb(112, 58, 160)), ("BBC Three", rgb(214, 46, 128)),
    ("BBC Four", rgb(70, 74, 86)), ("BBC Scotland", rgb(30, 92, 170)), ("BBC NEWS", rgb(176, 20, 26)),
    ("BBC", rgb(30, 30, 30)), ("STV", rgb(0, 124, 168)), ("ITV", rgb(0, 112, 150)), ("UTV", rgb(0, 112, 150)),
    ("Channel 4", rgb(44, 44, 52)), ("E4", rgb(110, 50, 140)), ("More4", rgb(0, 132, 110)), ("Film4", rgb(196, 76, 30)),
    ("5", rgb(196, 0, 112)), ("Sky", rgb(0, 84, 164)), ("U&", rgb(0, 150, 130)),
]


def font(px: float, weight=QFont.Normal) -> QFont:
    f = QFont()
    f.setPixelSize(max(1, int(px)))
    f.setWeight(weight)
    return f


def badge_colour(name: str) -> QColor:
    for prefix, colour in BADGES:
        if name == prefix or name.startswith(prefix + " ") or (prefix in ("U&",) and name.startswith(prefix)):
            return colour
    hue = zlib.crc32(name.encode()) % 360
    c = QColor()
    c.setHsl(hue, 120, 80)
    return c


class TvBoard(Board):
    key = "tv"
    title = "TV"
    accent = rgb(150, 140, 255)
    refresh_seconds = 30 * 60  # (the guide itself is only downloaded every few hours)
    retry_seconds = 5 * 60

    def __init__(self, cache_dir: Path):
        super().__init__()
        self.screen = Broadcast()
        self.cache_dir = cache_dir
        self.channel_ids: list[str] = list(tv.DEFAULT_CHANNELS)
        self.listings: Optional[tv.Listings] = None
        self.page_seconds = 20.0
        self.clock_24h = True
        self.status = "Fetching the TV guide…"
        self.offline = False

    # --- settings and data

    def configure(self, settings: Settings) -> None:
        self.clock_24h = settings.clock_24h
        self.page_seconds = float(settings.page_seconds)
        ids = [c for c in settings.tv_channels.split(",") if c]
        if ids != self.channel_ids:
            self.channel_ids = ids
            self.set_page(self.page)
            self.fetch_now()
        self.dirty = True

    def page_count(self) -> int:
        return max(1, math.ceil(len(self.channel_ids) / ROWS_PER_PAGE))

    def page_names(self) -> list[str]:
        if self.page_count() < 2:
            return []
        names = {c.id: c.short_name for c in (self.listings.channels if self.listings else [])}
        pages = []
        for i in range(self.page_count()):
            ids = self.channel_ids[i * ROWS_PER_PAGE:(i + 1) * ROWS_PER_PAGE]
            pages.append(f"{names.get(ids[0], 'Channels')} – {names.get(ids[-1], str((i + 1) * ROWS_PER_PAGE))}")
        return pages

    def fetch_job(self):
        if not self.channel_ids:
            return None
        cache_dir, ids = self.cache_dir, list(self.channel_ids)
        return lambda: tv.fetch(cache_dir, ids)

    def on_fetched(self, result) -> bool:
        if result is not None:
            self.listings = result
            self.status = ""
            # a guide more than a day old means the downloads are failing
            self.offline = datetime.now().timestamp() - result.guide_date > 24 * 3600
            return True
        self.offline = self.listings is not None
        if self.listings is None:
            self.status = "Can't get the TV guide — check your connection (retrying)"
        return False

    # --- drawing

    def step(self, dt: float) -> None:
        self.screen.step(dt)

    def paint_background(self, p: QPainter, target: QRectF) -> None:
        self.screen.paint(p, target)

    def content_key(self, now: datetime):
        return now.replace(second=0, microsecond=0), self.page

    def _time(self, when: datetime) -> str:
        return when.strftime("%H:%M") if self.clock_24h else when.strftime("%I:%M").lstrip("0") + when.strftime("%p").lower()

    def paint_content(self, p: QPainter, now: datetime) -> None:
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        self._paint_header(p, now)
        if not self.channel_ids:
            self._message(p, "Choose your channels in Settings (S)")
            return
        if self.listings is None:
            self._message(p, self.status)
            return
        self._paint_grid(p, now.astimezone())

    def _message(self, p: QPainter, text: str) -> None:
        p.setFont(font(34))
        p.setPen(DIM)
        p.drawText(QRectF(0, 440, W, 80), Qt.AlignCenter, text)

    def _paint_header(self, p: QPainter, now: datetime) -> None:
        p.setFont(font(46, QFont.DemiBold))
        p.setPen(WHITE)
        p.drawText(QRectF(54, 22, 1000, 60), Qt.AlignLeft | Qt.AlignVCenter, "TV guide")
        bits = [f"{now:%A} {now.day} {now:%B}", "Freeview"]
        if self.listings is not None:
            got = datetime.fromtimestamp(self.listings.guide_date)
            bits.append(f"listings from {got:%a} {self._time(got)}")
        if self.offline:
            bits.append("couldn't get a newer guide")
        p.setFont(font(21))
        p.setPen(DIM)
        p.drawText(QRectF(56, 84, 1100, 30), Qt.AlignLeft | Qt.AlignVCenter, " · ".join(bits))
        p.setFont(font(46, QFont.Light))
        p.setPen(WHITE)
        p.drawText(QRectF(1150, 22, 396, 60), Qt.AlignRight | Qt.AlignVCenter, self._time(now))
        n = self.page_count()
        if n > 1:
            r, gap = 6.0, 20.0
            x = 1546 - (n - 1) * gap
            p.setPen(Qt.NoPen)
            for i in range(n):
                current = i == self.page % n
                p.setBrush(WHITE if current else rgb(255, 255, 255, 80))
                p.drawEllipse(QPointF(x + i * gap, 100), r if current else r * 0.75, r if current else r * 0.75)

    def _paint_grid(self, p: QPainter, now: datetime) -> None:
        listings = self.listings
        start = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
        end = start + timedelta(minutes=WINDOW_MINUTES)
        left = GRID.left() + CHANNEL_W
        per_minute = (GRID.right() - left) / WINDOW_MINUTES

        def x_at(when: datetime) -> float:
            return left + (when - start).total_seconds() / 60 * per_minute

        # the panel behind it all
        p.setPen(QPen(rgb(255, 255, 255, 40), 1))
        p.setBrush(vgrad(GRID.top(), GRID.bottom(), rgb(10, 10, 26, 200), rgb(6, 6, 16, 215)))
        p.drawRoundedRect(GRID, 18, 18)

        # times along the top, every half hour
        p.setFont(font(19, QFont.DemiBold))
        for i in range(WINDOW_MINUTES // 30 + 1):
            t = start + timedelta(minutes=30 * i)
            x = x_at(t)
            p.setPen(QPen(rgb(255, 255, 255, 28), 1))
            p.drawLine(QPointF(x, GRID.top() + TIMES_H), QPointF(x, GRID.bottom() - 10))
            if i < WINDOW_MINUTES // 30:
                p.setPen(DIM)
                p.drawText(QRectF(x + 8, GRID.top() + 4, 150, TIMES_H - 4), Qt.AlignLeft | Qt.AlignVCenter, self._time(t))

        page = self.page % self.page_count()
        channels = [c for c in listings.channels if c.id in self.channel_ids]
        channels.sort(key=lambda c: self.channel_ids.index(c.id))
        channels = channels[page * ROWS_PER_PAGE:(page + 1) * ROWS_PER_PAGE]
        if not channels:
            return
        top = GRID.top() + TIMES_H + 4
        row_h = min(64.0, (GRID.bottom() - 12 - top) / max(len(channels), 1))
        for i, channel in enumerate(channels):
            y = top + i * row_h
            self._channel_badge(p, channel, QRectF(GRID.left() + 14, y + 5, CHANNEL_W - 26, row_h - 10))
            for prog in listings.programmes.get(channel.id, []):
                if prog.stop <= start or prog.start >= end:
                    continue
                x0, x1 = max(left, x_at(prog.start)), min(GRID.right() - 10, x_at(prog.stop))
                if x1 - x0 < 6:
                    continue
                self._programme(p, prog, QRectF(x0 + 2, y + 5, x1 - x0 - 4, row_h - 10), now, x_at(prog.start) < left)

        # the now line
        x = x_at(now)
        p.setPen(QPen(NOW_LINE, 2.5))
        p.drawLine(QPointF(x, GRID.top() + TIMES_H - 4), QPointF(x, top + len(channels) * row_h))
        p.setPen(Qt.NoPen)
        p.setBrush(NOW_LINE)
        p.drawEllipse(QPointF(x, GRID.top() + TIMES_H - 4), 5, 5)

    def _channel_badge(self, p: QPainter, channel: tv.Channel, rect: QRectF) -> None:
        colour = badge_colour(channel.short_name)
        p.setPen(QPen(rgb(255, 255, 255, 60), 1))
        p.setBrush(vgrad(rect.top(), rect.bottom(), colour.lighter(118), colour.darker(125)))
        p.drawRoundedRect(rect, 10, 10)
        f = font(min(22, rect.height() * 0.42), QFont.Bold)
        while QFontMetricsF(f).horizontalAdvance(channel.short_name) > rect.width() - 20 and f.pixelSize() > 14:
            f.setPixelSize(f.pixelSize() - 1)  # shrink a long name to fit, rather than cut it short
        p.setFont(f)
        p.setPen(WHITE)
        p.drawText(rect.adjusted(12, 0, -8, 0), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetricsF(f).elidedText(channel.short_name, Qt.ElideRight, rect.width() - 20))

    def _programme(self, p: QPainter, prog: tv.Programme, rect: QRectF, now: datetime, started_before: bool) -> None:
        on_now = prog.on_at(now)
        p.setPen(Qt.NoPen)
        if on_now:
            p.setBrush(vgrad(rect.top(), rect.bottom(), alpha(ON_NOW, 220), alpha(ON_NOW.darker(130), 220)))
        else:
            p.setBrush(LATER)
        p.drawRoundedRect(rect, 8, 8)
        if on_now:  # how far through it is
            bar = QRectF(rect.left() + 8, rect.bottom() - 6, rect.width() - 16, 3)
            p.setBrush(rgb(255, 255, 255, 60))
            p.drawRect(bar)
            p.setBrush(WHITE)
            p.drawRect(QRectF(bar.left(), bar.top(), bar.width() * prog.progress(now), bar.height()))
        if rect.width() < 28:
            return
        inner = rect.adjusted(10, 3, -8, -6)
        title_f = font(min(21, rect.height() * 0.36), QFont.DemiBold if on_now else QFont.Normal)
        p.setFont(title_f)
        p.setPen(WHITE if on_now else rgb(255, 255, 255, 215))
        title = ("‹ " if started_before else "") + prog.title
        p.drawText(QRectF(inner.left(), inner.top(), inner.width(), inner.height() * 0.58), Qt.AlignLeft | Qt.AlignBottom,
                   QFontMetricsF(title_f).elidedText(title, Qt.ElideRight, inner.width()))
        p.setFont(font(min(16, rect.height() * 0.27)))
        p.setPen(rgb(255, 255, 255, 190) if on_now else FAINT)
        when = f"{self._time(prog.start.astimezone())}–{self._time(prog.stop.astimezone())}"
        if prog.episode and inner.width() > 200:
            when += f"  ·  {prog.episode}"
        p.drawText(QRectF(inner.left(), inner.top() + inner.height() * 0.6, inner.width(), inner.height() * 0.4),
                   Qt.AlignLeft | Qt.AlignTop, QFontMetricsF(p.font()).elidedText(when, Qt.ElideRight, inner.width()))
