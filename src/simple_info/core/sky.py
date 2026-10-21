"""Where the sun is and how light it is, plus the moon's phase."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

TWILIGHT_MINUTES = 45
SYNODIC_MONTH_DAYS = 29.530588853
_KNOWN_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)


@dataclass
class Light:
    daylight: float  # 0 = full night, 1 = full day
    golden: float  # 0..1, how much dawn/dusk colour is in the sky
    sun_progress: float  # 0 at sunrise .. 1 at sunset (outside that: off-screen)
    night_progress: float  # 0 at sunset .. 1 at the next sunrise, for the moon's arc
    morning: bool  # golden light is dawn rather than dusk


def _minutes(dt: datetime) -> float:
    return dt.hour * 60 + dt.minute + dt.second / 60


def light_at(now: datetime, sunrise: Optional[datetime] = None, sunset: Optional[datetime] = None) -> Light:
    """now/sunrise/sunset are naive local times on the same day."""
    rise = _minutes(sunrise) if sunrise else 7 * 60
    set_ = _minutes(sunset) if sunset else 19 * 60
    if set_ <= rise:  # polar weirdness — fall back to a plain day
        rise, set_ = 7 * 60, 19 * 60
    m = _minutes(now)

    def ramp(x: float) -> float:  # 0..1 across the twilight band centred on the event
        return max(0.0, min(1.0, (x + TWILIGHT_MINUTES) / (2 * TWILIGHT_MINUTES)))

    up = ramp(m - rise)
    down = 1 - ramp(m - set_)
    daylight = _smooth(min(up, down))

    golden_width = 70
    golden = max(
        max(0.0, 1 - abs(m - rise) / golden_width),
        max(0.0, 1 - abs(m - set_) / golden_width),
    )
    morning = abs(m - rise) < abs(m - set_)

    day_len = set_ - rise
    sun_progress = (m - rise) / day_len
    night_len = 1440 - day_len
    since_set = (m - set_) % 1440
    night_progress = since_set / night_len if since_set <= night_len else -1.0
    return Light(daylight, _smooth(golden), sun_progress, night_progress, morning)


# Fixed lighting for the time-of-day preview (T key).
PREVIEW_LIGHTS = {
    "Dawn": Light(0.45, 1.0, 0.0, 1.0, True),
    "Day": Light(1.0, 0.0, 0.45, -1.0, False),
    "Dusk": Light(0.4, 1.0, 1.0, 0.0, False),
    "Night": Light(0.0, 0.0, -0.5, 0.45, False),
}


def _smooth(x: float) -> float:
    return x * x * (3 - 2 * x)


def moon_phase(now: Optional[datetime] = None) -> float:
    """0 = new, 0.25 = first quarter, 0.5 = full, 0.75 = last quarter."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.astimezone(timezone.utc)
    days = (now - _KNOWN_NEW_MOON).total_seconds() / 86400
    return (days / SYNODIC_MONTH_DAYS) % 1.0


def moon_illumination(phase: float) -> float:
    return (1 - math.cos(2 * math.pi * phase)) / 2
