"""What every information board has in common.

A board is drawn in two layers:
- the background, which says at a glance what kind of information this is
  and may move (drifting clouds, falling rain…). It's drawn every frame,
  filling the whole window.
- the content (the figures, tables and words), drawn on the 1600×900
  virtual canvas, centred and scaled to fit. It changes at most once a
  second, so the stage keeps it as an image and only redraws it when
  content_key() changes or the board says it's dirty.

A board that needs data from the internet hands the main window a job to
run on a background thread (fetch_job), and gets the result back on the
GUI thread (on_fetched). The main window decides when, from due().
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Callable, Hashable, Optional

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter

from simple_info.core.settings import Settings
from simple_info.gui.paint import rgb


TITLE_WIDTH = 640.0  # board titles stay left of the top centre, where the paused badge goes


def fit_title(text: str, font, width: float = TITLE_WIDTH):
    """The title's font, made smaller (down to two thirds) if the title is too long, then cut short with …"""
    from PySide6.QtGui import QFontMetricsF
    from PySide6.QtCore import Qt

    smallest = int(font.pixelSize() * 0.66)
    while QFontMetricsF(font).horizontalAdvance(text) > width and font.pixelSize() > smallest:
        font.setPixelSize(font.pixelSize() - 1)
    return font, QFontMetricsF(font).elidedText(text, Qt.ElideRight, width)


class Board:
    key = ""  # stable id, remembered in the settings
    title = ""  # shown in the board bar along the bottom
    accent: QColor = rgb(255, 255, 255)  # the board bar's colour for this board
    refresh_seconds = 15 * 60  # how often to fetch new data
    retry_seconds = 2 * 60  # how soon to try again after a failed fetch

    def __init__(self):
        self.dirty = True  # the content needs redrawing
        self.fetching = False
        self._next_fetch = 0.0  # monotonic time; 0 = as soon as possible
        self.page = 0
        self.paused = False  # held by the stage: anything that takes turns stays put

    # --- settings and data

    def configure(self, settings: Settings) -> None:
        """Called at start and whenever the settings change."""

    def fetch_job(self) -> Optional[Callable[[], object]]:
        """A function to run on a background thread to fetch this board's
        data, or None if the board has nothing to fetch."""
        return None

    def on_fetched(self, result) -> bool:
        """The fetch job's result, back on the GUI thread (None if it
        raised). Returns whether it worked, which sets when to fetch next."""
        return True

    def due(self, now: Optional[float] = None) -> bool:
        return not self.fetching and (now if now is not None else time.monotonic()) >= self._next_fetch

    def fetch_now(self) -> None:
        """Fetch at the next opportunity, whatever the schedule says."""
        self._next_fetch = 0.0

    def begin_fetch(self) -> None:
        self.fetching = True

    def end_fetch(self, ok: bool, now: Optional[float] = None) -> None:
        self.fetching = False
        self._next_fetch = (now if now is not None else time.monotonic()) + (self.refresh_seconds if ok else self.retry_seconds)
        self.dirty = True

    # --- pages (a board with more than one takes turns through them)

    page_seconds = 20.0

    def page_count(self) -> int:
        return 1

    def set_page(self, page: int) -> None:
        n = self.page_count()
        self.page = page % n if n else 0
        self.dirty = True

    # --- drawing

    def step(self, dt: float) -> None:
        """Move the background on by dt seconds."""

    def paint_background(self, p: QPainter, target: QRectF) -> None:
        p.fillRect(target, rgb(10, 12, 18))

    def content_key(self, now: datetime) -> Hashable:
        """The content is redrawn whenever this changes (or dirty is set)."""
        return now.replace(microsecond=0)

    def paint_content(self, p: QPainter, now: datetime) -> None:
        """Draw the content on the 1600×900 virtual canvas."""

    has_live = False  # set by boards that draw something moving over their content

    def paint_live(self, p: QPainter, t: float) -> None:
        """Draw anything that moves smoothly over the content (a scrolling
        line of text…), every frame, on the 1600×900 virtual canvas. t is in
        seconds and only ever increases."""
