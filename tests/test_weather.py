import json
from datetime import datetime, timezone
from unittest.mock import patch

from simple_info.core import weather as wx

PAYLOAD = {
    "utc_offset_seconds": 3600,
    "current": {
        "time": "2026-10-20T14:00",
        "temperature_2m": 9.4,
        "relative_humidity_2m": 88,
        "apparent_temperature": 6.1,
        "is_day": 1,
        "precipitation": 1.2,
        "weather_code": 63,
        "cloud_cover": 100,
        "wind_speed_10m": 22.0,
        "wind_direction_10m": 250,
        "wind_gusts_10m": 41.0,
    },
    "hourly": {
        "time": [f"2026-10-20T{h:02d}:00" for h in range(24)],
        "temperature_2m": [8.0 + h * 0.1 for h in range(24)],
        "precipitation_probability": [80] * 24,
        "weather_code": [63] * 24,
        "snow_depth": [0.0] * 14 + [0.05] + [0.0] * 9,
        "is_day": [0] * 7 + [1] * 11 + [0] * 6,
    },
    "daily": {
        "time": ["2026-10-20", "2026-10-21"],
        "weather_code": [63, 3],
        "temperature_2m_max": [11.0, 12.5],
        "temperature_2m_min": [6.0, None],
        "precipitation_probability_max": [90, 20],
        "sunrise": ["2026-10-20T07:42", "2026-10-21T07:44"],
        "sunset": ["2026-10-20T18:01", "2026-10-21T17:59"],
        "wind_speed_10m_max": [30.0, 18.0],
    },
}


def test_parse_forecast_reads_current_hourly_and_daily():
    f = wx.parse_forecast(PAYLOAD, "Keswick", fetched_at=100.0)
    assert f.location == "Keswick"
    assert f.temperature == 9.4
    assert f.condition == wx.RAIN
    assert f.description == "Rain"
    assert len(f.hourly) == 24 and f.hourly[7].is_day
    assert f.daily[1].temp_min == 0.0  # a missing value doesn't break parsing
    assert f.snow_depth == 0.05  # taken from the hour we're in


def test_local_now_and_upcoming_hours_use_the_locations_offset():
    f = wx.parse_forecast(PAYLOAD, "Keswick")
    utc = datetime(2026, 10, 20, 12, 30, tzinfo=timezone.utc)
    assert f.local_now(utc) == datetime(2026, 10, 20, 13, 30)
    hours = f.upcoming_hours(3, utc)
    assert [h.time for h in hours] == ["2026-10-20T13:00", "2026-10-20T14:00", "2026-10-20T15:00"]
    assert f.today(utc).date == "2026-10-20"


def test_scene_weather_for_rain_wind_and_snow():
    f = wx.parse_forecast(PAYLOAD, "Keswick")
    w = wx.scene_weather(f)
    assert w.rain > 0.5 and w.snow == 0 and w.clouds >= 0.85
    assert w.wind_from_west  # 250° is a west-south-westerly
    assert w.snow_on_ground  # 5 cm lying
    f.code, f.temperature, f.snow_depth = 75, -8.0, 0.0
    w = wx.scene_weather(f)
    assert w.snow == 1.0 and w.rain == 0 and w.snow_on_ground and w.frozen_lake


def test_scene_weather_without_a_forecast_is_a_gentle_default():
    w = wx.scene_weather(None)
    assert w.rain == 0 and w.snow == 0 and not w.thunder


def test_every_wmo_code_has_a_condition_and_description():
    for code in (0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99):
        assert wx.condition_for(code) in (wx.CLEAR, wx.PARTLY_CLOUDY, wx.CLOUDY, wx.FOG, wx.DRIZZLE, wx.RAIN, wx.SNOW, wx.THUNDER)
        assert wx.describe(code)


def test_forecast_cache_round_trips_and_expires(tmp_path):
    f = wx.parse_forecast(PAYLOAD, "Keswick", fetched_at=1000.0)
    path = tmp_path / "forecast.json"
    wx.save_forecast(f, path)
    back = wx.load_forecast(path, now=1000.0 + 3600)
    assert back == f
    assert wx.load_forecast(path, now=1000.0 + wx.MAX_CACHE_AGE_SECONDS + 1) is None
    path.write_text("not json")
    assert wx.load_forecast(path) is None


class _Response:
    def __init__(self, data):
        self._data = json.dumps(data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._data


def test_fetch_forecast_returns_none_when_offline():
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert wx.fetch_forecast(wx.Location("X", 1.0, 2.0)) is None


def test_fetch_forecast_parses_the_response():
    with patch("urllib.request.urlopen", return_value=_Response(PAYLOAD)):
        f = wx.fetch_forecast(wx.Location("Keswick", 54.6, -3.13))
    assert f is not None and f.location == "Keswick"


def test_locate_by_ip_and_search_places():
    with patch("urllib.request.urlopen", return_value=_Response({"success": True, "city": "Fochabers", "latitude": 57.6, "longitude": -3.1})):
        assert wx.locate_by_ip() == wx.Location("Fochabers", 57.6, -3.1)
    with patch("urllib.request.urlopen", return_value=_Response({"success": False})):
        assert wx.locate_by_ip() is None
    results = {"results": [{"name": "Keswick", "admin1": "England", "country": "United Kingdom", "latitude": 54.6, "longitude": -3.13}]}
    with patch("urllib.request.urlopen", return_value=_Response(results)):
        assert wx.search_places("Keswick") == [wx.Location("Keswick, England, United Kingdom", 54.6, -3.13)]
    assert wx.search_places("  ") == []


def test_display_helpers():
    assert wx.format_temp(10, "C") == "10°"
    assert wx.format_temp(10, "F") == "50°"
    assert wx.format_wind(16.09, "mph") == "10 mph"
    assert wx.format_wind(16.09, "kmh") == "16 km/h"
    assert wx.compass(250) == "W" and wx.compass(10) == "N" and wx.compass(135) == "SE"
