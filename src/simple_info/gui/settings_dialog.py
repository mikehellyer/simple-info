"""Settings: where the weather is for, units, and how the boards behave."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from simple_info.core import currency as cx
from simple_info.core import news as nw
from simple_info.core import sports as sp
from simple_info.core import trains as tr
from simple_info.core import tv as tvmod
from simple_info.core import weather as wx
from simple_info.core.settings import Settings
from simple_info.gui.workers import BackgroundRunner


class StationPicker(QWidget):
    """Search for a station by name (or code) and pick one of the matches."""

    def __init__(self, runner: BackgroundRunner, name: str, crs: str, placeholder: str, optional: bool = False):
        super().__init__()
        self._runner = runner
        self.station = tr.Station(name, crs) if crs else None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self._query = QLineEdit()
        self._query.setPlaceholderText(placeholder)
        self._query.returnPressed.connect(self._search)
        search = QPushButton("Search")
        search.clicked.connect(self._search)
        row.addWidget(self._query, 1)
        row.addWidget(search)
        if optional:
            clear = QPushButton("None")
            clear.setToolTip("Show every train")
            clear.clicked.connect(self._clear)
            row.addWidget(clear)
        layout.addLayout(row)
        self._results = QComboBox()
        self._results.currentIndexChanged.connect(self._on_chosen)
        self._results.hide()
        layout.addWidget(self._results)
        self._label = QLabel()
        self._label.setStyleSheet("color: gray;")
        layout.addWidget(self._label)
        self._optional = optional
        self._show()

    def _search(self) -> None:
        query = self._query.text().strip()
        if query:
            self._label.setText("Searching…")
            self._runner.run(lambda: tr.search_stations(query), self._on_results, lambda error: self._on_results([]))

    def _on_results(self, stations: list) -> None:
        self._results.blockSignals(True)
        self._results.clear()
        for s in stations[:30]:
            self._results.addItem(f"{s.name} ({s.crs})", s)
        self._results.blockSignals(False)
        self._results.setVisible(bool(stations))
        if stations:
            self._results.setCurrentIndex(0)
            self._on_chosen(0)
        else:
            self._label.setText("No stations found (or no connection) — try another spelling")

    def _on_chosen(self, index: int) -> None:
        station = self._results.itemData(index)
        if station is not None:
            self.station = station
            self._show()

    def _clear(self) -> None:
        self.station = None
        self._results.hide()
        self._show()

    def _show(self) -> None:
        if self.station:
            self._label.setText(f"Chosen: {self.station.name} ({self.station.crs})")
        else:
            self._label.setText("None: every train" if self._optional else "No station chosen yet — search above")


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, runner: BackgroundRunner, parent=None, cache_dir=None):
        super().__init__(parent)
        self._cache_dir = cache_dir  # where the TV guide is kept, for its list of channels
        self.setWindowTitle("Settings")
        self.setMinimumWidth(620)
        self._runner = runner
        self._place = (
            wx.Location(settings.location_name, settings.latitude, settings.longitude)
            if settings.location_mode == "manual" else None
        )
        outer = QVBoxLayout(self)
        outer.setSizeConstraint(QLayout.SetMinimumSize)  # never squeezed smaller than its contents
        self._tabs = QTabWidget()
        outer.addWidget(self._tabs)
        general = self._tab("General")
        weather_tab = self._tab("Weather")
        trains_tab = self._tab("Trains")
        currency_tab = self._tab("Currency")
        sport_tab = self._tab("Sport")

        # Location
        where = QGroupBox("Weather location")
        wl = QVBoxLayout(where)
        self._auto = QRadioButton("Find my location automatically (from my internet address)")
        self._manual = QRadioButton("Use a place I choose:")
        group = QButtonGroup(self)
        group.addButton(self._auto)
        group.addButton(self._manual)
        wl.addWidget(self._auto)
        wl.addWidget(self._manual)
        row = QHBoxLayout()
        self._query = QLineEdit()
        self._query.setPlaceholderText("Town or city, e.g. Keswick")
        self._query.returnPressed.connect(self._search)
        search = QPushButton("Search")
        search.clicked.connect(self._search)
        row.addWidget(self._query, 1)
        row.addWidget(search)
        wl.addLayout(row)
        self._results = QComboBox()
        self._results.currentIndexChanged.connect(self._on_result_chosen)
        wl.addWidget(self._results)
        self._place_label = QLabel()
        self._place_label.setStyleSheet("color: gray;")
        wl.addWidget(self._place_label)
        weather_tab.addWidget(where)
        (self._manual if self._place else self._auto).setChecked(True)
        self._results.hide()
        self._show_place()

        # Units
        units = QGroupBox("Units and clock")
        ul = QFormLayout(units)
        self._temp = QComboBox()
        self._temp.addItem("°C", "C")
        self._temp.addItem("°F", "F")
        self._temp.setCurrentIndex(self._temp.findData(settings.temperature_unit))
        self._wind = QComboBox()
        self._wind.addItem("mph", "mph")
        self._wind.addItem("km/h", "kmh")
        self._wind.setCurrentIndex(self._wind.findData(settings.wind_unit))
        self._clock24 = QCheckBox("24-hour clock")
        self._clock24.setChecked(settings.clock_24h)
        ul.addRow("Temperature", self._temp)
        ul.addRow("Wind", self._wind)
        ul.addRow("", self._clock24)
        general.addWidget(units)

        # Trains
        trains = QGroupBox("Train board (stations in Great Britain)")
        tl = QFormLayout(trains)
        self._station = StationPicker(runner, settings.train_station_name, settings.train_station_crs,
                                      "Station name or code, e.g. Carlisle or CAR")
        tl.addRow("Station", self._station)
        self._train_mode = QComboBox()
        for label, key in (("Departures", "departures"), ("Arrivals", "arrivals"), ("Both, in turn", "both")):
            self._train_mode.addItem(label, key)
        self._train_mode.setCurrentIndex(max(0, self._train_mode.findData(settings.train_mode)))
        tl.addRow("Show", self._train_mode)
        self._train_filter = StationPicker(runner, settings.train_filter_name, settings.train_filter_crs,
                                           "Optional: only trains calling at…", optional=True)
        tl.addRow("Only trains to/from", self._train_filter)
        self._rail_token = QLineEdit(settings.rail_token)
        self._rail_token.setPlaceholderText("optional — not needed")
        self._rail_token.setToolTip("A National Rail (Darwin OpenLDBWS) access token, if you have your own")
        tl.addRow("National Rail token", self._rail_token)
        trains_tab.addWidget(trains)

        # Boards
        boards = QGroupBox("Boards")
        bl = QFormLayout(boards)
        self._cycle = QCheckBox("Move on to the next board by itself")
        self._cycle.setChecked(settings.cycle_boards)
        self._cycle_seconds = QSpinBox()
        self._cycle_seconds.setRange(5, 3600)
        self._cycle_seconds.setSuffix(" seconds")
        self._cycle_seconds.setValue(settings.cycle_seconds)
        bl.addRow("", self._cycle)
        bl.addRow("Show each board for", self._cycle_seconds)
        self._page_seconds = QSpinBox()
        self._page_seconds.setRange(5, 600)
        self._page_seconds.setSuffix(" seconds")
        self._page_seconds.setValue(settings.page_seconds)
        bl.addRow("Turn pages every", self._page_seconds)
        page_hint = QLabel("(on boards with more than one page, like Sport and TV)")
        page_hint.setStyleSheet("color: gray;")
        bl.addRow("", page_hint)
        general.addWidget(boards)

        # Display
        display = QGroupBox("Display")
        dl = QFormLayout(display)
        self._start_fullscreen = QCheckBox("Start in full screen")
        self._start_fullscreen.setChecked(settings.start_fullscreen)
        self._keep_awake = QCheckBox("Keep the screen awake (no screensaver or lock)")
        self._keep_awake.setChecked(settings.keep_awake)
        self._tv_remote = QCheckBox("TV remote, over HDMI (HDMI-CEC)")
        self._tv_remote.setChecked(settings.tv_remote)
        self._graphics = QComboBox()
        for label, key in (("Automatic", "auto"), ("Full", "full"), ("Light (for a Raspberry Pi)", "light")):
            self._graphics.addItem(label, key)
        self._graphics.setCurrentIndex(max(0, self._graphics.findData(settings.graphics)))
        dl.addRow("", self._start_fullscreen)
        dl.addRow("", self._keep_awake)
        dl.addRow("", self._tv_remote)
        dl.addRow("Graphics", self._graphics)
        general.addWidget(display)

        # Currency
        money = QGroupBox("Currency board")
        ml = QFormLayout(money)
        self._base = QComboBox()
        for code, (name, symbol) in cx.CURRENCIES.items():
            self._base.addItem(f"{code} — {name}", code)
        self._base.setCurrentIndex(max(0, self._base.findData(settings.currency_base)))
        ml.addRow("What 1 of", self._base)
        self._codes = QListWidget()
        self._codes.setDragDropMode(QAbstractItemView.InternalMove)
        self._codes.setMinimumHeight(180)
        chosen = [c for c in settings.currency_codes.split(",") if c in cx.CURRENCIES]
        for code in chosen + [c for c in cx.CURRENCIES if c not in chosen]:
            item = QListWidgetItem(f"{code} — {cx.CURRENCIES[code][0]}")
            item.setData(Qt.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            item.setCheckState(Qt.Checked if code in chosen else Qt.Unchecked)
            self._codes.addItem(item)
        ml.addRow("buys in", self._codes)
        hint = QLabel("Tick up to 12; drag to change the order.")
        hint.setStyleSheet("color: gray;")
        ml.addRow("", hint)
        self._crypto = QCheckBox("Bitcoin and Ethereum too")
        self._crypto.setChecked(settings.currency_crypto)
        ml.addRow("", self._crypto)
        currency_tab.addWidget(money)

        # Sport
        sport = QGroupBox("Sport board")
        sl = QFormLayout(sport)
        self._competitions = QListWidget()
        self._competitions.setDragDropMode(QAbstractItemView.InternalMove)
        self._competitions.setMinimumHeight(240)
        chosen = [k for k in settings.sport_competitions.split(",") if k in sp.BY_KEY]
        for key in chosen + [c.key for c in sp.COMPETITIONS if c.key not in chosen]:
            comp = sp.BY_KEY[key]
            item = QListWidgetItem(f"{comp.name}  ({sp.SPORT_NAMES[comp.sport].lower()})")
            item.setData(Qt.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            item.setCheckState(Qt.Checked if key in chosen else Qt.Unchecked)
            self._competitions.addItem(item)
        sl.addRow("Follow", self._competitions)
        hint = QLabel("Each ticked competition gets a page of its own; drag to change the order.\n"
                      "Pick a competition in the list to choose its favourite team, shown in gold.")
        hint.setStyleSheet("color: gray;")
        sl.addRow("", hint)
        # a favourite team for the competition picked in the list, shown in gold on its page
        self._favourites = sp.parse_favourites(settings.sport_favourites)
        self._team_lists: dict[str, list] = {}
        self._favourite = QComboBox()
        self._favourite.setEnabled(False)
        self._favourite.currentIndexChanged.connect(self._on_favourite_chosen)
        self._favourite_label = QLabel("Favourite team")
        sl.addRow(self._favourite_label, self._favourite)
        self._competitions.currentItemChanged.connect(lambda item, _: self._show_favourite(item))
        sport_tab.addWidget(sport)

        # TV
        tv_tab = self._tab("TV")
        tv_box = QGroupBox("TV board (Freeview channels)")
        tvl = QVBoxLayout(tv_box)
        self._tv_list = QListWidget()
        self._tv_list.setDragDropMode(QAbstractItemView.InternalMove)
        self._tv_list.setMinimumHeight(300)
        tvl.addWidget(self._tv_list)
        tv_hint = QLabel("Tick the channels to show, and drag them into your order; ten fit on a page.")
        tv_hint.setStyleSheet("color: gray;")
        tvl.addWidget(tv_hint)
        tv_tab.addWidget(tv_box)
        self._tv_chosen = [c for c in settings.tv_channels.split(",") if c]
        self._fill_channels([tvmod.Channel(c, c) for c in self._tv_chosen])  # until the full list is read
        self._runner.run(lambda: tvmod.read_channels(tvmod.guide_path(self._cache_dir)) if self._cache_dir else [],
                         self._fill_channels, lambda error: None)
        # News
        news_tab = self._tab("News")
        news_box = QGroupBox("News board")
        nl = QVBoxLayout(news_box)
        self._feeds = QListWidget()
        self._feeds.setDragDropMode(QAbstractItemView.InternalMove)
        self._feeds.setMinimumHeight(300)
        chosen = [k for k in settings.news_feeds.split(",") if k in nw.BY_KEY]
        for key in chosen + [f.key for f in nw.FEEDS if f.key not in chosen]:
            item = QListWidgetItem(nw.BY_KEY[key].name)
            item.setData(Qt.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            item.setCheckState(Qt.Checked if key in chosen else Qt.Unchecked)
            self._feeds.addItem(item)
        nl.addWidget(self._feeds)
        news_hint = QLabel("Each ticked feed gets a page of its own; drag to change the order.")
        news_hint.setStyleSheet("color: gray;")
        nl.addWidget(news_hint)
        news_tab.addWidget(news_box)
        for tab in (general, weather_tab, trains_tab, currency_tab, sport_tab, tv_tab, news_tab):
            tab.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _search(self) -> None:
        query = self._query.text().strip()
        if not query:
            return
        self._manual.setChecked(True)
        self._place_label.setText("Searching…")
        self._runner.run(lambda: wx.search_places(query), self._on_results, lambda error: self._on_results([]))

    def _on_results(self, places: list) -> None:
        self._results.blockSignals(True)
        self._results.clear()
        for place in places:
            self._results.addItem(place.name, place)
        self._results.blockSignals(False)
        self._results.setVisible(bool(places))
        if places:
            self._results.setCurrentIndex(0)
            self._on_result_chosen(0)
        else:
            self._place_label.setText("No places found (or no connection) — try another spelling")

    def _on_result_chosen(self, index: int) -> None:
        place = self._results.itemData(index)
        if place is not None:
            self._place = place
            self._show_place()

    def _show_place(self) -> None:
        if self._place:
            self._place_label.setText(f"Chosen: {self._place.name}  ({self._place.latitude:.2f}, {self._place.longitude:.2f})")
        else:
            self._place_label.setText("No place chosen yet — search above")

    def _show_favourite(self, item) -> None:
        key = item.data(Qt.UserRole) if item is not None else None
        self._favourite_key = key
        if key is None:
            return
        self._favourite_label.setText(f"Favourite in {sp.BY_KEY[key].name}")
        if key in self._team_lists:
            self._fill_favourites(key)
            return
        self._favourite.blockSignals(True)
        self._favourite.clear()
        self._favourite.addItem("Finding the teams…", None)
        self._favourite.blockSignals(False)
        self._favourite.setEnabled(False)
        self._runner.run(lambda: sp.fetch_teams(key), lambda teams: self._on_teams(key, teams), lambda error: self._on_teams(key, []))

    def _on_teams(self, key: str, teams: list) -> None:
        if teams:
            self._team_lists[key] = teams
        if key == self._favourite_key:
            self._fill_favourites(key)

    def _fill_favourites(self, key: str) -> None:
        teams = self._team_lists.get(key, [])
        self._favourite.blockSignals(True)
        self._favourite.clear()
        if not teams:
            self._favourite.addItem("Couldn't get the teams (no connection?)", None)
            self._favourite.setEnabled(False)
        else:
            self._favourite.addItem("None", "")
            for team_id, name in teams:
                self._favourite.addItem(name, team_id)
            self._favourite.setCurrentIndex(max(0, self._favourite.findData(self._favourites.get(key, ""))))
            self._favourite.setEnabled(True)
        self._favourite.blockSignals(False)

    def _on_favourite_chosen(self, index: int) -> None:
        key, team = getattr(self, "_favourite_key", None), self._favourite.itemData(index)
        if key is None or team is None:
            return
        if team:
            self._favourites[key] = team
        else:
            self._favourites.pop(key, None)

    def _fill_channels(self, channels: list) -> None:
        if not channels:
            return
        # keep any ticks and order the viewer has already changed
        if self._tv_list.count():
            self._tv_chosen = [self._tv_list.item(i).data(Qt.UserRole) for i in range(self._tv_list.count())
                               if self._tv_list.item(i).checkState() == Qt.Checked]
        by_id = {c.id: c for c in channels}
        self._tv_list.clear()
        for cid in self._tv_chosen + [c.id for c in channels if c.id not in self._tv_chosen]:
            channel = by_id.get(cid, tvmod.Channel(cid, cid))
            item = QListWidgetItem(channel.short_name if channel.name != cid else cid)
            item.setData(Qt.UserRole, cid)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            item.setCheckState(Qt.Checked if cid in self._tv_chosen else Qt.Unchecked)
            self._tv_list.addItem(item)

    def _tab(self, title: str) -> QVBoxLayout:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._tabs.addTab(page, title)
        return layout

    def _chosen_codes(self) -> list[str]:
        base = self._base.currentData()
        codes = [self._codes.item(i).data(Qt.UserRole) for i in range(self._codes.count())
                 if self._codes.item(i).checkState() == Qt.Checked]
        return [c for c in codes if c != base][:12]

    def values(self) -> dict:
        manual = self._manual.isChecked() and self._place is not None
        values = {
            "location_mode": "manual" if manual else "auto",
            "temperature_unit": self._temp.currentData(),
            "wind_unit": self._wind.currentData(),
            "clock_24h": self._clock24.isChecked(),
            "cycle_boards": self._cycle.isChecked(),
            "cycle_seconds": self._cycle_seconds.value(),
            "keep_awake": self._keep_awake.isChecked(),
            "start_fullscreen": self._start_fullscreen.isChecked(),
            "tv_remote": self._tv_remote.isChecked(),
            "graphics": self._graphics.currentData(),
            "train_mode": self._train_mode.currentData(),
            "rail_token": self._rail_token.text().strip(),
            "currency_base": self._base.currentData(),
            "currency_codes": ",".join(self._chosen_codes()),
            "currency_crypto": self._crypto.isChecked(),
            "sport_competitions": ",".join(
                self._competitions.item(i).data(Qt.UserRole) for i in range(self._competitions.count())
                if self._competitions.item(i).checkState() == Qt.Checked),
            "page_seconds": self._page_seconds.value(),
            "news_feeds": ",".join(self._feeds.item(i).data(Qt.UserRole) for i in range(self._feeds.count())
                                   if self._feeds.item(i).checkState() == Qt.Checked),
            "tv_channels": ",".join(self._tv_list.item(i).data(Qt.UserRole) for i in range(self._tv_list.count())
                                    if self._tv_list.item(i).checkState() == Qt.Checked),
            "sport_favourites": sp.format_favourites(self._favourites),
        }
        station, filter_ = self._station.station, self._train_filter.station
        values.update(train_station_name=station.name if station else "", train_station_crs=station.crs if station else "",
                      train_filter_name=filter_.name if filter_ else "", train_filter_crs=filter_.crs if filter_ else "")
        if manual:
            values.update(location_name=self._place.name, latitude=self._place.latitude, longitude=self._place.longitude)
        return values
