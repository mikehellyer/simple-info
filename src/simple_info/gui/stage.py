"""The window's one big canvas: shows the current board, crossfades from
one board to the next, and draws the board bar and messages on top."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontMetricsF, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from simple_info.gui.boards.base import Board
from simple_info.gui.paint import H, W, alpha, rgb

FRAME_MS = 33
LIGHT_FRAME_MS = 50  # 20 fps in light graphics mode
LIGHT_SCALE = 0.5  # light mode draws the moving background at this fraction of the window's size
FADE_SECONDS = 1.0
BAR_SECONDS = 4.0  # how long the board bar stays up after a switch or a mouse move
CURSOR_HIDE_SECONDS = 3.0

HINT = "◀ ▶  switch boards     ▲ ▼  turn pages     H  pause     F  full screen     S  settings     Right-click  menu"


def fit(rect: QRectF) -> tuple[float, float, float]:
    """Scale and offset that fit the 1600×900 canvas inside rect, centred."""
    s = min(rect.width() / W, rect.height() / H)
    return s, rect.x() + (rect.width() - W * s) / 2, rect.y() + (rect.height() - H * s) / 2


class Stage(QWidget):
    board_changed = Signal(str)
    page_changed = Signal(int)
    pause_clicked = Signal()  # the paused badge was clicked

    def __init__(self, boards: list[Board], parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setMinimumSize(480, 270)

        self.boards = boards
        self.index = 0
        self._fade_from: Optional[QPixmap] = None
        self._fade_left = 0.0
        self._on_board = 0.0  # seconds on the current board
        self._on_page = 0.0  # seconds on the current page of a board with pages
        self.paused = False  # held: no turning pages or moving on by itself
        self._qr: Optional[tuple[list, str]] = None  # the phone remote's QR code and address, while shown
        self._qr_left = 0.0
        self.cycle = False
        self.cycle_seconds = 30.0

        self._content: Optional[QImage] = None
        self._content_key = None
        self._light = False
        self._buffer: Optional[QImage] = None

        self._toast = ""
        self._toast_left = 0.0
        self._bar_left = BAR_SECONDS + 2
        self._hint_left = BAR_SECONDS + 2
        self._idle = 0.0

        self._last = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(FRAME_MS)

    # --- state

    @property
    def board(self) -> Board:
        return self.boards[self.index]

    def show_board(self, index: int, fade: bool = True) -> None:
        index %= len(self.boards)
        self._on_board = 0.0
        self._on_page = 0.0
        self._bar_left = BAR_SECONDS
        if index == self.index:
            self.update()
            return
        if fade and self.isVisible() and self.width() > 0:
            self._fade_from = self.grab()
            self._fade_left = FADE_SECONDS
        self.index = index
        self.board.set_page(0)
        self._content_key = None
        self.board_changed.emit(self.board.key)
        self.update()

    def show_key(self, key: str, fade: bool = True) -> bool:
        for i, b in enumerate(self.boards):
            if b.key == key:
                self.show_board(i, fade)
                return True
        return False

    def turn_page(self, step: int = 1, fade: bool = True) -> bool:
        """Show the current board's next (or previous) page, if it has more than one."""
        board = self.board
        if board.page_count() <= 1:
            return False
        if fade and self.isVisible() and self.width() > 0:
            self._fade_from = self.grab()
            self._fade_left = FADE_SECONDS
        board.set_page(board.page + step)
        self._on_page = 0.0
        self.page_changed.emit(board.page)
        self.update()
        return True

    def show_qr(self, matrix: list, url: str, seconds: float = 45.0) -> None:
        """Show the phone remote's QR code (shown again, it hides)."""
        if self._qr_left > 0:
            self._qr_left = 0.0
        else:
            self._qr, self._qr_left = (matrix, url), seconds
        self.update()

    def set_paused(self, paused: bool) -> None:
        """Hold what's on screen: no turning pages, no moving on to the next
        board, and boards that take turns (trains: departures and arrivals)
        stay on what they're showing."""
        self.paused = paused
        self._on_page = 0.0
        self._on_board = 0.0
        for board in self.boards:
            board.paused = paused
            board.dirty = True
        self.update()

    def next_board(self) -> None:
        self.show_board(self.index + 1)

    def previous_board(self) -> None:
        self.show_board(self.index - 1)

    def set_light_graphics(self, light: bool) -> None:
        """Light graphics: the moving background is drawn smaller and scaled
        up, at a lower frame rate, for slower machines such as a Raspberry
        Pi. The words are still drawn at full size, so they stay sharp."""
        self._light = light
        self._buffer = None
        self._timer.setInterval(LIGHT_FRAME_MS if light else FRAME_MS)

    def toast(self, text: str, seconds: float = 3.0) -> None:
        self._toast, self._toast_left = text, seconds
        self.update()

    def shutdown(self) -> None:
        self._timer.stop()

    # --- animation

    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        self.board.step(dt)
        self._on_board += dt
        pages = self.board.page_count()
        if self.paused:
            pass  # held: stay on this board and this page
        elif pages > 1:
            # a board with pages takes turns through them; moving on by
            # itself, it shows them all first
            self._on_page += dt
            if self._on_page >= self.board.page_seconds:
                if self.cycle and len(self.boards) > 1 and self.board.page == pages - 1:
                    self.next_board()
                else:
                    self.turn_page(1)
        elif self.cycle and len(self.boards) > 1 and self._on_board >= self.cycle_seconds:
            self.next_board()
        if self._fade_left > 0:
            self._fade_left -= dt
            if self._fade_left <= 0:
                self._fade_from = None
        self._toast_left = max(0.0, self._toast_left - dt)
        self._qr_left = max(0.0, self._qr_left - dt)
        self._bar_left = max(0.0, self._bar_left - dt)
        self._hint_left = max(0.0, self._hint_left - dt)
        self._idle += dt
        if self._idle > CURSOR_HIDE_SECONDS and self.window().isFullScreen():
            self.setCursor(Qt.BlankCursor)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        self._idle = 0.0
        if self.cursor().shape() == Qt.BlankCursor:
            self.unsetCursor()
        self._bar_left = max(self._bar_left, 2.5)
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        w = self.window()
        w.showNormal() if w.isFullScreen() else w.showFullScreen()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            if self.paused and self._pause_badge(QRectF(self.rect())).contains(event.position()):
                self.pause_clicked.emit()
                return
            hit = self._bar_hit(event.position().x(), event.position().y())
            if hit is not None:
                self.show_board(hit)
                return
        super().mousePressEvent(event)

    # --- painting

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = QRectF(self.rect())
        board = self.board

        if self._light:
            size = (max(1, int(rect.width() * LIGHT_SCALE)), max(1, int(rect.height() * LIGHT_SCALE)))
            if self._buffer is None or (self._buffer.width(), self._buffer.height()) != size:
                self._buffer = QImage(size[0], size[1], QImage.Format_RGB32)
            bp = QPainter(self._buffer)
            board.paint_background(bp, QRectF(0, 0, *size))
            bp.end()
            p.drawImage(rect, self._buffer)
        else:
            board.paint_background(p, rect)

        p.drawImage(rect.topLeft(), self._content_image(board, rect))
        if board.has_live:
            s, x, y = fit(rect)
            p.save()
            p.translate(x, y)
            p.scale(s, s)
            board.paint_live(p, time.monotonic())
            p.restore()

        if self._fade_from is not None and self._fade_left > 0:
            p.setOpacity(max(0.0, self._fade_left / FADE_SECONDS) ** 1.5)
            p.drawPixmap(self.rect(), self._fade_from)
            p.setOpacity(1.0)
        self._paint_bar(p, rect)
        if self.paused:
            self._paint_paused(p, rect)
        self._paint_messages(p, rect)
        p.end()

    def _content_image(self, board: Board, rect: QRectF) -> QImage:
        """The board's words and figures, redrawn only when they change."""
        now = datetime.now()
        dpr = self.devicePixelRatioF()
        size = (max(1, int(rect.width() * dpr)), max(1, int(rect.height() * dpr)))
        key = (board.key, board.content_key(now), size)
        if self._content is None or board.dirty or key != self._content_key:
            if self._content is None or (self._content.width(), self._content.height()) != size:
                self._content = QImage(size[0], size[1], QImage.Format_ARGB32_Premultiplied)
                self._content.setDevicePixelRatio(dpr)
            self._content.fill(Qt.transparent)
            cp = QPainter(self._content)
            s, x, y = fit(rect)
            cp.translate(x, y)
            cp.scale(s, s)
            board.paint_content(cp, now)
            cp.end()
            board.dirty = False
            self._content_key = key
        return self._content

    def _bar_layout(self, rect: QRectF) -> tuple[list[QRectF], QFont, float]:
        """Where each board's pill sits in the board bar, in window pixels."""
        s, x0, y0 = fit(rect)
        f = QFont()
        f.setPixelSize(max(11, int(20 * s)))
        f.setWeight(QFont.DemiBold)
        fm = QFontMetricsF(f)
        h = 38 * s
        gap = 10 * s
        widths = [fm.horizontalAdvance(f"{i + 1}  {b.title}") + 36 * s for i, b in enumerate(self.boards)]
        total = sum(widths) + gap * (len(widths) - 1)
        x = rect.center().x() - total / 2
        y = rect.bottom() - h - 10 * s
        pills = []
        for w in widths:
            pills.append(QRectF(x, y, w, h))
            x += w + gap
        return pills, f, s

    def _bar_hit(self, x: float, y: float) -> Optional[int]:
        if self._bar_left <= 0:
            return None
        pills, _, _ = self._bar_layout(QRectF(self.rect()))
        for i, r in enumerate(pills):
            if r.contains(x, y):
                return i
        return None

    def _paint_bar(self, p: QPainter, rect: QRectF) -> None:
        if self._bar_left <= 0:
            return
        a = min(1.0, self._bar_left)
        pills, f, s = self._bar_layout(rect)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(f)
        for i, (r, b) in enumerate(zip(pills, self.boards)):
            current = i == self.index
            p.setPen(Qt.NoPen)
            p.setBrush(alpha(b.accent, 215 * a) if current else rgb(0, 0, 0, 130 * a))
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
            if current and self.cycle and len(self.boards) > 1:
                k = min(1.0, self._on_board / max(1.0, self.cycle_seconds))
                p.setBrush(rgb(255, 255, 255, 160 * a))
                inner = r.adjusted(r.height() / 2, r.height() - 4 * s, -r.height() / 2, -2 * s)
                p.drawRect(QRectF(inner.left(), inner.top(), inner.width() * k, inner.height()))
            p.setPen(rgb(10, 14, 22, 255 * a) if current else rgb(255, 255, 255, 220 * a))
            p.drawText(r, Qt.AlignCenter, f"{i + 1}  {b.title}")
        p.restore()

    def _pause_badge(self, rect: QRectF) -> QRectF:
        """Where the paused badge sits: top centre, clear of every board's title and clock."""
        s, x, y = fit(rect)
        w, h = 176 * s, 44 * s
        return QRectF(rect.center().x() - w / 2, y + 12 * s, w, h)

    def _paint_paused(self, p: QPainter, rect: QRectF) -> None:
        badge = self._pause_badge(rect)
        s = badge.height() / 44
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(rgb(255, 255, 255, 120), max(1.0, 1.5 * s)))
        p.setBrush(rgb(0, 0, 0, 170))
        p.drawRoundedRect(badge, badge.height() / 2, badge.height() / 2)
        # the pause sign: two bars
        p.setPen(Qt.NoPen)
        p.setBrush(rgb(255, 200, 70))
        bx, by, bh = badge.left() + 20 * s, badge.top() + 12 * s, 20 * s
        p.drawRoundedRect(QRectF(bx, by, 6 * s, bh), 2 * s, 2 * s)
        p.drawRoundedRect(QRectF(bx + 11 * s, by, 6 * s, bh), 2 * s, 2 * s)
        f = QFont()
        f.setPixelSize(max(10, int(21 * s)))
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(rgb(255, 255, 255, 235))
        p.drawText(QRectF(bx + 28 * s, badge.top(), badge.right() - bx - 40 * s, badge.height()), Qt.AlignCenter, "Paused")
        p.restore()

    def _paint_qr(self, p: QPainter, rect: QRectF) -> None:
        matrix, url = self._qr
        size = min(rect.width(), rect.height()) * 0.42
        cell = size / len(matrix)
        card = QRectF(rect.center().x() - size / 2 - 24, rect.center().y() - size / 2 - 56, size + 48, size + 130)
        p.save()
        p.setOpacity(min(1.0, self._qr_left))
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(rgb(12, 16, 32, 235))
        p.drawRoundedRect(card, 20, 20)
        font = QFont()
        font.setPixelSize(max(14, int(size * 0.07)))
        p.setFont(font)
        p.setPen(rgb(220, 230, 255))
        p.drawText(QRectF(card.left(), card.top() + 12, card.width(), 36), Qt.AlignCenter, "Scan to use your phone as a remote")
        code = QRectF(card.left() + 24, card.top() + 56, size, size)
        p.setPen(Qt.NoPen)
        p.setBrush(rgb(255, 255, 255))
        p.drawRoundedRect(code.adjusted(-8, -8, 8, 8), 8, 8)
        p.setBrush(rgb(0, 0, 0))
        for y, row in enumerate(matrix):
            for x, dark in enumerate(row):
                if dark:
                    p.drawRect(QRectF(code.left() + x * cell, code.top() + y * cell, cell + 0.5, cell + 0.5))
        font.setPixelSize(max(12, int(size * 0.055)))
        p.setFont(font)
        p.setPen(rgb(200, 210, 240))
        p.drawText(QRectF(card.left(), code.bottom() + 14, card.width(), 30), Qt.AlignCenter, url)
        p.restore()

    def _paint_messages(self, p: QPainter, rect: QRectF) -> None:
        if self._qr is not None and self._qr_left > 0:
            self._paint_qr(p, rect)
        font = QFont()
        size = max(12, int(rect.width() / 90))
        font.setPixelSize(size)
        p.setFont(font)
        p.setPen(Qt.NoPen)
        if self._hint_left > 0:
            a = min(1.0, self._hint_left)
            s, _, _ = fit(rect)
            box = QRectF(rect.left(), rect.bottom() - 60 * s - size * 2.4, rect.width(), size * 2.2)
            p.setPen(rgb(255, 255, 255, 200 * a))
            p.drawText(box, Qt.AlignCenter, HINT)
        if self._toast_left > 0:
            a = min(1.0, self._toast_left)
            metrics_w = p.fontMetrics().horizontalAdvance(self._toast) + size * 3
            box = QRectF(rect.center().x() - metrics_w / 2, rect.top() + size * 1.5, metrics_w, size * 2.4)
            p.setPen(Qt.NoPen)
            p.setBrush(rgb(0, 0, 0, 150 * a))
            p.drawRoundedRect(box, size * 1.2, size * 1.2)
            p.setPen(rgb(255, 255, 255, 240 * a))
            p.drawText(box, Qt.AlignCenter, self._toast)
