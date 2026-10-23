"""The sport board: a page for each competition you follow, taking turns,
over a floodlit stadium marked out for that sport.

Football, rugby and baseball pages show the live games, the latest
results and what's coming up beside the league table. Cricket has no
table, so its page is a grid of scorecards: what's on now, what's just
finished and what's next.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen

from simple_info.core import sports as sp
from simple_info.core.settings import Settings
from simple_info.gui.boards.base import TITLE_WIDTH, Board, fit_title
from simple_info.gui.boards.stadium import Stadium
from simple_info.gui.paint import W, alpha, rgb, vgrad

WHITE = rgb(255, 255, 255)
DIM = rgb(255, 255, 255, 165)
FAINT = rgb(255, 255, 255, 110)
LIVE_RED = rgb(240, 64, 64)
GOLD = rgb(255, 210, 90)

MATCHES = QRectF(50, 140, 880, 712)
TABLE = QRectF(958, 140, 592, 712)
ROW = 40.0
DAY_ROW = 34.0
LIVE_REFRESH = 60  # seconds between fetches while a game is on
QUIET_REFRESH = 10 * 60


def font(px: float, weight=QFont.Normal) -> QFont:
    f = QFont()
    f.setPixelSize(max(1, int(px)))
    f.setWeight(weight)
    return f


def _colour(hex_colour: str) -> Optional[QColor]:
    if len(hex_colour) == 6:
        try:
            return rgb(int(hex_colour[0:2], 16), int(hex_colour[2:4], 16), int(hex_colour[4:6], 16))
        except ValueError:
            return None
    return None


def _day_label(d: datetime, now: datetime) -> str:
    delta = (d.date() - now.date()).days
    if delta == 0:
        return "Today"
    if delta == -1:
        return "Yesterday"
    if delta == 1:
        return "Tomorrow"
    return f"{d:%A} {d.day} {d:%B}"


class SportBoard(Board):
    key = "sport"
    title = "Sport"
    accent = rgb(90, 200, 110)
    refresh_seconds = QUIET_REFRESH
    retry_seconds = 2 * 60

    def __init__(self):
        super().__init__()
        self.stadium = Stadium()
        self.keys: list[str] = list(sp.DEFAULT_KEYS)
        self.data: dict[str, sp.CompetitionData] = {}
        self.page_seconds = 20.0
        self.clock_24h = True
        self.offline = False
        self._cache: dict = {}  # finished match days and tables, so they aren't fetched again
        self._colours: dict[str, str] = {}  # team name -> colour, learned from the matches (tables don't say)
        self._asked: list[str] = []  # the competitions the last fetch was for
        self.favourites: dict[str, str] = {}  # competition key -> favourite team's id (or, for cricket, name)
        self._fav: set = set()  # the favourite on the page being drawn

    # --- settings and data

    def configure(self, settings: Settings) -> None:
        self.clock_24h = settings.clock_24h
        self.page_seconds = float(settings.page_seconds)
        self.favourites = sp.parse_favourites(settings.sport_favourites)
        keys = [k for k in settings.sport_competitions.split(",") if k in sp.BY_KEY]
        if keys != self.keys:
            self.keys = keys
            self.data = {k: v for k, v in self.data.items() if k in keys}
            self.set_page(self.page)
            self.fetch_now()
        self.dirty = True

    def page_count(self) -> int:
        return max(1, len(self.keys))

    def page_names(self) -> list[str]:
        return [sp.BY_KEY[k].name for k in self.keys]

    def fetch_job(self):
        if not self.keys:
            return None
        # every minute while a game is on, but only for the competitions with one
        now = time.time()
        keys = [k for k in self.keys if k not in self.data or self.data[k].live
                or now - self.data[k].fetched_at > QUIET_REFRESH - 30]
        if not keys:
            return None
        cache = self._cache
        self._asked = keys

        def job():
            return {key: sp.fetch_competition(key, cache=cache) for key in keys}

        return job

    def on_fetched(self, result) -> bool:
        got = {k: v for k, v in (result or {}).items() if v is not None}
        self.data.update(got)
        for d in got.values():
            for m in d.matches:
                for team in (m.home, m.away):
                    if team.colour:
                        self._colours[team.name] = team.colour
        ok = bool(got) and len(got) == len(self._asked)
        self.offline = not ok and bool(self.data)
        live = any(d.live for d in self.data.values())
        self.refresh_seconds = LIVE_REFRESH if live else QUIET_REFRESH
        return ok

    def _team_colour(self, team: sp.Team) -> QColor:
        c = _colour(team.colour or self._colours.get(team.name, ""))
        return c if c is not None else rgb(130, 136, 146)

    # --- drawing

    def current(self) -> tuple[Optional[str], Optional[sp.CompetitionData]]:
        if not self.keys:
            return None, None
        key = self.keys[self.page % len(self.keys)]
        return key, self.data.get(key)

    def step(self, dt: float) -> None:
        self.stadium.step(dt)

    def paint_background(self, p: QPainter, target: QRectF) -> None:
        key, _ = self.current()
        self.stadium.paint(p, target, sp.BY_KEY[key].sport if key else sp.FOOTBALL)

    def content_key(self, now: datetime):
        return now.replace(second=0, microsecond=0), self.page

    def paint_content(self, p: QPainter, now: datetime) -> None:
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        key, data = self.current()
        self._fav = {self.favourites[key]} if key in self.favourites else set()
        # shade the top, so the title reads clearly against the floodlights
        p.fillRect(QRectF(-400, -400, W + 800, 555), vgrad(0, 155, (0, rgb(2, 4, 10, 225)), (0.68, rgb(2, 4, 10, 215)), (1, rgb(2, 4, 10, 0))))
        self._paint_header(p, now, key, data)
        if key is None:
            self._message(p, "Choose the competitions to follow in Settings (S)")
            return
        if data is None:
            self._message(p, "Fetching the scores…")
            return
        if data.sport == sp.CRICKET:
            self._paint_cricket(p, data, now)
        else:
            self._paint_matches(p, data, now, QRectF(MATCHES) if data.tables else QRectF(MATCHES.left(), MATCHES.top(), TABLE.right() - MATCHES.left(), MATCHES.height()))
            if data.tables:
                self._paint_tables(p, data)

    def _message(self, p: QPainter, text: str) -> None:
        p.setFont(font(34))
        p.setPen(DIM)
        p.drawText(QRectF(0, 440, W, 80), Qt.AlignCenter, text)

    def _card(self, p: QPainter, rect: QRectF) -> None:
        p.setPen(QPen(rgb(255, 255, 255, 40), 1))
        p.setBrush(vgrad(rect.top(), rect.bottom(), rgb(6, 14, 10, 200), rgb(4, 10, 8, 215)))
        p.drawRoundedRect(rect, 18, 18)

    def _paint_header(self, p: QPainter, now: datetime, key: Optional[str], data: Optional[sp.CompetitionData]) -> None:
        comp = sp.BY_KEY.get(key) if key else None
        name = (data.name if data else "") or (comp.name if comp else "Sport")
        f, name = fit_title(name, font(46, QFont.DemiBold))
        p.setFont(f)
        p.setPen(WHITE)
        p.drawText(QRectF(54, 22, TITLE_WIDTH, 60), Qt.AlignLeft | Qt.AlignVCenter, name)
        bits = [sp.SPORT_NAMES.get(comp.sport, "") if comp else ""]
        if data is not None:
            updated = datetime.fromtimestamp(data.fetched_at)
            bits.append(f"updated {updated:%H:%M}" if self.clock_24h else f"updated {updated:%I:%M %p}".replace(" 0", " "))
        if data is not None and data.live:
            bits.append(f"{len(data.live)} live")
        if data is not None and self._fav:
            name = next((t.name for m in data.matches for t in (m.home, m.away) if t.is_one_of(self._fav)), "") or next(
                (team.name for table in data.tables for _, team, _ in table.rows if team.is_one_of(self._fav)), "")
            if name:
                bits.append(f"★ {name}")
        if self.offline:
            bits.append("offline — showing the last scores")
        p.setFont(font(21))
        p.setPen(DIM)
        p.drawText(QRectF(56, 84, 1000, 30), Qt.AlignLeft | Qt.AlignVCenter, " · ".join(b for b in bits if b))
        clock = now.strftime("%H:%M") if self.clock_24h else now.strftime("%I:%M %p").lstrip("0")
        p.setFont(font(46, QFont.Light))
        p.setPen(WHITE)
        p.drawText(QRectF(1150, 22, 396, 60), Qt.AlignRight | Qt.AlignVCenter, clock)
        # page dots
        n = len(self.keys)
        if n > 1:
            r, gap = 6.0, 20.0
            x = 1546 - (n - 1) * gap
            p.setPen(Qt.NoPen)
            for i in range(n):
                p.setBrush(WHITE if i == self.page % n else rgb(255, 255, 255, 80))
                p.drawEllipse(QPointF(x + i * gap, 100), r if i == self.page % n else r * 0.75, r if i == self.page % n else r * 0.75)

    # --- football, rugby, baseball

    def _paint_matches(self, p: QPainter, data: sp.CompetitionData, now: datetime, area: QRectF) -> None:
        self._card(p, area)
        inner = area.adjusted(24, 18, -24, -18)
        live, results, fixtures = data.live, data.results, data.fixtures
        # room: everything live, then results, keeping some room for fixtures
        total = int(inner.height() // ROW)
        want_fixtures = min(len(fixtures), max(3, total // 3)) if fixtures else 0
        lines: list = []
        if live:
            lines.append(("section", "Live now"))
            lines += [("match", m) for m in live]
        budget = total - len(lines) - (want_fixtures + 2 if fixtures else 0)
        if results and budget > 2:
            lines.append(("section", "Latest results"))
            lines += self._by_day(results[:max(0, budget - 1)], now)
        if fixtures:
            room = total - len(lines) - 1
            lines.append(("section", "Coming up"))
            lines += self._by_day(fixtures, now)[:max(0, room)]
        if not (live or results or fixtures):
            p.setFont(font(26))
            p.setPen(DIM)
            p.drawText(inner, Qt.AlignCenter, "No recent or upcoming matches")
            return
        y = inner.top()
        for kind, item in lines:
            if kind == "section":
                h = DAY_ROW + 6
                if y + h > inner.bottom():
                    break
                p.setFont(font(22, QFont.Bold))
                p.setPen(GOLD)
                p.drawText(QRectF(inner.left(), y + 4, inner.width(), DAY_ROW), Qt.AlignLeft | Qt.AlignVCenter, item.upper())
            elif kind == "day":
                h = DAY_ROW
                if y + h + ROW > inner.bottom():  # (a day's heading with no room for its matches)
                    break
                p.setFont(font(18, QFont.DemiBold))
                p.setPen(FAINT)
                p.drawText(QRectF(inner.left(), y, inner.width(), DAY_ROW), Qt.AlignLeft | Qt.AlignVCenter, item)
            else:
                h = ROW
                if y + h > inner.bottom():
                    break
                self._match_row(p, item, QRectF(inner.left(), y, inner.width(), ROW))
            y += h

    def _by_day(self, matches: list, now: datetime) -> list:
        """Matches under a heading for each day, the favourite's first, so it's
        never the one left off when a day has more than fits."""
        days = {}
        for m in matches:
            days.setdefault(_day_label(m.local_start(), now), []).append(m)
        matches = [m for group in days.values()
                   for m in sorted(group, key=lambda m: not (m.home.is_one_of(self._fav) or m.away.is_one_of(self._fav)))]
        out, day = [], None
        for m in matches:
            label = _day_label(m.local_start(), now)
            if label != day:
                out.append(("day", label))
                day = label
            out.append(("match", m))
        return out

    def _chip(self, p: QPainter, rect: QRectF, colour: QColor) -> None:
        p.setPen(QPen(rgb(255, 255, 255, 90), 1))
        p.setBrush(colour)
        p.drawRoundedRect(rect, 3, 3)

    def _highlight(self, p: QPainter, rect: QRectF) -> None:
        """The gold band behind a favourite team's row."""
        p.setPen(Qt.NoPen)
        p.setBrush(alpha(GOLD, 46))
        p.drawRoundedRect(rect, 8, 8)
        p.setBrush(GOLD)
        p.drawRoundedRect(QRectF(rect.left(), rect.top() + 3, 5, rect.height() - 6), 2.5, 2.5)

    def _match_row(self, p: QPainter, m: sp.Match, rect: QRectF) -> None:
        if m.home.is_one_of(self._fav) or m.away.is_one_of(self._fav):
            self._highlight(p, rect.adjusted(-14, 1, 14, -1))
        mid = rect.center().x()
        box = QRectF(mid - 62, rect.top() + 4, 124, rect.height() - 8)
        name_w = box.left() - rect.left() - 34
        home_won = m.state == sp.DONE and m.home.winner
        away_won = m.state == sp.DONE and m.away.winner
        # home: name right-aligned against the score, with a colour chip
        for team, won, side in ((m.home, home_won, -1), (m.away, away_won, 1)):
            fav = team.is_one_of(self._fav)
            f = font(24, QFont.DemiBold if won or fav else QFont.Normal)
            p.setFont(f)
            p.setPen(GOLD if fav else WHITE if (won or m.state != sp.DONE or not (home_won or away_won)) else DIM)
            name = QFontMetricsF(f).elidedText(team.name, Qt.ElideRight, name_w)
            if side < 0:
                p.drawText(QRectF(rect.left(), rect.top(), name_w, rect.height()), Qt.AlignRight | Qt.AlignVCenter, name)
                self._chip(p, QRectF(box.left() - 22, rect.center().y() - 8, 12, 16), self._team_colour(team))
            else:
                p.drawText(QRectF(box.right() + 34, rect.top(), name_w, rect.height()), Qt.AlignLeft | Qt.AlignVCenter, name)
                self._chip(p, QRectF(box.right() + 10, rect.center().y() - 8, 12, 16), self._team_colour(team))
        # the score (or the start time)
        p.setPen(Qt.NoPen)
        if m.state == sp.LIVE:
            p.setBrush(alpha(LIVE_RED, 210))
        elif m.state == sp.DONE:
            p.setBrush(rgb(255, 255, 255, 34))
        else:
            p.setBrush(rgb(255, 255, 255, 14))
        p.drawRoundedRect(box, 8, 8)
        p.setPen(WHITE)
        if m.state == sp.PRE:
            start = m.local_start()
            text = start.strftime("%H:%M") if self.clock_24h else start.strftime("%I:%M%p").lstrip("0").lower()
            p.setFont(font(22))
        else:
            text = f"{m.home.score or 0} – {m.away.score or 0}"
            p.setFont(font(25, QFont.Bold))
        p.drawText(box, Qt.AlignCenter, text)
        if m.state == sp.LIVE and m.detail:
            p.setFont(font(15, QFont.DemiBold))
            p.setPen(rgb(255, 170, 160))
            p.drawText(QRectF(rect.right() - 90, rect.top(), 90, rect.height()), Qt.AlignRight | Qt.AlignVCenter, m.detail)

    def _paint_tables(self, p: QPainter, data: sp.CompetitionData) -> None:
        self._card(p, TABLE)
        inner = TABLE.adjusted(22, 16, -22, -14)
        tables = data.tables[:2]
        row = 29.0
        head = 30.0
        total_rows = int((inner.height() - len(tables) * (head * 2 + 6)) // row)
        per_table = max(3, total_rows // len(tables))
        y = inner.top()
        for t in tables:
            cols = t.columns
            col_w = 56.0 if len(cols) <= 4 else 50.0
            team_w = inner.width() - 40 - col_w * len(cols)
            p.setFont(font(19, QFont.Bold))
            p.setPen(GOLD)
            p.drawText(QRectF(inner.left(), y, inner.width(), head), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetricsF(p.font()).elidedText(t.name.upper(), Qt.ElideRight, inner.width()))
            y += head
            p.setFont(font(16, QFont.DemiBold))
            p.setPen(FAINT)
            for i, c in enumerate(cols):
                p.drawText(QRectF(inner.left() + 40 + team_w + i * col_w, y, col_w, head), Qt.AlignRight | Qt.AlignVCenter, c)
            y += head
            for pos, team, values in t.rows[:per_table]:
                if y + row > inner.bottom() + 2:
                    break
                fav = team.is_one_of(self._fav)
                if fav:
                    self._highlight(p, QRectF(inner.left() - 12, y, inner.width() + 24, row))
                elif pos % 2 == 0:
                    p.setPen(Qt.NoPen)
                    p.setBrush(rgb(255, 255, 255, 12))
                    p.drawRect(QRectF(inner.left() - 8, y, inner.width() + 16, row))
                p.setFont(font(18))
                p.setPen(DIM)
                p.drawText(QRectF(inner.left(), y, 28, row), Qt.AlignRight | Qt.AlignVCenter, str(pos))
                self._chip(p, QRectF(inner.left() + 36, y + row / 2 - 7, 9, 14), self._team_colour(team))
                p.setPen(GOLD if fav else WHITE)
                f = font(19, QFont.Bold if fav else QFont.Normal)
                p.setFont(f)
                p.drawText(QRectF(inner.left() + 52, y, team_w - 16, row), Qt.AlignLeft | Qt.AlignVCenter,
                           QFontMetricsF(f).elidedText(team.name, Qt.ElideRight, team_w - 16))
                for i, v in enumerate(values):
                    last = i == len(values) - 1
                    p.setFont(font(19, QFont.Bold if last else QFont.Normal))
                    p.setPen(GOLD if fav else WHITE if last else DIM)
                    p.drawText(QRectF(inner.left() + 40 + team_w + i * col_w, y, col_w, row), Qt.AlignRight | Qt.AlignVCenter, v)
                y += row
            y += 6

    # --- cricket

    def _paint_cricket(self, p: QPainter, data: sp.CompetitionData, now: datetime) -> None:
        matches = data.live + data.results + data.fixtures
        matches.sort(key=lambda m: not (m.home.is_one_of(self._fav) or m.away.is_one_of(self._fav)))  # the favourite's first
        area = QRectF(MATCHES.left(), MATCHES.top(), TABLE.right() - MATCHES.left(), MATCHES.height())
        if not matches:
            self._card(p, area)
            p.setFont(font(26))
            p.setPen(DIM)
            p.drawText(area, Qt.AlignCenter, "No cricket on just now")
            return
        cols, rows, gap = 2, 4, 18.0
        w = (area.width() - gap) / cols
        h = (area.height() - gap * (rows - 1)) / rows
        for i, m in enumerate(matches[:cols * rows]):
            rect = QRectF(area.left() + (i % cols) * (w + gap), area.top() + (i // cols) * (h + gap), w, h)
            self._cricket_card(p, m, rect, now)

    def _cricket_card(self, p: QPainter, m: sp.Match, rect: QRectF, now: datetime) -> None:
        self._card(p, rect)
        if m.home.is_one_of(self._fav) or m.away.is_one_of(self._fav):
            p.setPen(QPen(GOLD, 3))
            p.setBrush(alpha(GOLD, 26))
            p.drawRoundedRect(rect.adjusted(1.5, 1.5, -1.5, -1.5), 17, 17)
        inner = rect.adjusted(20, 12, -20, -10)
        # the series and the kind of match
        badge = m.kind or ""
        p.setFont(font(15, QFont.Bold))
        bw = QFontMetricsF(p.font()).horizontalAdvance(badge) + 18 if badge else 0
        if badge:
            p.setPen(Qt.NoPen)
            p.setBrush(LIVE_RED if m.state == sp.LIVE else rgb(255, 255, 255, 40))
            br = QRectF(inner.right() - bw, inner.top() + 2, bw, 22)
            p.drawRoundedRect(br, 11, 11)
            p.setPen(WHITE)
            p.drawText(br, Qt.AlignCenter, badge)
        p.setFont(font(16))
        p.setPen(FAINT)
        p.drawText(QRectF(inner.left(), inner.top(), inner.width() - bw - 10, 26), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetricsF(p.font()).elidedText(m.competition, Qt.ElideRight, inner.width() - bw - 10))
        # the two sides and their scores
        y = inner.top() + 30
        for team in (m.home, m.away):
            self._chip(p, QRectF(inner.left(), y + 9, 10, 16), self._team_colour(team))
            fav = team.is_one_of(self._fav)
            f = font(23, QFont.DemiBold if team.winner or fav else QFont.Normal)
            p.setFont(f)
            p.setPen(GOLD if fav else WHITE)
            p.drawText(QRectF(inner.left() + 20, y, inner.width() * 0.45, 34), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetricsF(f).elidedText(team.name, Qt.ElideRight, inner.width() * 0.45))
            sf = font(22, QFont.Bold)
            p.setFont(sf)
            score = team.score or ("" if m.state == sp.PRE else "–")
            p.drawText(QRectF(inner.left() + inner.width() * 0.45, y, inner.width() * 0.55, 34), Qt.AlignRight | Qt.AlignVCenter,
                       QFontMetricsF(sf).elidedText(score, Qt.ElideLeft, inner.width() * 0.55))
            y += 34
        # how it stands
        if m.state == sp.PRE:
            start = m.local_start()
            when = start.strftime("%H:%M") if self.clock_24h else start.strftime("%I:%M %p").lstrip("0")
            line, colour = f"Starts {_day_label(start, now).lower() if _day_label(start, now) in ('Today', 'Tomorrow') else _day_label(start, now)} at {when}", DIM
        else:
            line = m.summary or m.detail
            colour = rgb(255, 170, 160) if m.state == sp.LIVE else GOLD
        p.setFont(font(18, QFont.DemiBold))
        p.setPen(colour)
        p.drawText(QRectF(inner.left(), inner.bottom() - 28, inner.width(), 28), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetricsF(p.font()).elidedText(line, Qt.ElideRight, inner.width()))
