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
    # Your own Rail Data Marketplace key (raildata.org.uk), for departures
    # straight from National Rail. Kept only here, sent only to National Rail.
    rail_key: str = ""

    # The currency board: what one of `currency_base` buys in each of
    # `currency_codes` (comma-separated, shown in that order), and whether
    # Bitcoin and Ethereum join in.
    currency_base: str = "GBP"
    currency_codes: str = "EUR,USD,CAD,AUD,JPY,CHF,NZD,SEK,NOK"
    currency_crypto: bool = True

    # The sport board: the competitions followed (ESPN keys, comma-separated,
    # one page each in this order), and how long each page stays up.
    sport_competitions: str = "soccer/eng.1,soccer/sco.1,baseball/mlb,cricket/international,rugby/180659,rugby/267979,rugby/270557"
    # A favourite team for each competition, to pick out on its page:
    # "soccer/sco.1=257,cricket/international=Scotland" (ESPN team ids;
    # cricket's national sides by name).
    sport_favourites: str = ""

    # The TV board: the channels on it (ids from the Freeview guide,
    # comma-separated, in this order).
    tv_channels: str = "BBCOneScotHD.uk,BBCTwoHD.uk,STVNorth.uk,Channel4Scotland.uk,5.uk,BBCScotland.uk,BBCFourHD.uk,ITV2.uk,E4.uk,More4.uk,Film4.uk,BBCNews.uk"

    # The news board: the feeds followed (keys from core.news, comma-separated,
    # one page each in this order).
    news_feeds: str = "bbc/top,bbc/scotland,bbc/ne-scotland,bbc/world"

    # The radio board: the stations on it (ids from the Freeview guide,
    # comma-separated, in this order).
    radio_channels: str = "BBCRScotland.uk,BBCR1.uk,BBCR2.uk,BBCR3.uk,BBCR4FM.uk,BBCR5L.uk,BBCR6M.uk,ClassicFM.uk"

    # The board showing when the app was last closed, so it opens there again.
    board: str = "weather"
    # Move on to the next board by itself every so often.
    cycle_boards: bool = False
    cycle_seconds: int = 30
    # Paused (H, or the remote's play/pause): stay on this board and page.
    paused: bool = False
    board_page: int = 0  # the page the board was on, to come back to
    # How long each page stays up on boards with more than one (sport, TV).
    page_seconds: int = 20

    # Stop the screensaver, screen blanking and lock while the board is open.
    keep_awake: bool = True
    # Open straight into full screen (e.g. for a Raspberry Pi information display).
    start_fullscreen: bool = False
    # The TV's own remote over HDMI-CEC.
    tv_remote: bool = True
    # The phone remote: a web page for phones on the home network.
    phone_remote: bool = False
    remote_port: int = 8765
    remote_pin: str = ""
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
    "page_seconds": (5, 600),
    "remote_port": (1024, 65535),
    "board_page": (0, 99),
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
        from simple_info.core.sports import BY_KEY, format_favourites, parse_favourites

        self.settings.sport_favourites = format_favourites(parse_favourites(self.settings.sport_favourites))

        keys = [k for k in self.settings.sport_competitions.split(",") if k in BY_KEY]
        self.settings.sport_competitions = ",".join(dict.fromkeys(keys))
        from simple_info.core.news import BY_KEY as NEWS_FEEDS

        feeds = [k for k in self.settings.news_feeds.split(",") if k in NEWS_FEEDS]
        self.settings.news_feeds = ",".join(dict.fromkeys(feeds))
        for name in ("train_station_crs", "train_filter_crs"):
            code = getattr(self.settings, name)
            setattr(self.settings, name, code.upper() if len(code) == 3 and code.isalpha() else "")
        if not (self.settings.remote_pin.isdigit() and len(self.settings.remote_pin) <= 8):
            self.settings.remote_pin = ""
        if self.settings.location_mode == "manual" and not self.settings.location_name:
            self.settings.location_mode = "auto"

    def save(self) -> None:
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(json.dumps(asdict(self.settings), indent=2))
        except OSError:
            pass
