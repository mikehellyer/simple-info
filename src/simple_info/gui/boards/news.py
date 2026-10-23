"""The news board: a page for each news feed you follow — the lead story
with its picture, and the next headlines beside it — and a ticker along
the bottom running through the latest headlines from all of them, over a
newsroom's slowly turning globe."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen

from simple_info.core import news as nw
from simple_info.core.settings import Settings
from simple_info.gui.boards.base import TITLE_WIDTH, Board, fit_title
from simple_info.gui.boards.newsroom import Newsroom
from simple_info.gui.paint import W, alpha, rgb, vgrad

WHITE = rgb(255, 255, 255)
DIM = rgb(255, 255, 255, 175)
FAINT = rgb(255, 255, 255, 115)
RED = rgb(206, 22, 40)

LEAD = QRectF(50, 150, 820, 668)
LIST = QRectF(894, 150, 656, 668)
TICKER = QRectF(50, 836, 1500, 48)
LIST_ITEMS = 6
TICKER_SPEED = 110.0  # virtual pixels a second


def font(px: float, weight=QFont.Normal) -> QFont:
    f = QFont()
    f.setPixelSize(max(1, int(px)))
    f.setWeight(weight)
    return f


def wrap(text: str, f: QFont, width: float, max_lines: int) -> list[str]:
    """Words wrapped into at most max_lines, the last one cut short with … if need be."""
    metrics = QFontMetricsF(f)
    lines, line = [], ""
    words = text.split()
    for i, word in enumerate(words):
        trial = f"{line} {word}".strip()
        if metrics.horizontalAdvance(trial) <= width or not line:
            line = trial
            continue
        lines.append(line)
        line = word
        if len(lines) == max_lines - 1:
            line = " ".join(words[i:])
            break
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if lines:
        lines[-1] = metrics.elidedText(lines[-1], Qt.ElideRight, width)
    return lines


def draw_lines(p: QPainter, lines: list[str], x: float, y: float, width: float, line_height: float) -> float:
    for i, line in enumerate(lines):
        p.drawText(QRectF(x, y + i * line_height, width, line_height), Qt.AlignLeft | Qt.AlignVCenter, line)
    return y + len(lines) * line_height


class NewsBoard(Board):
    key = "news"
    title = "News"
    accent = rgb(230, 60, 70)
    refresh_seconds = 10 * 60
    retry_seconds = 2 * 60
    has_live = True

    def __init__(self):
        super().__init__()
        self.room = Newsroom()
        self.keys: list[str] = list(nw.DEFAULT_KEYS)
        self.stories: dict[str, list[nw.Story]] = {}
        self.page_seconds = 20.0
        self.clock_24h = True
        self.offline = False
        self.updated: Optional[datetime] = None
        self._pictures: dict[str, QImage] = {}  # url -> picture, decoded once
        self._ticker_text = ""
        self._ticker_width = 0.0
        self._ticker_start = 0.0
        self._ticker_font = font(24, QFont.DemiBold)

    # --- settings and data

    def configure(self, settings: Settings) -> None:
        self.clock_24h = settings.clock_24h
        self.page_seconds = float(settings.page_seconds)
        keys = [k for k in settings.news_feeds.split(",") if k in nw.BY_KEY]
        if keys != self.keys:
            self.keys = keys
            self.stories = {k: v for k, v in self.stories.items() if k in keys}
            self.set_page(self.page)
            self.fetch_now()
        self.dirty = True

    def page_count(self) -> int:
        return max(1, len(self.keys))

    def page_names(self) -> list[str]:
        return [nw.BY_KEY[k].name.replace("BBC News – ", "BBC ") for k in self.keys]

    def fetch_job(self):
        if not self.keys:
            return None
        keys, have = list(self.keys), set(self._pictures)

        def job():
            stories, pictures = {}, {}
            for key in keys:
                got = nw.fetch_feed(key)
                if got is None:
                    continue
                stories[key] = got
                # pictures for what's shown: the lead's bigger, the rest small
                for i, story in enumerate(got[:LIST_ITEMS + 1]):
                    if not story.image:
                        continue
                    url = nw.sized(story.image, 480 if i == 0 else 240)
                    if url in have or url in pictures:
                        continue
                    data = nw.fetch_image(url)
                    if data:
                        pictures[url] = data
            return stories, pictures

        return job

    def on_fetched(self, result) -> bool:
        stories, pictures = result or ({}, {})
        self.stories.update(stories)
        for url, data in pictures.items():
            img = QImage.fromData(data)
            if not img.isNull():
                self._pictures[url] = img
        # forget pictures no longer wanted, so memory doesn't creep up over the days
        wanted = {nw.sized(s.image, 480 if i == 0 else 240) for items in self.stories.values()
                  for i, s in enumerate(items[:LIST_ITEMS + 1]) if s.image}
        self._pictures = {u: img for u, img in self._pictures.items() if u in wanted}
        ok = bool(stories) and len(stories) == len(self.keys)
        if stories:
            self.updated = datetime.now()
        self.offline = not ok and bool(self.stories)
        return ok

    def latest(self, count: int = 12) -> list[nw.Story]:
        """The newest headlines across all the feeds, without repeats."""
        seen, out = set(), []
        everything = [s for items in self.stories.values() for s in items[:10]]
        everything.sort(key=lambda s: s.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        for s in everything:
            if s.title not in seen:
                seen.add(s.title)
                out.append(s)
            if len(out) == count:
                break
        return out

    # --- drawing

    def current(self) -> tuple[Optional[str], list[nw.Story]]:
        if not self.keys:
            return None, []
        key = self.keys[self.page % len(self.keys)]
        return key, self.stories.get(key, [])

    def step(self, dt: float) -> None:
        self.room.step(dt)

    def paint_background(self, p: QPainter, target: QRectF) -> None:
        self.room.paint(p, target)

    def content_key(self, now: datetime):
        return now.replace(second=0, microsecond=0), self.page

    def paint_content(self, p: QPainter, now: datetime) -> None:
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        key, stories = self.current()
        self._paint_header(p, now, key)
        if key is None:
            self._message(p, "Choose the news to follow in Settings (S)")
            return
        if not stories:
            self._message(p, "Fetching the news…" if not self.offline else "Can't reach the news — check your connection (retrying)")
            return
        utc_now = datetime.now(timezone.utc)
        self._paint_lead(p, stories[0], utc_now)
        self._paint_list(p, stories[1:LIST_ITEMS + 1], utc_now)
        self._paint_ticker_frame(p)

    def _message(self, p: QPainter, text: str) -> None:
        p.setFont(font(34))
        p.setPen(DIM)
        p.drawText(QRectF(0, 440, W, 80), Qt.AlignCenter, text)

    def _paint_header(self, p: QPainter, now: datetime, key: Optional[str]) -> None:
        feed = nw.BY_KEY.get(key) if key else None
        name = feed.name if feed else "News"
        source, _, section = name.partition(" – ")
        f, title = fit_title(section or source, font(46, QFont.DemiBold))
        p.setFont(f)
        p.setPen(WHITE)
        p.drawText(QRectF(54, 22, TITLE_WIDTH, 60), Qt.AlignLeft | Qt.AlignVCenter, title)
        bits = [source] if section else []
        if self.updated is not None:
            bits.append(f"updated {self.updated:%H:%M}" if self.clock_24h else f"updated {self.updated:%I:%M %p}".replace(" 0", " "))
        if self.offline:
            bits.append("offline — showing the last headlines")
        p.setFont(font(21))
        p.setPen(DIM)
        p.drawText(QRectF(56, 84, 1080, 30), Qt.AlignLeft | Qt.AlignVCenter, " · ".join(bits))
        clock = now.strftime("%H:%M") if self.clock_24h else now.strftime("%I:%M %p").lstrip("0")
        p.setFont(font(46, QFont.Light))
        p.setPen(WHITE)
        p.drawText(QRectF(1150, 22, 396, 60), Qt.AlignRight | Qt.AlignVCenter, clock)
        n = len(self.keys)
        if n > 1:
            r, gap = 6.0, 20.0
            x = 1546 - (n - 1) * gap
            p.setPen(Qt.NoPen)
            for i in range(n):
                current = i == self.page % n
                p.setBrush(WHITE if current else rgb(255, 255, 255, 80))
                p.drawEllipse(QPointF(x + i * gap, 100), r if current else r * 0.75, r if current else r * 0.75)

    def _card(self, p: QPainter, rect: QRectF) -> None:
        p.setPen(QPen(rgb(255, 255, 255, 40), 1))
        p.setBrush(vgrad(rect.top(), rect.bottom(), rgb(8, 12, 30, 205), rgb(6, 8, 20, 220)))
        p.drawRoundedRect(rect, 18, 18)

    def _picture(self, p: QPainter, story: nw.Story, rect: QRectF, width: int, radius: float) -> None:
        """The story's picture cropped to fill rect (or a plain panel if there's none)."""
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.save()
        p.setClipPath(path)
        img = self._pictures.get(nw.sized(story.image, width)) if story.image else None
        if img is None:
            p.fillRect(rect, vgrad(rect.top(), rect.bottom(), rgb(40, 50, 90), rgb(20, 24, 50)))
            p.setFont(font(rect.height() * 0.22, QFont.Bold))
            p.setPen(rgb(255, 255, 255, 60))
            p.drawText(rect, Qt.AlignCenter, story.source or "News")
        else:
            scale = max(rect.width() / img.width(), rect.height() / img.height())
            w, h = img.width() * scale, img.height() * scale
            p.drawImage(QRectF(rect.center().x() - w / 2, rect.center().y() - h / 2, w, h), img)
        p.restore()

    def _paint_lead(self, p: QPainter, story: nw.Story, now: datetime) -> None:
        self._card(p, LEAD)
        pic = QRectF(LEAD.left() + 18, LEAD.top() + 18, LEAD.width() - 36, (LEAD.width() - 36) * 9 / 16)
        self._picture(p, story, pic, 480, 12)
        x, width = LEAD.left() + 28, LEAD.width() - 56
        y = pic.bottom() + 16
        f = font(33, QFont.Bold)
        p.setFont(f)
        p.setPen(WHITE)
        y = draw_lines(p, wrap(story.title, f, width, 2), x, y, width, 42)
        when = nw.ago(story.published, now)
        room = int((LEAD.bottom() - 46 - y) // 30)
        if story.summary and room > 0:
            sf = font(22)
            p.setFont(sf)
            p.setPen(DIM)
            draw_lines(p, wrap(story.summary, sf, width, min(3, room)), x, y + 6, width, 30)
        p.setFont(font(18, QFont.DemiBold))
        p.setPen(rgb(255, 120, 120))
        p.drawText(QRectF(x, LEAD.bottom() - 42, width, 28), Qt.AlignLeft | Qt.AlignVCenter, when)

    def _paint_list(self, p: QPainter, stories: list[nw.Story], now: datetime) -> None:
        self._card(p, LIST)
        if not stories:
            return
        inner = LIST.adjusted(16, 14, -16, -14)
        h = inner.height() / LIST_ITEMS
        for i, story in enumerate(stories):
            y = inner.top() + i * h
            if i:
                p.setPen(QPen(rgb(255, 255, 255, 26), 1))
                p.drawLine(QPointF(inner.left() + 4, y), QPointF(inner.right() - 4, y))
            pic = QRectF(inner.left(), y + 9, (h - 18) * 16 / 9, h - 18)
            self._picture(p, story, pic, 240, 8)
            x = pic.right() + 16
            width = inner.right() - x
            f = font(21, QFont.DemiBold)
            p.setFont(f)
            p.setPen(WHITE)
            lines = wrap(story.title, f, width, 2)
            top = y + (h - (len(lines) * 27 + 22)) / 2
            after = draw_lines(p, lines, x, top, width, 27)
            p.setFont(font(16, QFont.DemiBold))
            p.setPen(rgb(255, 120, 120))
            p.drawText(QRectF(x, after, width, 22), Qt.AlignLeft | Qt.AlignVCenter, nw.ago(story.published, now))

    def _paint_ticker_frame(self, p: QPainter) -> None:
        p.setPen(Qt.NoPen)
        p.setBrush(rgb(8, 10, 24, 225))
        p.drawRoundedRect(TICKER, 10, 10)
        label = QRectF(TICKER.left(), TICKER.top(), 132, TICKER.height())
        path = QPainterPath()
        path.addRoundedRect(label, 10, 10)
        p.fillPath(path, RED)
        p.setFont(font(21, QFont.Bold))
        p.setPen(WHITE)
        p.drawText(label, Qt.AlignCenter, "LATEST")

    # --- the ticker, moving every frame

    def paint_live(self, p: QPainter, t: float) -> None:
        key, stories = self.current()
        if not stories:
            return
        text = "      ●      ".join(s.title for s in self.latest())
        if text != self._ticker_text:
            self._ticker_text = text
            self._ticker_width = QFontMetricsF(self._ticker_font).horizontalAdvance(text)
            self._ticker_start = t
        strip = QRectF(TICKER.left() + 146, TICKER.top(), TICKER.width() - 156, TICKER.height())
        travel = self._ticker_width + strip.width() + 160
        x = strip.right() - ((t - self._ticker_start) * TICKER_SPEED) % travel
        p.save()
        p.setClipRect(strip)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self._ticker_font)
        p.setPen(WHITE)
        p.drawText(QRectF(x, strip.top(), self._ticker_width + 10, strip.height()), Qt.AlignLeft | Qt.AlignVCenter, self._ticker_text)
        p.restore()
