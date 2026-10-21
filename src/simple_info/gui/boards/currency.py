"""The currency board: what one of your currency buys abroad, with each
rate's move since the day before and its last month as a trend line, on
a banknote-green background. Bitcoin and Ethereum can join in too."""
from __future__ import annotations

import colorsys
import math
import zlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QFontMetricsF, QPainter, QPainterPath, QPen

from simple_info.core import currency as cx
from simple_info.core.settings import Settings
from simple_info.gui.boards.banknote import Banknote
from simple_info.gui.boards.base import Board
from simple_info.gui.paint import W, alpha, rgb, vgrad

CREAM = rgb(246, 240, 222)
DIM = rgb(246, 240, 222, 160)
FAINT = rgb(246, 240, 222, 105)
GOLD = rgb(226, 196, 120)
UP = rgb(110, 224, 150)
DOWN = rgb(255, 118, 104)
FLAT = rgb(200, 200, 190)

GRID = QRectF(50, 150, 1500, 700)
GAP = 22


def font(px: float, weight=QFont.Normal) -> QFont:
    f = QFont()
    f.setPixelSize(max(1, int(px)))
    f.setWeight(weight)
    return f


def badge_colour(code: str):
    """A steady colour for each currency's badge, from its code."""
    hue = (zlib.crc32(code.encode()) % 360) / 360
    r, g, b = colorsys.hls_to_rgb(hue, 0.42, 0.55)
    return rgb(r * 255, g * 255, b * 255)


def _trend_colour(values: list[float]):
    if len(values) < 2 or abs(values[-1] / values[0] - 1) < 0.0005:
        return FLAT
    return UP if values[-1] > values[0] else DOWN


def _change_colour(percent: float):
    return UP if percent > 0.005 else DOWN if percent < -0.005 else FLAT


class CurrencyBoard(Board):
    key = "currency"
    title = "Currency"
    accent = rgb(120, 210, 160)
    refresh_seconds = 15 * 60
    retry_seconds = 2 * 60

    def __init__(self, cache_dir: Path):
        super().__init__()
        self.note = Banknote()
        self._cache_path = cache_dir / "rates.json"
        self.rates: Optional[cx.Rates] = cx.load_rates(self._cache_path)
        self.base = "GBP"
        self.codes: list[str] = list(cx.DEFAULT_CODES)
        self.crypto = True
        self.clock_24h = True
        self.status = "" if self.rates else "Fetching the exchange rates…"
        self.offline = False

    # --- settings and data

    def configure(self, settings: Settings) -> None:
        self.clock_24h = settings.clock_24h
        codes = [c for c in settings.currency_codes.split(",") if c in cx.CURRENCIES and c != settings.currency_base]
        wanted = (settings.currency_base, codes, settings.currency_crypto)
        if wanted != (self.base, self.codes, self.crypto):
            self.base, self.codes, self.crypto = wanted
            if self.rates is not None and (self.rates.base != self.base or not self.crypto and self.rates.coins):
                self.rates = None
                self.status = "Fetching the exchange rates…"
            self.fetch_now()
        self.dirty = True

    def fetch_job(self):
        if not self.codes and not self.crypto:
            return None
        base, codes, crypto = self.base, list(self.codes) or ["EUR" if self.base != "EUR" else "USD"], self.crypto
        return lambda: cx.fetch(base, codes, crypto)

    def on_fetched(self, result) -> bool:
        if result is not None:
            self.rates = result
            self.status, self.offline = "", False
            cx.save_rates(result, self._cache_path)
            return True
        self.offline = self.rates is not None
        if self.rates is None:
            self.status = "Can't reach the exchange rates — check your connection (retrying)"
        return False

    # --- drawing

    def step(self, dt: float) -> None:
        self.note.step(dt)

    def paint_background(self, p: QPainter, target: QRectF) -> None:
        self.note.paint(p, target)

    def content_key(self, now: datetime):
        return now.replace(second=0, microsecond=0)  # the clock here shows minutes only

    def paint_content(self, p: QPainter, now: datetime) -> None:
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        self._paint_header(p, now)
        r = self.rates
        if r is None:
            p.setFont(font(34))
            p.setPen(DIM)
            p.drawText(QRectF(0, 440, W, 80), Qt.AlignCenter, self.status)
            return
        wanted = [code for code in self.codes]
        rates = sorted((x for x in r.rates if x.code in wanted), key=lambda x: wanted.index(x.code))
        cards: list = [*rates, *(r.coins if self.crypto else [])]
        if not cards:
            return
        cols = 3 if len(cards) <= 9 else 4
        rows = math.ceil(len(cards) / cols)
        w = (GRID.width() - GAP * (cols - 1)) / cols
        h = min(260.0, (GRID.height() - GAP * (rows - 1)) / rows)
        top = GRID.top() + (GRID.height() - (h * rows + GAP * (rows - 1))) / 2
        for i, item in enumerate(cards):
            rect = QRectF(GRID.left() + (i % cols) * (w + GAP), top + (i // cols) * (h + GAP), w, h)
            if isinstance(item, cx.Coin):
                self._paint_coin(p, rect, item)
            else:
                self._paint_rate(p, rect, item)

    def _paint_header(self, p: QPainter, now: datetime) -> None:
        base_name, base_symbol = cx.CURRENCIES.get(self.base, (self.base, ""))
        p.setPen(CREAM)
        p.setFont(font(46, QFont.DemiBold))
        p.drawText(QRectF(54, 26, 900, 60), Qt.AlignLeft | Qt.AlignVCenter, f"What {base_symbol}1 buys")
        sub = f"{base_name} exchange rates"
        r = self.rates
        if r is not None and r.date:
            day = datetime.fromisoformat(r.date)
            sub += f" · European Central Bank, {day:%A} {day.day} {day:%B}"
        if self.offline:
            sub += " · offline — showing the last rates"
        p.setFont(font(21))
        p.setPen(DIM)
        p.drawText(QRectF(56, 88, 1100, 32), Qt.AlignLeft | Qt.AlignVCenter, sub)
        clock = now.strftime("%H:%M") if self.clock_24h else now.strftime("%I:%M %p").lstrip("0")
        p.setFont(font(46, QFont.Light))
        p.setPen(CREAM)
        p.drawText(QRectF(1150, 26, 396, 60), Qt.AlignRight | Qt.AlignVCenter, clock)
        p.setFont(font(21))
        p.setPen(DIM)
        p.drawText(QRectF(1150, 88, 396, 32), Qt.AlignRight | Qt.AlignVCenter, f"{now:%A} {now.day} {now:%B}")

    def _card(self, p: QPainter, rect: QRectF) -> None:
        p.setPen(QPen(alpha(GOLD, 70), 1.2))
        p.setBrush(vgrad(rect.top(), rect.bottom(), rgb(4, 20, 16, 150), rgb(2, 12, 10, 175)))
        p.drawRoundedRect(rect, 18, 18)

    def _badge(self, p: QPainter, centre: QPointF, radius: float, text: str, colour) -> None:
        p.setPen(QPen(alpha(GOLD, 200), radius * 0.08))
        p.setBrush(vgrad(centre.y() - radius, centre.y() + radius, colour.lighter(125), colour.darker(140)))
        p.drawEllipse(centre, radius, radius)
        size = radius * (1.0 if len(text) <= 1 else 0.8 if len(text) == 2 else 0.62)
        p.setFont(font(size, QFont.Bold))
        p.setPen(CREAM)
        p.drawText(QRectF(centre.x() - radius, centre.y() - radius, radius * 2, radius * 2), Qt.AlignCenter, text)

    def _top_lines(self, p: QPainter, rect: QRectF, k: float, code: str, name: str, symbol: str, colour) -> float:
        """The badge, code and name along a card's top. Returns where the text ends."""
        pad = 20 * k
        radius = 30 * k
        self._badge(p, QPointF(rect.left() + pad + radius, rect.top() + pad + radius), radius, symbol, colour)
        x = rect.left() + pad * 1.6 + radius * 2
        p.setPen(CREAM)
        p.setFont(font(30 * k, QFont.Bold))
        p.drawText(QRectF(x, rect.top() + pad - 2 * k, rect.width(), 36 * k), Qt.AlignLeft | Qt.AlignVCenter, code)
        p.setPen(DIM)
        p.setFont(font(18 * k))
        width = rect.width() * 0.5 - (x - rect.left())
        p.drawText(QRectF(x, rect.top() + pad + 34 * k, width, 26 * k), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetricsF(p.font()).elidedText(name, Qt.ElideRight, width))
        return x

    def _big_number(self, p: QPainter, rect: QRectF, k: float, text: str, change: float, note: str) -> None:
        pad = 20 * k
        p.setPen(CREAM)
        big = font(48 * k, QFont.DemiBold)
        width = rect.width() * 0.56
        while QFontMetricsF(big).horizontalAdvance(text) > width and big.pixelSize() > 12:
            big.setPixelSize(big.pixelSize() - 2)
        p.setFont(big)
        p.drawText(QRectF(rect.right() - pad - width, rect.top() + pad - 6 * k, width, 58 * k), Qt.AlignRight | Qt.AlignVCenter, text)
        p.setFont(font(20 * k, QFont.DemiBold))
        p.setPen(_change_colour(change))
        p.drawText(QRectF(rect.right() - pad - width, rect.top() + pad + 50 * k, width, 28 * k), Qt.AlignRight | Qt.AlignVCenter,
                   f"{cx.format_change(change)}  {note}")

    def _sparkline(self, p: QPainter, rect: QRectF, values: list[float], label: str) -> None:
        if len(values) < 2:
            return
        lo, hi = min(values), max(values)
        span = (hi - lo) or abs(hi) * 0.001 or 1.0
        colour = _trend_colour(values)
        pts = [QPointF(rect.left() + rect.width() * i / (len(values) - 1),
                       rect.bottom() - (v - lo) / span * rect.height()) for i, v in enumerate(values)]
        area = QPainterPath(pts[0])
        for pt in pts[1:]:
            area.lineTo(pt)
        line = QPainterPath(area)
        area.lineTo(rect.right(), rect.bottom() + 6)
        area.lineTo(rect.left(), rect.bottom() + 6)
        area.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(vgrad(rect.top(), rect.bottom() + 6, alpha(colour, 70), alpha(colour, 0)))
        p.drawPath(area)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(colour, 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(line)
        p.setPen(Qt.NoPen)
        p.setBrush(colour)
        p.drawEllipse(pts[-1], 4, 4)
        p.setFont(font(14))
        p.setPen(FAINT)
        p.drawText(QRectF(rect.left(), rect.top() - 20, rect.width(), 18), Qt.AlignLeft | Qt.AlignVCenter, label)

    def _paint_rate(self, p: QPainter, rect: QRectF, rate: cx.Rate) -> None:
        self._card(p, rect)
        k = min(rect.width() / 484, rect.height() / 220)
        pad = 20 * k
        self._top_lines(p, rect, k, rate.code, rate.name, rate.symbol, badge_colour(rate.code))
        self._big_number(p, rect, k, f"{rate.symbol}{cx.format_rate(rate.rate)}" if len(rate.symbol) <= 3 else cx.format_rate(rate.rate),
                         rate.change, "on the day")
        spark = QRectF(rect.left() + pad, rect.top() + 128 * k, rect.width() * 0.62, rect.bottom() - pad - (rect.top() + 128 * k))
        self._sparkline(p, spark, rate.history, "last month")
        # and the other way round
        base_symbol = cx.CURRENCIES.get(self.base, ("", self.base))[1]
        inverse = 1 / rate.rate if rate.rate else 0
        p.setFont(font(17 * k))
        p.setPen(DIM)
        box = QRectF(spark.right() + pad, spark.bottom() - 46 * k, rect.right() - pad - spark.right() - pad, 46 * k)
        p.drawText(box, Qt.AlignRight | Qt.AlignBottom | Qt.TextWordWrap, f"1 {rate.code} =\n{cx.format_money(inverse, base_symbol)}")

    def _paint_coin(self, p: QPainter, rect: QRectF, coin: cx.Coin) -> None:
        self._card(p, rect)
        k = min(rect.width() / 484, rect.height() / 220)
        pad = 20 * k
        self._top_lines(p, rect, k, coin.name, "one coin costs", coin.symbol, rgb(210, 150, 40) if coin.id == "bitcoin" else rgb(100, 110, 180))
        base_symbol = cx.CURRENCIES.get(self.base, ("", self.base))[1]
        self._big_number(p, rect, k, cx.format_money(coin.price, base_symbol), coin.change, "24 hrs")
        spark = QRectF(rect.left() + pad, rect.top() + 128 * k, rect.width() - pad * 2, rect.bottom() - pad - (rect.top() + 128 * k))
        self._sparkline(p, spark, coin.history, "last week")
