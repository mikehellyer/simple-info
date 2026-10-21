"""Local weather from Open-Meteo (free, no API key), and where "local" is.

Everything that touches the network returns None on failure rather than
raising — the board carries on with the last known (or default) weather.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from simple_info.core.http import SSL_CONTEXT

TIMEOUT_SECONDS = 8
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
IP_LOCATION_URL = "https://ipwho.is/"

# Conditions the sky knows how to draw.
CLEAR, PARTLY_CLOUDY, CLOUDY, FOG, DRIZZLE, RAIN, SNOW, THUNDER = (
    "clear", "partly_cloudy", "cloudy", "fog", "drizzle", "rain", "snow", "thunder",
)

# WMO weather interpretation codes, as Open-Meteo reports them.
_WMO = {
    0: (CLEAR, "Clear sky"),
    1: (CLEAR, "Mainly clear"),
    2: (PARTLY_CLOUDY, "Partly cloudy"),
    3: (CLOUDY, "Overcast"),
    45: (FOG, "Fog"),
    48: (FOG, "Freezing fog"),
    51: (DRIZZLE, "Light drizzle"),
    53: (DRIZZLE, "Drizzle"),
    55: (DRIZZLE, "Heavy drizzle"),
    56: (DRIZZLE, "Freezing drizzle"),
    57: (DRIZZLE, "Heavy freezing drizzle"),
    61: (RAIN, "Light rain"),
    63: (RAIN, "Rain"),
    65: (RAIN, "Heavy rain"),
    66: (RAIN, "Freezing rain"),
    67: (RAIN, "Heavy freezing rain"),
    71: (SNOW, "Light snow"),
    73: (SNOW, "Snow"),
    75: (SNOW, "Heavy snow"),
    77: (SNOW, "Snow grains"),
    80: (RAIN, "Light showers"),
    81: (RAIN, "Showers"),
    82: (RAIN, "Violent showers"),
    85: (SNOW, "Snow showers"),
    86: (SNOW, "Heavy snow showers"),
    95: (THUNDER, "Thunderstorm"),
    96: (THUNDER, "Thunderstorm with hail"),
    99: (THUNDER, "Severe thunderstorm with hail"),
}

# How hard it's coming down, for codes that have a light/moderate/heavy scale.
_INTENSITY = {
    51: 0.3, 53: 0.45, 55: 0.6, 56: 0.35, 57: 0.6,
    61: 0.4, 63: 0.65, 65: 1.0, 66: 0.5, 67: 0.9,
    71: 0.35, 73: 0.65, 75: 1.0, 77: 0.3,
    80: 0.45, 81: 0.7, 82: 1.0, 85: 0.5, 86: 0.9,
    95: 0.85, 96: 0.9, 99: 1.0,
}


def condition_for(code: int) -> str:
    return _WMO.get(code, (CLOUDY, ""))[0]


def describe(code: int) -> str:
    return _WMO.get(code, (CLOUDY, "Unknown"))[1]


@dataclass
class Location:
    name: str
    latitude: float
    longitude: float


@dataclass
class Hour:
    time: str  # local ISO time at the location, e.g. "2026-10-20T14:00"
    temperature: float
    code: int
    precip_probability: int
    is_day: bool


@dataclass
class Day:
    date: str  # "2026-10-20"
    code: int
    temp_max: float
    temp_min: float
    precip_probability: int
    sunrise: str
    sunset: str
    wind_max: float


@dataclass
class Forecast:
    location: str
    utc_offset_seconds: int
    temperature: float
    apparent_temperature: float
    humidity: int
    wind_speed: float  # km/h
    wind_direction: int
    wind_gusts: float
    code: int
    is_day: bool
    cloud_cover: int
    precipitation: float
    snow_depth: float  # metres
    fetched_at: float  # unix time
    hourly: list[Hour] = field(default_factory=list)
    daily: list[Day] = field(default_factory=list)

    @property
    def condition(self) -> str:
        return condition_for(self.code)

    @property
    def description(self) -> str:
        return describe(self.code)

    def local_now(self, now: Optional[datetime] = None) -> datetime:
        """The current wall-clock time at the forecast's location (naive)."""
        now = now or datetime.now(timezone.utc)
        return (now.astimezone(timezone.utc) + timedelta(seconds=self.utc_offset_seconds)).replace(tzinfo=None)

    def upcoming_hours(self, count: int, now: Optional[datetime] = None) -> list[Hour]:
        current = self.local_now(now).replace(minute=0, second=0, microsecond=0)
        upcoming = [h for h in self.hourly if _parse_local(h.time) >= current]
        return upcoming[:count]

    def today(self, now: Optional[datetime] = None) -> Optional[Day]:
        date = self.local_now(now).date().isoformat()
        return next((d for d in self.daily if d.date == date), self.daily[0] if self.daily else None)


def _parse_local(text: str) -> datetime:
    return datetime.fromisoformat(text)


@dataclass
class SceneWeather:
    """What the sky should show, boiled down from a forecast."""

    condition: str = PARTLY_CLOUDY
    clouds: float = 0.35  # 0..1 sky cover
    rain: float = 0.0  # 0..1 intensity
    snow: float = 0.0  # 0..1 intensity
    fog: float = 0.0  # 0..1
    thunder: bool = False
    wind: float = 0.2  # 0..1, 1 ≈ a gale
    wind_from_west: bool = True  # rain/snow/smoke lean to the right
    snow_on_ground: bool = False
    frozen_lake: bool = False


def scene_weather(forecast: Optional[Forecast]) -> SceneWeather:
    if forecast is None:
        return SceneWeather()
    cond = forecast.condition
    intensity = _INTENSITY.get(forecast.code, 0.5)
    w = SceneWeather(condition=cond)
    w.clouds = max(0.0, min(1.0, forecast.cloud_cover / 100))
    if cond == CLEAR:
        w.clouds = min(w.clouds, 0.15)
    elif cond == PARTLY_CLOUDY:
        w.clouds = max(0.3, min(w.clouds, 0.6))
    elif cond in (CLOUDY, DRIZZLE, RAIN, SNOW, THUNDER):
        w.clouds = max(w.clouds, 0.85)
    if cond == FOG:
        w.fog, w.clouds = 0.85, max(w.clouds, 0.7)
    elif cond == DRIZZLE:
        w.rain = 0.25 + intensity * 0.3
    elif cond == RAIN:
        w.rain = intensity
    elif cond == THUNDER:
        w.rain, w.thunder = max(0.8, intensity), True
    elif cond == SNOW:
        w.snow = intensity
    w.wind = max(0.0, min(1.0, forecast.wind_speed / 55))
    # Meteorological direction is where the wind comes *from*: from the
    # west (180..360°) blows things left-to-right on screen.
    w.wind_from_west = 180 <= forecast.wind_direction % 360 <= 360
    w.snow_on_ground = forecast.snow_depth >= 0.01 or (cond == SNOW and forecast.temperature <= 1.5)
    w.frozen_lake = forecast.temperature <= -6
    return w


# Fixed looks for the weather preview (P key), so every style can be seen
# without waiting for the real weather to change.
PREVIEWS = {
    "Clear": SceneWeather(CLEAR, clouds=0.05, wind=0.1),
    "Partly cloudy": SceneWeather(PARTLY_CLOUDY, clouds=0.45, wind=0.25),
    "Overcast": SceneWeather(CLOUDY, clouds=0.95, wind=0.35),
    "Fog": SceneWeather(FOG, clouds=0.75, fog=0.85, wind=0.05),
    "Drizzle": SceneWeather(DRIZZLE, clouds=0.9, rain=0.35, wind=0.25),
    "Rain": SceneWeather(RAIN, clouds=1.0, rain=0.75, wind=0.45),
    "Thunderstorm": SceneWeather(THUNDER, clouds=1.0, rain=1.0, thunder=True, wind=0.8),
    "Snow": SceneWeather(SNOW, clouds=0.95, snow=0.7, wind=0.25, snow_on_ground=True),
}


def parse_forecast(payload: dict, location_name: str, fetched_at: Optional[float] = None) -> Forecast:
    cur = payload["current"]
    hourly_raw = payload.get("hourly", {})
    daily_raw = payload.get("daily", {})

    hours = []
    for i, t in enumerate(hourly_raw.get("time", [])):
        hours.append(
            Hour(
                time=t,
                temperature=_num(hourly_raw.get("temperature_2m"), i),
                code=int(_num(hourly_raw.get("weather_code"), i)),
                precip_probability=int(_num(hourly_raw.get("precipitation_probability"), i)),
                is_day=bool(_num(hourly_raw.get("is_day"), i, 1)),
            )
        )
    days = []
    for i, d in enumerate(daily_raw.get("time", [])):
        days.append(
            Day(
                date=d,
                code=int(_num(daily_raw.get("weather_code"), i)),
                temp_max=_num(daily_raw.get("temperature_2m_max"), i),
                temp_min=_num(daily_raw.get("temperature_2m_min"), i),
                precip_probability=int(_num(daily_raw.get("precipitation_probability_max"), i)),
                sunrise=_str(daily_raw.get("sunrise"), i),
                sunset=_str(daily_raw.get("sunset"), i),
                wind_max=_num(daily_raw.get("wind_speed_10m_max"), i),
            )
        )

    # Snow depth only comes hourly; take the hour we're in.
    snow_depth = 0.0
    current_hour = (cur.get("time") or "")[:13]
    for i, t in enumerate(hourly_raw.get("time", [])):
        if t[:13] == current_hour:
            snow_depth = _num(hourly_raw.get("snow_depth"), i)
            break

    return Forecast(
        location=location_name,
        utc_offset_seconds=int(payload.get("utc_offset_seconds", 0)),
        temperature=float(cur.get("temperature_2m") or 0.0),
        apparent_temperature=float(cur.get("apparent_temperature") or 0.0),
        humidity=int(cur.get("relative_humidity_2m") or 0),
        wind_speed=float(cur.get("wind_speed_10m") or 0.0),
        wind_direction=int(cur.get("wind_direction_10m") or 0),
        wind_gusts=float(cur.get("wind_gusts_10m") or 0.0),
        code=int(cur.get("weather_code") or 0),
        is_day=bool(cur.get("is_day", 1)),
        cloud_cover=int(cur.get("cloud_cover") or 0),
        precipitation=float(cur.get("precipitation") or 0.0),
        snow_depth=snow_depth,
        fetched_at=fetched_at if fetched_at is not None else time.time(),
        hourly=hours,
        daily=days,
    )


def _num(values, i, default=0.0) -> float:
    try:
        v = values[i]
    except (TypeError, IndexError):
        return default
    return default if v is None else float(v)


def _str(values, i) -> str:
    try:
        return str(values[i] or "")
    except (TypeError, IndexError):
        return ""


def _get_json(url: str) -> Optional[dict]:
    request = urllib.request.Request(url, headers={"User-Agent": "Simple-Info/1"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=SSL_CONTEXT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def fetch_forecast(location: Location) -> Optional[Forecast]:
    params = {
        "latitude": f"{location.latitude:.4f}",
        "longitude": f"{location.longitude:.4f}",
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,"
        "weather_code,cloud_cover,wind_speed_10m,wind_direction_10m,wind_gusts_10m",
        "hourly": "temperature_2m,precipitation_probability,weather_code,snow_depth,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
        "sunrise,sunset,wind_speed_10m_max",
        "timezone": "auto",
        "forecast_days": "7",
    }
    data = _get_json(f"{FORECAST_URL}?{urllib.parse.urlencode(params)}")
    if not data or "current" not in data:
        return None
    try:
        return parse_forecast(data, location.name)
    except (KeyError, TypeError, ValueError):
        return None


def locate_by_ip() -> Optional[Location]:
    """A rough location from this machine's public IP address."""
    data = _get_json(IP_LOCATION_URL)
    if not data or not data.get("success", True):
        return None
    try:
        return Location(
            name=data.get("city") or data.get("region") or "Here",
            latitude=float(data["latitude"]),
            longitude=float(data["longitude"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def search_places(query: str, count: int = 8) -> list[Location]:
    """Places matching a name, best first, labelled 'Town, Region, Country'."""
    query = query.strip()
    if not query:
        return []
    params = {"name": query, "count": str(count), "language": "en", "format": "json"}
    data = _get_json(f"{GEOCODE_URL}?{urllib.parse.urlencode(params)}")
    places = []
    for r in (data or {}).get("results", []) or []:
        try:
            label = ", ".join(p for p in (r.get("name"), r.get("admin1"), r.get("country")) if p)
            places.append(Location(label, float(r["latitude"]), float(r["longitude"])))
        except (KeyError, TypeError, ValueError):
            continue
    return places


# --- remembering the last forecast, so a restart while offline still has weather

MAX_CACHE_AGE_SECONDS = 12 * 3600


def save_forecast(forecast: Forecast, path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(forecast)))
    except OSError:
        pass


def load_forecast(path: Path, now: Optional[float] = None) -> Optional[Forecast]:
    try:
        data = json.loads(path.read_text())
        data["hourly"] = [Hour(**h) for h in data.get("hourly", [])]
        data["daily"] = [Day(**d) for d in data.get("daily", [])]
        forecast = Forecast(**data)
    except (OSError, ValueError, TypeError):
        return None
    if (now if now is not None else time.time()) - forecast.fetched_at > MAX_CACHE_AGE_SECONDS:
        return None
    return forecast


# --- display helpers

def format_temp(celsius: float, unit: str) -> str:
    value = celsius * 9 / 5 + 32 if unit == "F" else celsius
    return f"{round(value):d}°"


def format_wind(kmh: float, unit: str) -> str:
    if unit == "mph":
        return f"{round(kmh / 1.609):d} mph"
    return f"{round(kmh):d} km/h"


def compass(degrees: float) -> str:
    points = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return points[int((degrees % 360) / 45 + 0.5) % 8]
