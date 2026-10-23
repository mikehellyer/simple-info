"""The main window: the stage, the update banner, keyboard shortcuts, the
right-click menu, and keeping every board's data up to date."""
from __future__ import annotations

import sys
import time
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Optional

from platformdirs import user_cache_dir
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMenu, QMessageBox, QVBoxLayout, QWidget

from simple_info import __version__
from simple_info.core import cec
from simple_info.core import weather as wx
from simple_info.core.diagnostics import log_event
from simple_info.core.keep_awake import KeepAwake
from simple_info.core.remote_server import RemoteServer, qr_matrix
from simple_info.core.platform_info import is_raspberry_pi
from simple_info.core.self_update import download_asset, find_asset_for_this_platform, launch_installer
from simple_info.core.settings import SettingsStore
from simple_info.core.tv_keys import ACTIONS as TV_KEY_ACTIONS
from simple_info.core.tv_keys import TvKeyReader
from simple_info.core.updater import API_TIMEOUT_SECONDS, check_for_update
from simple_info.gui.boards.base import Board
from simple_info.gui.boards.currency import CurrencyBoard
from simple_info.gui.boards.news import NewsBoard
from simple_info.gui.boards.sport import SportBoard
from simple_info.gui.boards.tv import TvBoard
from simple_info.gui.boards.trains import TrainBoard
from simple_info.gui.boards.weather import WeatherBoard
from simple_info.gui.settings_dialog import SettingsDialog
from simple_info.gui.stage import Stage
from simple_info.gui.update_banner import UpdateBanner
from simple_info.gui.workers import BackgroundRunner

UPDATE_OWNER = "mikehellyer"
UPDATE_REPO = "simple-info"
BACKGROUND_JOIN_TIMEOUT_MS = (max(API_TIMEOUT_SECONDS, wx.TIMEOUT_SECONDS) + 1) * 1000
ICON_PATH = Path(__file__).parent / "resources" / "icon.png"
SERVICE_MS = 1000  # how often to see whether a board wants new data


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simple-Info")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1280, 760)

        self._store = SettingsStore()
        self._runner = BackgroundRunner(self)
        self._keep_awake = KeepAwake()
        self._pending_update = None
        self._last_action: dict[str, float] = {}
        self._tv_keys: Optional[TvKeyReader] = None
        self._unused_tv_keys: set[str] = set()
        self._remote: Optional[RemoteServer] = None
        self._remote_state: dict = {}
        self._remote_timer = QTimer(self)
        self._remote_timer.timeout.connect(self._poll_remote)
        self._cec_timer = QTimer(self)
        self._cec_timer.timeout.connect(self._register_tv_remote)
        self._tv_key_timer = QTimer(self)
        self._tv_key_timer.timeout.connect(self._poll_tv_keys)

        cache = Path(user_cache_dir("Simple-Info"))
        self._cache = cache
        self._weather = WeatherBoard(cache)
        self._trains = TrainBoard()
        self._currency = CurrencyBoard(cache)
        self._sport = SportBoard()
        self._tv = TvBoard(cache)
        self._news = NewsBoard()
        self._boards: list[Board] = [self._weather, self._trains, self._currency, self._sport, self._tv, self._news]

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._update_banner = UpdateBanner()
        self._update_banner.update_clicked.connect(self._start_update)
        layout.addWidget(self._update_banner)
        self._stage = Stage(self._boards)
        self._stage.setContextMenuPolicy(Qt.CustomContextMenu)
        self._stage.customContextMenuRequested.connect(self._show_menu)
        self._stage.board_changed.connect(lambda key: self._store.update(board=key, board_page=0))
        self._stage.page_changed.connect(lambda page: self._store.update(board_page=page))
        self._stage.pause_clicked.connect(self._toggle_pause)
        layout.addWidget(self._stage, 1)
        self.setCentralWidget(central)

        self._build_actions()
        self._apply_settings()
        s = self._store.settings
        page = s.board_page  # (read first: switching boards resets the saved page)
        if self._stage.show_key(s.board, fade=False) and page < self._stage.board.page_count():
            self._stage.board.set_page(page)  # back to the page it was on
            self._store.update(board_page=page)
        if s.paused:
            self._stage.set_paused(True)
            self._act_pause.setChecked(True)

        self._service_timer = QTimer(self)
        self._service_timer.timeout.connect(self._service_boards)
        self._service_timer.start(SERVICE_MS)
        self._service_boards()
        self._check_for_updates()

    # --- actions and the menu

    def _action(self, text: str, keys, slot, checkable: bool = False) -> QAction:
        action = QAction(text, self)
        if keys:
            action.setShortcuts([QKeySequence(k) for k in (keys if isinstance(keys, (list, tuple)) else [keys])])
        action.setShortcutContext(Qt.WindowShortcut)
        action.setCheckable(checkable)
        action.triggered.connect(slot)
        self.addAction(action)
        return action

    def _build_actions(self) -> None:
        # Besides the keyboard, a TV remote (over HDMI-CEC) or a Bluetooth
        # clicker sends arrows, OK, back, channel up/down and the coloured buttons.
        k = Qt.Key
        self._act_next = self._action("Next board", [k.Key_Right, k.Key_PageDown, "Space", "Tab", k.Key_ChannelUp],
                                      lambda: self._once("next", self._stage.next_board))
        self._act_previous = self._action("Previous board", [k.Key_Left, k.Key_PageUp, "Shift+Tab", k.Key_ChannelDown],
                                          lambda: self._once("previous", self._stage.previous_board))
        self._act_page_next = self._action("Next page", [k.Key_Down], lambda: self._once("page", lambda: self._stage.turn_page(1)))
        self._act_page_previous = self._action("Previous page", [k.Key_Up], lambda: self._once("page", lambda: self._stage.turn_page(-1)))
        self._board_actions = []
        for i, board in enumerate(self._boards[:9]):
            self._board_actions.append(self._action(board.title, str(i + 1), partial(self._stage.show_board, i)))
        self._act_pause = self._action("Pause (stay on this page)",
                                       ["H", k.Key_Pause, k.Key_MediaTogglePlayPause, k.Key_MediaPause, k.Key_MediaPlay],
                                       lambda: self._once("hold", self._toggle_pause), checkable=True)
        self._act_cycle = self._action("Move through the boards by itself", ["C", k.Key_Red],
                                       lambda: self._once("cycle", self._toggle_cycle), checkable=True)
        self._act_full = self._action("Full screen", ["F", "F11"], self._toggle_full_screen, checkable=True)
        self._act_refresh = self._action("Refresh now", ["R", k.Key_Green], lambda: self._once("refresh", self._refresh_now))
        self._act_preview_weather = self._action("Preview another weather", ["P", k.Key_Yellow],
                                                 lambda: self._once("weather_preview", self._cycle_weather_preview))
        self._act_preview_time = self._action("Preview another time of day", ["T"],
                                              lambda: self._once("time_preview", self._cycle_time_preview))
        self._act_phone = self._action("Show the phone remote's QR code", ["Q", k.Key_Blue],
                                       lambda: self._once("phone_qr", self._show_phone_remote))
        self._act_settings = self._action("Settings…", ["S", "Ctrl+,"], self._open_settings)
        self._act_about = self._action("About Simple-Info", None, self._about)
        self._act_quit = self._action("Quit", "Ctrl+Q", self.close)
        self._action("", "Escape", self._on_escape)

    def _show_menu(self, pos) -> None:
        menu = QMenu(self)
        boards = menu.addMenu("Boards")
        for action in self._board_actions:
            boards.addAction(action)
        for action in (self._act_next, self._act_previous, self._act_page_next, self._act_page_previous, self._act_pause, self._act_cycle,
                       self._act_phone, None, self._act_full, self._act_refresh, None,
                       self._act_preview_weather, self._act_preview_time, None, self._act_settings, self._act_about, self._act_quit):
            menu.addSeparator() if action is None else menu.addAction(action)
        menu.exec(self._stage.mapToGlobal(pos))

    def _on_escape(self) -> None:
        if self.isFullScreen():
            self._toggle_full_screen()

    def show_at_start(self, fullscreen: bool = False) -> None:
        """Show the window, full screen if asked to (here, or in Settings)."""
        if fullscreen or self._store.settings.start_fullscreen:
            self.showFullScreen()
        else:
            self.show()
        # take the keyboard focus, so keys from a keyboard (or a TV remote,
        # through the desktop) come here straight away
        self.raise_()
        self.activateWindow()
        self._stage.setFocus()
        self._act_full.setChecked(self.isFullScreen())

    def _toggle_full_screen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        self._act_full.setChecked(self.isFullScreen())

    def _toggle_pause(self) -> None:
        paused = not self._stage.paused
        self._stage.set_paused(paused)
        self._act_pause.setChecked(paused)
        self._store.update(paused=paused, board_page=self._stage.board.page)
        self._stage.toast("Paused: staying on this page (H to carry on)" if paused else "Carrying on")

    def _toggle_cycle(self) -> None:
        on = not self._store.settings.cycle_boards
        self._store.update(cycle_boards=on)
        self._apply_settings()
        self._stage.toast(f"Moving to the next board every {self._store.settings.cycle_seconds} seconds" if on else "Staying on this board")

    def _once(self, name: str, action) -> None:
        """Do an action, unless it was done a moment ago: a TV remote's
        button can arrive twice (through the desktop and read directly),
        and a toggle done twice would undo itself."""
        now = time.monotonic()
        if now - self._last_action.get(name, 0.0) < 0.3:
            return
        self._last_action[name] = now
        action()

    # --- previews (to see each weather without waiting for it)

    def _cycle_weather_preview(self) -> None:
        self._stage.show_key(self._weather.key)
        self._stage.toast(self._weather.cycle_weather_preview())

    def _cycle_time_preview(self) -> None:
        self._stage.show_key(self._weather.key)
        self._stage.toast(self._weather.cycle_time_preview())

    # --- the TV remote

    # --- the phone remote

    def _apply_phone_remote(self) -> None:
        s = self._store.settings
        wanted = s.phone_remote
        if self._remote is not None and (not wanted or self._remote.port != s.remote_port or self._remote.pin != s.remote_pin):
            self._remote.stop()
            self._remote = None
            self._remote_timer.stop()
        if wanted and self._remote is None:
            self._remote = RemoteServer(lambda: self._remote_state, s.remote_port, s.remote_pin)
            if self._remote.start():
                log_event(f"phone remote at {self._remote.url()}")
                self._remote_state = self._make_remote_state()
                self._remote_timer.start(150)
            else:
                log_event(f"phone remote couldn't start: {self._remote.error}")
                self._stage.toast(f"The phone remote couldn't start (port {s.remote_port} in use?)", 6)
                self._remote = None

    def remote_url(self) -> Optional[str]:
        return self._remote.url() if self._remote is not None else None

    def _show_phone_remote(self) -> None:
        url = self.remote_url()
        if url is None:
            self._stage.toast("The phone remote is off: turn it on in Settings (S) → Phone remote", 5)
            return
        self._stage.show_qr(qr_matrix(url), url)

    def _make_remote_state(self) -> dict:
        s = self._store.settings
        board = self._stage.board
        now = datetime.now()
        accent = board.accent
        return {
            "version": __version__,
            "time": now.strftime("%H:%M") if s.clock_24h else now.strftime("%I:%M %p").lstrip("0"),
            "board": board.key,
            "board_title": board.title,
            "accent": f"#{accent.red():02x}{accent.green():02x}{accent.blue():02x}",
            "boards": [{"key": b.key, "title": b.title} for b in self._boards],
            "page": board.page,
            "pages": board.page_names(),
            "paused": self._stage.paused,
            "cycle": s.cycle_boards,
            "fullscreen": self.isFullScreen(),
        }

    def _poll_remote(self) -> None:
        if self._remote is None:
            return
        for action, value in self._remote.take_commands():
            self._remote_command(action, value)
        self._remote_state = self._make_remote_state()  # (swapped whole, so the server thread never sees half)

    def _remote_command(self, action: str, value) -> None:
        if action == "board":
            self._stage.show_key(value)
        elif action == "page":
            board = self._stage.board
            if value == "next":
                self._stage.turn_page(1)
            elif value == "previous":
                self._stage.turn_page(-1)
            elif isinstance(value, int) and value < board.page_count() and value != board.page:
                self._stage.turn_page(value - board.page)
        elif action == "pause":
            self._toggle_pause()
        elif action == "cycle":
            self._toggle_cycle()
        elif action == "refresh":
            self._refresh_now()
        elif action == "fullscreen":
            self._toggle_full_screen()

    def _apply_tv_remote(self) -> None:
        if self._store.settings.tv_remote and cec.cec_devices():
            if not self._cec_timer.isActive():
                self._register_tv_remote()
                self._cec_timer.start(10 * 60 * 1000)  # re-registered now and then, in case the TV was off
                self._tv_key_timer.start(40)
        else:
            self._cec_timer.stop()
            self._tv_key_timer.stop()
            if self._tv_keys is not None:
                self._tv_keys.stop()
                self._tv_keys = None

    def _register_tv_remote(self) -> None:
        self._runner.run(cec.register_with_tv, lambda message: log_event(message), lambda error: None)

    def _poll_tv_keys(self) -> None:
        if self._tv_keys is None:
            reader = TvKeyReader()
            if reader.start():
                self._tv_keys = reader
                log_event(f"reading TV remote keys from {', '.join(f'{n} ({p})' for n, p in reader.devices)}")
            else:
                if reader.errors:
                    log_event(f"can't read TV remote keys: {'; '.join(reader.errors)}")
                self._tv_key_timer.setInterval(60 * 1000)  # the device may turn up later: look again in a minute
                return
            self._tv_key_timer.setInterval(40)
        for key in self._tv_keys.take():
            action = TV_KEY_ACTIONS.get(key)
            if action is None:
                if key not in self._unused_tv_keys:  # (logged once each, to see what a TV sends)
                    self._unused_tv_keys.add(key)
                    log_event(f"TV remote button with nothing to do: {key}")
                continue
            if action.startswith("board_"):
                index = int(action[6:]) - 1
                if index < len(self._boards):
                    self._stage.show_board(index)
                continue
            {
                "next": lambda: self._once("next", self._stage.next_board),
                "previous": lambda: self._once("previous", self._stage.previous_board),
                "page_next": lambda: self._once("page", lambda: self._stage.turn_page(1)),
                "page_previous": lambda: self._once("page", lambda: self._stage.turn_page(-1)),
                "refresh": lambda: self._once("refresh", self._refresh_now),
                "cycle": lambda: self._once("cycle", self._toggle_cycle),
                "hold": lambda: self._once("hold", self._toggle_pause),
                "weather_preview": lambda: self._once("weather_preview", self._cycle_weather_preview),
                "time_preview": lambda: self._once("time_preview", self._cycle_time_preview),
                "phone_qr": lambda: self._once("phone_qr", self._show_phone_remote),
            }[action]()

    # --- settings

    def _apply_settings(self) -> None:
        s = self._store.settings
        for board in self._boards:
            board.configure(s)
        self._stage.cycle = s.cycle_boards
        self._stage.cycle_seconds = s.cycle_seconds
        self._act_cycle.setChecked(s.cycle_boards)
        light = s.graphics == "light" or (s.graphics == "auto" and is_raspberry_pi())
        self._stage.set_light_graphics(light)
        if s.keep_awake and not self._keep_awake.active:
            log_event(f"keeping the screen awake via {self._keep_awake.start() or 'nothing (not supported here)'}")
        elif not s.keep_awake and self._keep_awake.active:
            self._keep_awake.stop()
            log_event("no longer keeping the screen awake")
        self._apply_tv_remote()
        self._apply_phone_remote()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._store.settings, self._runner, self, cache_dir=self._cache, remote_url=self.remote_url())
        if dialog.exec():
            self._store.update(**dialog.values())
        self._apply_settings()
        self._service_boards()

    # --- data

    def _service_boards(self) -> None:
        """Start a fetch for every board whose data is due."""
        for board in self._boards:
            if not board.due():
                continue
            job = board.fetch_job()
            if job is None:
                continue
            board.begin_fetch()
            self._runner.run(job, partial(self._on_fetched, board), partial(self._on_fetch_failed, board))

    def _on_fetched(self, board: Board, result) -> None:
        board.end_fetch(board.on_fetched(result))

    def _on_fetch_failed(self, board: Board, error: Exception) -> None:
        log_event(f"{board.key}: fetch failed: {error!r}")
        board.end_fetch(board.on_fetched(None))

    def _refresh_now(self) -> None:
        self._stage.board.fetch_now()
        self._service_boards()
        self._stage.toast(f"Refreshing {self._stage.board.title.lower()}…", 2)

    # --- about & updates

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About Simple-Info",
            f"<b>Simple-Info</b> v{__version__}<br><br>"
            "An information board: switch between boards of live information, "
            "each with its own background so you can tell at a glance what it shows.<br><br>"
            "Weather data by <a href='https://open-meteo.com/'>Open-Meteo.com</a> (CC BY 4.0).<br>"
            "Train times from National Rail Enquiries, via <a href='https://huxley2.azurewebsites.net/'>Huxley 2</a>.<br>"
            "Exchange rates: European Central Bank, via <a href='https://frankfurter.dev/'>Frankfurter</a>; "
            "crypto prices by <a href='https://www.coingecko.com/'>CoinGecko</a>.<br>"
            "Sport scores and tables from ESPN and BBC Sport.<br>"
            "TV listings from the open-source <a href='https://github.com/dp247/Freeview-EPG'>Freeview EPG</a>.<br>"
            "News from the BBC News, Sky News and Guardian RSS feeds.<br><br>"
            "By Mike Hellyer, built with Claude Code.",
        )

    def _check_for_updates(self) -> None:
        self._runner.run(
            lambda: check_for_update(__version__, UPDATE_OWNER, UPDATE_REPO),
            self._on_update_checked,
            lambda error: None,
        )

    def _on_update_checked(self, info) -> None:
        if info:
            self._pending_update = info
            self._update_banner.announce(info.version)

    def _start_update(self) -> None:
        if self._pending_update is None:
            return
        asset_url = find_asset_for_this_platform(self._pending_update.assets)
        if asset_url is None:
            self._update_banner.set_status(f"No installer for this platform — see {self._pending_update.url}")
            return
        self._update_banner.set_busy(True, "Downloading…")
        self._runner.run(lambda: download_asset(asset_url), self._on_update_downloaded, lambda error: self._on_update_downloaded(None))

    def _on_update_downloaded(self, path) -> None:
        if path is None:
            self._update_banner.set_status("Couldn't download the update — try again")
            self._update_banner.set_busy(False)
            return
        try:
            process = launch_installer(path)
        except OSError:
            self._update_banner.set_status(f"Downloaded to {path} — open it manually")
            self._update_banner.set_busy(False)
            return

        self._update_banner.set_status("Installer launched — closing to finish…")
        if sys.platform not in ("win32", "darwin") and process is not None:
            # Linux: wait for pkexec/apt to finish before quitting — quitting
            # immediately can kill its password prompt before it's answered.
            self._runner.run(lambda: (path, self._wait_for_installer(process)), self._on_installer_finished)
        else:
            QTimer.singleShot(1500, self.close)

    @staticmethod
    def _wait_for_installer(process) -> tuple[int, str]:
        returncode = process.wait()
        stderr_text = process.stderr.read().strip() if process.stderr is not None else ""
        return returncode, stderr_text

    def _on_installer_finished(self, result) -> None:
        path, (returncode, stderr_text) = result
        if returncode == 0:
            self.close()
            return
        detail = f": {stderr_text}" if stderr_text else f" (exit code {returncode})"
        self._update_banner.set_status(f"Update didn't install{detail} — installer is at {path}")
        self._update_banner.set_busy(False)

    def closeEvent(self, event) -> None:
        if self._remote is not None:
            self._remote.stop()
        self._stage.shutdown()
        self._service_timer.stop()
        self._keep_awake.stop()
        if self._tv_keys is not None:
            self._tv_keys.stop()
        self._store.save()
        self._runner.shutdown(BACKGROUND_JOIN_TIMEOUT_MS)
        super().closeEvent(event)
