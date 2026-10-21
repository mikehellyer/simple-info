"""Settings: where the weather is for, units, and how the boards behave."""
from __future__ import annotations

from PySide6.QtWidgets import (
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
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from simple_info.core import weather as wx
from simple_info.core.settings import Settings
from simple_info.gui.workers import BackgroundRunner


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
        }
        if manual:
            values.update(location_name=self._place.name, latitude=self._place.latitude, longitude=self._place.longitude)
        return values
