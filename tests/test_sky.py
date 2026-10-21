from datetime import datetime, timezone

from simple_info.core import sky


def at(h, m=0):
    return datetime(2026, 10, 20, h, m)


def test_daylight_through_the_day():
    rise, set_ = at(7, 30), at(18, 0)
    assert sky.light_at(at(2), rise, set_).daylight == 0
    assert sky.light_at(at(12), rise, set_).daylight == 1
    dawn = sky.light_at(at(7, 30), rise, set_)
    assert 0.3 < dawn.daylight < 0.7 and dawn.golden > 0.9 and dawn.morning
    dusk = sky.light_at(at(18, 0), rise, set_)
    assert dusk.golden > 0.9 and not dusk.morning


def test_sun_and_moon_progress():
    rise, set_ = at(7), at(19)
    assert abs(sky.light_at(at(13), rise, set_).sun_progress - 0.5) < 1e-9
    night = sky.light_at(at(1), rise, set_)
    assert 0 < night.night_progress < 1
    assert sky.light_at(at(12), rise, set_).night_progress == -1.0


def test_defaults_without_sunrise_and_sunset():
    assert sky.light_at(at(12)).daylight == 1
    assert sky.light_at(at(23)).daylight == 0


def test_moon_phase_on_known_dates():
    # Full moon 2026-10-26 04:12 UTC, new moon 2026-10-10 15:50 UTC
    assert abs(sky.moon_phase(datetime(2026, 10, 26, 4, 12, tzinfo=timezone.utc)) - 0.5) < 0.03
    phase = sky.moon_phase(datetime(2026, 10, 10, 15, 50, tzinfo=timezone.utc))
    assert min(phase, 1 - phase) < 0.03
    assert sky.moon_illumination(0.5) == 1.0
