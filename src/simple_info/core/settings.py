"""Persisted user preferences."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional

from platformdirs import user_config_dir


@dataclass
class Settings:
    # Where the weather is for: "auto" (from this machine's IP address) or
    # "manual" (a place picked in Settings).
    location_mode: str = "auto"
    location_name: str = ""
    latitude: float = 0.0
    longitude: float = 0.0

    temperature_unit: str = "C"  # "C" or "F"
    wind_unit: str = "mph"  # "mph" or "kmh"
    clock_24h: bool = True

    # The train board: a station in Great Britain (name and three-letter
    # code), departures, arrivals or both in turn, and optionally only the
    # trains going to (or coming from) another station.
    train_station_name: str = ""
    train_station_crs: str = ""
    train_mode: str = "departures"  # "departures", "arrivals" or "both"
    train_filter_name: str = ""
    train_filter_crs: str = ""
    # A National Rail (Darwin) access token, if you have one: not needed.
    rail_token: str = ""

    # The currency board: what one of `currency_base` buys in each of
    # `currency_codes` (comma-separated, shown in that order), and whether
    # Bitcoin and Ethereum join in.
    currency_base: str = "GBP"
    currency_codes: str = "EUR,USD,CAD,AUD,JPY,CHF,NZD,SEK,NOK"
    currency_crypto: bool = True

    # The board showing when the app was last closed, so it opens there again.
    board: str = "weather"
    # Move on to the next board by itself every so often.
    cycle_boards: bool = False
    cycle_seconds: int = 30

    # Stop the screensaver, screen blanking and lock while the board is open.
    keep_awake: bool = True
    # Open straight into full screen (e.g. for a Raspberry Pi information display).
    start_fullscreen: bool = False
    # The TV's own remote over HDMI-CEC.
    tv_remote: bool = True
    # "auto" picks "light" on a Raspberry Pi: the moving backgrounds are
    # drawn at lower resolution and frame rate, which a Pi can keep up with.
    graphics: str = "auto"


_CHOICES = {
    "location_mode": ("auto", "manual"),
    "temperature_unit": ("C", "F"),
    "wind_unit": ("mph", "kmh"),
    "graphics": ("auto", "full", "light"),
    "train_mode": ("departures", "arrivals", "both"),
}
_RANGES = {
    "cycle_seconds": (5, 3600),
}


class SettingsStore:
    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or Path(user_config_dir("Simple-Info")) / "settings.json"
        self.settings = Settings()
        self.load()

    def update(self, **changes) -> None:
        for name, value in changes.items():
            if not hasattr(self.settings, name):
                raise AttributeError(name)
            setattr(self.settings, name, value)
        self.save()

    def load(self) -> None:
        try:
            data = json.loads(self._config_path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        defaults = Settings()
        for f in fields(Settings):
            if f.name not in data:
                continue
            value, default = data[f.name], getattr(defaults, f.name)
            if isinstance(default, float) and isinstance(value, int) and not isinstance(value, bool):
                value = float(value)
            if type(value) is not type(default):
                continue
            if f.name in _CHOICES and value not in _CHOICES[f.name]:
                continue
            if f.name in _RANGES:
                low, high = _RANGES[f.name]
                value = max(low, min(high, value))
            setattr(self.settings, f.name, value)
        from simple_info.core.currency import CURRENCIES

        if self.settings.currency_base not in CURRENCIES:
            self.settings.currency_base = "GBP"
        codes = [c for c in self.settings.currency_codes.split(",") if c in CURRENCIES]
        self.settings.currency_codes = ",".join(dict.fromkeys(codes))
        for name in ("train_station_crs", "train_filter_crs"):
            code = getattr(self.settings, name)
            setattr(self.settings, name, code.upper() if len(code) == 3 and code.isalpha() else "")
        if self.settings.location_mode == "manual" and not self.settings.location_name:
            self.settings.location_mode = "auto"

    def save(self) -> None:
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(json.dumps(asdict(self.settings), indent=2))
        except OSError:
            pass
