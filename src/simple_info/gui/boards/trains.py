"""The train board: live departures and arrivals for a station, on an amber
dot-matrix display hanging in a Victorian train shed.

Like the boards on British platforms, the first train gets a line of its
own that scrolls through where it calls, and station notices scroll along
the bottom beside the clock.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Hashable, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QFont, QFontMetricsF, QImage, QPainter, QPen

from simple_info.core import trains as tr
from simple_info.core.settings import Settings
from simple_info.gui.boards.base import Board
from simple_info.gui.boards.station import StationHall
from simple_info.gui.paint import radial, rgb, vgrad

AMBER = rgb(255, 172, 0)
AMBER_DIM = rgb(200, 120, 0)
LATE = rgb(255, 120, 30)
CANCELLED = rgb(255, 64, 40)
SCREEN = rgb(8, 7, 4)

CASE = QRectF(70, 96, 1460, 732)  # the board's steel case
DISPLAY = CASE.adjusted(22, 22, -22, -22)  # the black dot-matrix screen inside it
LEFT, RIGHT = DISPLAY.left() + 26, DISPLAY.right() - 26
# columns: time, destination (or origin), platform, expected
COL_TIME, COL_PLACE, COL_PLAT, COL_EXP = LEFT, LEFT + 150, RIGHT - 400, RIGHT - 250
FIRST_ROW = DISPLAY.top() + 132
CALLING_ROW = QRectF(LEFT, FIRST_ROW + 54, RIGHT - LEFT, 40)
ROW_HEIGHT = 50
OTHER_ROWS = FIRST_ROW + 160  # where the second train's row starts
BOTTOM_ROW = QRectF(LEFT, DISPLAY.bottom() - 66, RIGHT - LEFT, 52)
CLOCK_WIDTH = 230
TICKER = QRectF(BOTTOM_ROW.left(), BOTTOM_ROW.top(), BOTTOM_ROW.width() - CLOCK_WIDTH - 30, BOTTOM_ROW.height())
MAX_ROWS = 8  # the first train and seven more
BOTH_SECONDS = 20  # in "both" mode, how long departures and arrivals each show
SCROLL_SPEED = 120.0  # virtual pixels a second


def font(px: float, weight=QFont.DemiBold) -> QFont:
    f = QFont()
    f.setPixelSize(max(1, int(px)))
    f.setWeight(weight)
    return f


def _status_colour(service: tr.Service):
    return {tr.CANCELLED: CANCELLED, tr.LATE: LATE}.get(service.status, AMBER)


class Marquee:
    """A line of text scrolling right to left through a strip, round and round."""

    def __init__(self, px: float):
        self.font = font(px)
        self._metrics = QFontMetricsF(self.font)
        self.text = ""
        self._width = 0.0
        self._start = 0.0

    def set_text(self, text: str, t: float) -> None:
        if text != self.text:
            self.text = text
            self._width = self._metrics.horizontalAdvance(text)
            self._start = t

    def paint(self, p: QPainter, rect: QRectF, t: float, colour) -> None:
        if not self.text:
            return
        if self._width <= rect.width():  # it fits: no need to move
            x = rect.left()
        else:  # in from the right, out to the left, a short pause, and round again
            travel = self._width + rect.width() + 200
            x = rect.right() - (max(0.0, t - self._start) * SCROLL_SPEED) % travel
        p.save()
        p.setClipRect(rect)
        p.setFont(self.font)
        p.setPen(colour)
        p.drawText(QRectF(x, rect.top(), self._width + 10, rect.height()), Qt.AlignLeft | Qt.AlignVCenter, self.text)
        p.restore()


class Grille:
    """The dark gaps between a dot-matrix display's LEDs, laid over whatever
    was drawn on it so the text looks made of dots. Done as a small tile in
    real pixels (not scaled), so the dots stay crisp at any size."""

    def __init__(self):
        self._tile: Optional[QImage] = None
        self._pitch = 0

    def _tile_for(self, pitch: int) -> QImage:
        if self._tile is None or pitch != self._pitch:
            self._pitch = pitch
            img = QImage(pitch, pitch, QImage.Format_ARGB32_Premultiplied)
            img.fill(Qt.transparent)
            gap = 1 if pitch < 6 else 2
            dark = rgb(0, 0, 0, 170)
            for i in range(pitch):
                for g in range(gap):
                    img.setPixelColor(i, pitch - 1 - g, dark)
                    img.setPixelColor(pitch - 1 - g, i, dark)
            # round the dots' corners off a little
            if pitch >= 4:
                for x, y in ((0, 0), (pitch - 1 - gap, 0), (0, pitch - 1 - gap), (pitch - 1 - gap, pitch - 1 - gap)):
                    img.setPixelColor(x, y, rgb(0, 0, 0, 90))
            self._tile = img
        return self._tile

    def paint(self, p: QPainter, rect: QRectF) -> None:
        device = p.transform().mapRect(rect)
        pitch = max(3, round(4 * p.transform().m11()))  # LEDs 4 virtual pixels apart
        p.save()
        p.resetTransform()
        p.setBrushOrigin(device.topLeft())
        p.fillRect(device, QBrush(self._tile_for(pitch)))
        p.restore()


class TrainBoard(Board):
    key = "trains"
    title = "Trains"
    accent = rgb(255, 172, 0)
    refresh_seconds = 60
    retry_seconds = 30
    has_live = True

    def __init__(self):
        super().__init__()
        self.hall = StationHall()
        self.crs = ""
        self.station_name = ""
        self.mode = tr.DEPARTURES
        self.filter_crs = ""
        self.filter_name = ""
        self.token = ""
        self.clock_24h = True
        self.boards: dict[str, tr.TrainBoard] = {}
        self.status = ""
        self.offline = False
        self._grille = Grille()
        self._calling = Marquee(26)
        self._ticker = Marquee(26)

    # --- settings and data

    def configure(self, settings: Settings) -> None:
        self.clock_24h = settings.clock_24h
        wanted = (settings.train_station_crs, settings.train_mode, settings.train_filter_crs, settings.rail_token)
        if wanted != (self.crs, self.mode, self.filter_crs, self.token):
            self.crs, self.mode, self.filter_crs, self.token = wanted
            self.boards = {}
            self.offline = False
            self.status = "Fetching the trains…" if self.crs else ""
            self.fetch_now()
        self.station_name = settings.train_station_name
        self.filter_name = settings.train_filter_name
        self.dirty = True

    def _kinds(self) -> list[str]:
        return [tr.DEPARTURES, tr.ARRIVALS] if self.mode == "both" else [self.mode]

    def fetch_job(self):
        if not self.crs:
            return None
        crs, kinds, filter_crs, token = self.crs, self._kinds(), self.filter_crs, self.token

        def job():
            return {kind: tr.fetch_board(crs, kind, 10, filter_crs, token) for kind in kinds}

        return job

    def on_fetched(self, result) -> bool:
        got = {kind: board for kind, board in (result or {}).items() if board is not None}
        self.boards.update(got)
        ok = bool(got) and len(got) == len(self._kinds())
        self.offline = not ok and bool(self.boards)
        if ok or self.boards:
            self.status = ""
        else:
            self.status = "Can't reach National Rail's live departures — check your connection (retrying)"
        return ok

    def showing(self, t: Optional[float] = None) -> str:
        """Which board is up now: in "both" mode they take turns."""
        if self.mode != "both":
            return self.mode
        t = time.time() if t is None else t
        return tr.DEPARTURES if int(t // BOTH_SECONDS) % 2 == 0 else tr.ARRIVALS

    # --- drawing

    def step(self, dt: float) -> None:
        self.hall.step(dt)

    def paint_background(self, p: QPainter, target: QRectF) -> None:
        self.hall.paint(p, target)

    def content_key(self, now: datetime) -> Hashable:
        return now.replace(microsecond=0), self.showing(now.timestamp())

    def paint_content(self, p: QPainter, now: datetime) -> None:
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        self._paint_case(p)
        kind = self.showing(now.timestamp())
        board = self.boards.get(kind)
        self._paint_header(p, kind, board)
        if not self.crs:
            self._paint_notice(p, "Choose your station in Settings (S)",
                               "Any station in Great Britain: its departures, its arrivals, or both in turn.")
        elif board is None:
            self._paint_notice(p, self.status or "Fetching the trains…", "")
        elif not board.services:
            self._paint_notice(p, f"No {'departures' if kind == tr.DEPARTURES else 'arrivals'} in the next two hours", "")
        else:
            self._paint_trains(p, kind, board)
        self._paint_clock(p, now)
        self._grille.paint(p, DISPLAY)

    def _paint_case(self, p: QPainter) -> None:
        # hung from the roof on two rods
        p.setPen(QPen(rgb(30, 32, 36), 8))
        for x in (CASE.left() + 260, CASE.right() - 260):
            p.drawLine(QPointF(x, -10), QPointF(x, CASE.top()))
        p.setPen(Qt.NoPen)
        p.setBrush(radial(CASE.center().x(), CASE.center().y(), CASE.width() * 0.6,
                          (0, rgb(255, 150, 20, 40)), (1, rgb(255, 150, 20, 0))))
        p.drawEllipse(CASE.center(), CASE.width() * 0.62, CASE.height() * 0.75)
        p.setBrush(vgrad(CASE.top(), CASE.bottom(), rgb(74, 78, 86), rgb(36, 38, 44)))
        p.setPen(QPen(rgb(110, 116, 126), 2))
        p.drawRoundedRect(CASE, 16, 16)
        p.setPen(QPen(rgb(0, 0, 0), 3))
        p.setBrush(SCREEN)
        p.drawRoundedRect(DISPLAY, 6, 6)

    def _place_heading(self, kind: str) -> str:
        return "Destination" if kind == tr.DEPARTURES else "From"

    def _paint_header(self, p: QPainter, kind: str, board: Optional[tr.TrainBoard]) -> None:
        name = (board.station if board else "") or self.station_name or "Trains"
        title = "Departures" if kind == tr.DEPARTURES else "Arrivals"
        top = DISPLAY.top() + 14
        p.setFont(font(40))
        p.setPen(AMBER)
        p.drawText(QRectF(LEFT, top, RIGHT - LEFT - 360, 52), Qt.AlignLeft | Qt.AlignVCenter, name)
        p.drawText(QRectF(RIGHT - 360, top, 360, 52), Qt.AlignRight | Qt.AlignVCenter, title)
        note = ""
        if self.filter_crs:
            note = f"{'Calling at' if kind == tr.DEPARTURES else 'Coming from'} {self.filter_name or self.filter_crs}"
        if self.offline:
            note = (note + " · " if note else "") + "offline — showing the last trains"
        if note:
            p.setFont(font(20))
            p.setPen(AMBER_DIM)
            p.drawText(QRectF(LEFT, top + 50, RIGHT - LEFT, 26), Qt.AlignLeft | Qt.AlignVCenter, note)
        if self.crs:
            p.setFont(font(20))
            p.setPen(AMBER_DIM)
            y = FIRST_ROW - 38
            for x, w, text, align in ((COL_TIME, 140, "Time", Qt.AlignLeft), (COL_PLACE, COL_PLAT - COL_PLACE, self._place_heading(kind), Qt.AlignLeft),
                                      (COL_PLAT, 120, "Plat", Qt.AlignLeft), (COL_EXP, RIGHT - COL_EXP, "Expected", Qt.AlignRight)):
                p.drawText(QRectF(x, y, w, 28), align | Qt.AlignVCenter, text)

    def _paint_notice(self, p: QPainter, text: str, detail: str) -> None:
        p.setFont(font(36))
        p.setPen(AMBER)
        p.drawText(QRectF(LEFT, DISPLAY.top() + 230, RIGHT - LEFT, 60), Qt.AlignCenter, text)
        if detail:
            p.setFont(font(24))
            p.setPen(AMBER_DIM)
            p.drawText(QRectF(LEFT, DISPLAY.top() + 300, RIGHT - LEFT, 40), Qt.AlignCenter, detail)

    def _row(self, p: QPainter, s: tr.Service, kind: str, y: float, h: float, px: float) -> None:
        place = s.destination if kind == tr.DEPARTURES else s.origin or s.destination
        if s.via and kind == tr.DEPARTURES:
            place = f"{place} {s.via}"
        p.setFont(font(px))
        p.setPen(AMBER)
        p.drawText(QRectF(COL_TIME, y, 140, h), Qt.AlignLeft | Qt.AlignVCenter, s.scheduled)
        metrics = QFontMetricsF(p.font())
        p.drawText(QRectF(COL_PLACE, y, COL_PLAT - COL_PLACE - 20, h), Qt.AlignLeft | Qt.AlignVCenter,
                   metrics.elidedText(place, Qt.ElideRight, COL_PLAT - COL_PLACE - 20))
        p.drawText(QRectF(COL_PLAT, y, 120, h), Qt.AlignLeft | Qt.AlignVCenter, s.platform or "–")
        p.setPen(_status_colour(s))
        p.drawText(QRectF(COL_EXP - 40, y, RIGHT - COL_EXP + 40, h), Qt.AlignRight | Qt.AlignVCenter, s.expected_text)

    def _paint_trains(self, p: QPainter, kind: str, board: tr.TrainBoard) -> None:
        first, *rest = board.services[:MAX_ROWS]
        self._row(p, first, kind, FIRST_ROW, 54, 36)
        # under the first train (the calling points scroll in the live layer): who runs it, and why it's late
        details = [first.operator]
        if first.coaches:
            details.append(f"{first.coaches} coaches")
        if first.reason:
            details.append(first.reason)
        p.setFont(font(21, QFont.Normal))
        p.setPen(AMBER_DIM)
        p.drawText(QRectF(LEFT, CALLING_ROW.bottom() + 2, RIGHT - LEFT, 30), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetricsF(p.font()).elidedText(" · ".join(d for d in details if d), Qt.ElideRight, RIGHT - LEFT))
        for i, s in enumerate(rest):
            y = OTHER_ROWS + i * ROW_HEIGHT
            if y + ROW_HEIGHT > BOTTOM_ROW.top() - 4:
                break
            self._row(p, s, kind, y, ROW_HEIGHT, 30)

    def _paint_clock(self, p: QPainter, now: datetime) -> None:
        text = now.strftime("%H:%M:%S") if self.clock_24h else now.strftime("%I:%M:%S").lstrip("0")
        p.setFont(font(44))
        p.setPen(AMBER)
        p.drawText(QRectF(BOTTOM_ROW.right() - CLOCK_WIDTH, BOTTOM_ROW.top(), CLOCK_WIDTH, BOTTOM_ROW.height()),
                   Qt.AlignRight | Qt.AlignVCenter, text)

    def paint_live(self, p: QPainter, t: float) -> None:
        board = self.boards.get(self.showing()) if self.crs else None
        if board is None:
            return
        p.setRenderHint(QPainter.TextAntialiasing)
        calling = tr.calling_at_text(board.services[0], board.kind) if board.services else ""
        self._calling.set_text(calling, t)
        self._ticker.set_text("     •     ".join(board.messages), t)
        for marquee, rect in ((self._calling, CALLING_ROW), (self._ticker, TICKER)):
            if marquee.text:
                p.fillRect(rect, SCREEN)  # (over the content's own grille, so the dots aren't doubled)
                marquee.paint(p, rect, t, AMBER)
                self._grille.paint(p, rect)
