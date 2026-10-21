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
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from simple_info.core import currency as cx
from simple_info.core import trains as tr
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
    def __init__(self, settings: Settings, runner: BackgroundRunner, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(900)
        self._runner = runner
        self._place = (
            wx.Location(settings.location_name, settings.latitude, settings.longitude)
            if settings.location_mode == "manual" else None
        )
        outer = QVBoxLayout(self)
        columns = QHBoxLayout()
        outer.addLayout(columns)
        layout = QVBoxLayout()  # the left-hand column
        right = QVBoxLayout()
        columns.addLayout(layout)
        columns.addLayout(right)

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
        layout.addWidget(where)
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
        layout.addWidget(units)

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
        layout.addWidget(trains)
        layout.addStretch(1)

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
        right.addWidget(boards)

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
        right.addWidget(display)

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
        right.addWidget(money)
        right.addStretch(1)

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
        }
        station, filter_ = self._station.station, self._train_filter.station
        values.update(train_station_name=station.name if station else "", train_station_crs=station.crs if station else "",
                      train_filter_name=filter_.name if filter_ else "", train_filter_crs=filter_.crs if filter_ else "")
        if manual:
            values.update(location_name=self._place.name, latitude=self._place.latitude, longitude=self._place.longitude)
        return values
