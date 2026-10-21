"""The weather board: a big clock with the local forecast beside it, over
the sky as it really is outside."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QFontMetricsF, QPainter, QPainterPath, QPen

from simple_info.core import sky
from simple_info.core import weather as wx
from simple_info.core.settings import Settings
from simple_info.gui.boards.base import Board
from simple_info.gui.boards.weather_icons import draw_icon
from simple_info.gui.boards.weather_sky import WeatherSky
from simple_info.gui.paint import W, radial, rgb

WHITE = rgb(255, 255, 255)
DIM = rgb(255, 255, 255, 170)
FAINT = rgb(255, 255, 255, 110)
RAIN_BLUE = rgb(130, 196, 255)
CONDITIONS_REFRESH_SECONDS = 20  # how often the sky catches up with the time of day


def font(px: float, weight=QFont.Normal) -> QFont:
    f = QFont()
    f.setPixelSize(max(1, int(px)))
    f.setWeight(weight)
    return f


class WeatherBoard(Board):
    key = "weather"
    title = "Weather"
    accent = rgb(110, 180, 255)
    refresh_seconds = 15 * 60

    def __init__(self, cache_dir: Path):
        super().__init__()
        self.sky = WeatherSky()
        self._forecast_path = cache_dir / "forecast.json"
        self.forecast: Optional[wx.Forecast] = wx.load_forecast(self._forecast_path)
        self.status = "" if self.forecast else "Fetching the weather…"
        self._location: Optional[wx.Location] = None  # found from the IP address, kept between fetches
        self._place: Optional[wx.Location] = None  # chosen in Settings
        self.temperature_unit = "C"
        self.wind_unit = "mph"
        self.clock_24h = True
        self.weather_preview: Optional[str] = None  # a name from wx.PREVIEWS, or None for the real weather
        self.time_preview: Optional[str] = None  # a name from sky.PREVIEW_LIGHTS, or None for the real time
        self._since_conditions = CONDITIONS_REFRESH_SECONDS
        self.refresh_conditions()

    # --- settings and data

    def configure(self, settings: Settings) -> None:
        self.temperature_unit, self.wind_unit, self.clock_24h = settings.temperature_unit, settings.wind_unit, settings.clock_24h
        place = wx.Location(settings.location_name, settings.latitude, settings.longitude) if settings.location_mode == "manual" else None
        if place != self._place:
            first = self._place is None and place is None
            self._place = place
            if not first:
                self._location = None
                self.status = "Fetching the weather…"
                self.fetch_now()
        self.dirty = True

    def fetch_job(self):
        known = self._place or self._location

        def job():
            location = known or wx.locate_by_ip()
            if location is None:
                return None, None
            return location, wx.fetch_forecast(location)

        return job

    def on_fetched(self, result) -> bool:
        location, forecast = result or (None, None)
        if location is not None and self._place is None:
            self._location = location
        if forecast is not None:
            self.forecast = forecast
            self.status = ""
            wx.save_forecast(forecast, self._forecast_path)
        elif self.forecast is not None:
            self.status = "offline — showing the last forecast"
        elif location is None:
            self.status = "Couldn't work out where you are — choose a place in Settings (S)"
        else:
            self.status = "Weather unavailable — check your connection (retrying)"
        self.refresh_conditions()
        return forecast is not None

    # --- the sky behind

    def refresh_conditions(self) -> None:
        f = self.forecast
        weather = wx.PREVIEWS[self.weather_preview] if self.weather_preview else wx.scene_weather(f)
        if self.time_preview:
            light = sky.PREVIEW_LIGHTS[self.time_preview]
        else:
            now, rise, set_ = datetime.now(), None, None
            if f is not None:
                now = f.local_now()
                today = f.today()
                if today and today.sunrise and today.sunset:
                    rise, set_ = datetime.fromisoformat(today.sunrise), datetime.fromisoformat(today.sunset)
            light = sky.light_at(now, rise, set_)
        self.sky.set_conditions(weather, light, sky.moon_phase())
        self._since_conditions = 0.0

    def cycle_weather_preview(self) -> str:
        names = [None, *wx.PREVIEWS]
        self.weather_preview = names[(names.index(self.weather_preview) + 1) % len(names)]
        self.refresh_conditions()
        return f"Weather preview: {self.weather_preview}  (P for the next)" if self.weather_preview else "Live weather"

    def cycle_time_preview(self) -> str:
        names = [None, *sky.PREVIEW_LIGHTS]
        self.time_preview = names[(names.index(self.time_preview) + 1) % len(names)]
        self.refresh_conditions()
        return f"Time-of-day preview: {self.time_preview}  (T for the next)" if self.time_preview else "Live time of day"

    # --- drawing

    def step(self, dt: float) -> None:
        self._since_conditions += dt
        if self._since_conditions >= CONDITIONS_REFRESH_SECONDS:
            self.refresh_conditions()
        self.sky.step(dt)

    def paint_background(self, p: QPainter, target: QRectF) -> None:
        self.sky.paint(p, target)

    def paint_content(self, p: QPainter, now: datetime) -> None:
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        self._paint_clock(p, now)
        f = self.forecast
        if f is None:
            p.setFont(font(34))
            p.setPen(DIM)
            p.drawText(QRectF(0, 520, W, 80), Qt.AlignCenter, self.status)
            return
        self._paint_header(p, f)
        self._paint_current(p, f)
        self._paint_hours(p, f)
        self._paint_days(p, f)

    def _paint_clock(self, p: QPainter, now: datetime) -> None:
        if self.clock_24h:
            main, suffix = now.strftime("%H:%M"), ""
        else:
            main, suffix = f"{now.hour % 12 or 12}:{now.minute:02d}", ("AM" if now.hour < 12 else "PM")
        big = font(250, QFont.Light)
        secs = font(80, QFont.Light)
        fm, sm = QFontMetricsF(big), QFontMetricsF(secs)
        seconds = f":{now.second:02d}"
        width = fm.horizontalAdvance(main) + sm.horizontalAdvance(seconds) + 10
        left = 470 - width / 2
        baseline = 300
        p.setPen(WHITE)
        p.setFont(big)
        p.drawText(QPointF(left, baseline), main)
        p.setFont(secs)
        p.setPen(DIM)
        x = left + fm.horizontalAdvance(main) + 10
        p.drawText(QPointF(x, baseline), seconds)
        if suffix:
            p.drawText(QPointF(x, baseline - fm.capHeight() + sm.capHeight()), suffix)
        p.setFont(font(46))
        p.setPen(WHITE)
        p.drawText(QRectF(40, baseline + 20, 860, 60), Qt.AlignCenter, f"{now:%A} {now.day} {now:%B}")

    def _paint_header(self, p: QPainter, f: wx.Forecast) -> None:
        # a little map pin, then the place
        pin = QPainterPath()
        pin.moveTo(60, 70)
        pin.cubicTo(46, 52, 46, 36, 60, 34)
        pin.cubicTo(74, 36, 74, 52, 60, 70)
        p.setPen(Qt.NoPen)
        p.setBrush(rgb(255, 110, 90))
        p.drawPath(pin)
        p.setBrush(WHITE)
        p.drawEllipse(QPointF(60, 46), 4, 4)
        p.setFont(font(30, QFont.DemiBold))
        p.setPen(WHITE)
        p.drawText(QRectF(82, 30, 820, 44), Qt.AlignLeft | Qt.AlignVCenter, f.location or "Here")
        updated = datetime.fromtimestamp(f.fetched_at).strftime("%H:%M" if self.clock_24h else "%I:%M %p").lstrip("0")
        p.setFont(font(18))
        p.setPen(FAINT)
        p.drawText(QRectF(82, 70, 820, 26), Qt.AlignLeft | Qt.AlignVCenter, f"Updated {updated}" + (f" · {self.status}" if self.status else ""))

    def _card(self, p: QPainter, rect: QRectF) -> None:
        p.setPen(QPen(rgb(255, 255, 255, 40), 1))
        p.setBrush(rgb(255, 255, 255, 22))
        p.drawRoundedRect(rect, 22, 22)

    def _paint_current(self, p: QPainter, f: wx.Forecast) -> None:
        card = QRectF(950, 40, 600, 400)
        self._card(p, card)
        if f.is_day and f.condition in (wx.CLEAR, wx.PARTLY_CLOUDY):
            p.setPen(Qt.NoPen)
            p.setBrush(radial(1060, 160, 140, (0, rgb(255, 210, 90, 60)), (1, rgb(255, 210, 90, 0))))
            p.drawEllipse(QPointF(1060, 160), 140, 140)
        draw_icon(p, QPointF(1070, 160), 170, f.code, f.is_day)
        p.setPen(WHITE)
        p.setFont(font(130, QFont.Light))
        p.drawText(QRectF(1170, 70, 360, 170), Qt.AlignRight | Qt.AlignVCenter, wx.format_temp(f.temperature, self.temperature_unit))
        p.setFont(font(38, QFont.DemiBold))
        p.drawText(QRectF(980, 250, 540, 50), Qt.AlignLeft | Qt.AlignVCenter, f.description)

        today = f.today(None)
        rows = [
            ("Feels like", wx.format_temp(f.apparent_temperature, self.temperature_unit)),
            ("Wind", f"{wx.format_wind(f.wind_speed, self.wind_unit)} {wx.compass(f.wind_direction)}"
                     + (f", gusts {wx.format_wind(f.wind_gusts, self.wind_unit)}" if f.wind_gusts > f.wind_speed * 1.3 else "")),
            ("Humidity", f"{f.humidity}%"),
        ]
        if today and today.sunrise and today.sunset:
            fmt = "%H:%M" if self.clock_24h else "%I:%M %p"
            rise = datetime.fromisoformat(today.sunrise).strftime(fmt).lstrip("0")
            set_ = datetime.fromisoformat(today.sunset).strftime(fmt).lstrip("0")
            rows.append(("Sun", f"up {rise} · down {set_}"))
        p.setFont(font(24))
        for i, (label, value) in enumerate(rows):
            y = 308 + i * 32
            p.setPen(DIM)
            p.drawText(QRectF(980, y, 160, 30), Qt.AlignLeft | Qt.AlignVCenter, label)
            p.setPen(WHITE)
            p.drawText(QRectF(1130, y, 400, 30), Qt.AlignLeft | Qt.AlignVCenter, value)

    def _paint_hours(self, p: QPainter, f: wx.Forecast) -> None:
        hours = f.upcoming_hours(12)
        card = QRectF(50, 470, 1500, 170)
        self._card(p, card)
        if not hours:
            return
        col = card.width() / len(hours)
        for i, h in enumerate(hours):
            x = card.left() + col * i
            t = datetime.fromisoformat(h.time)
            label = "Now" if i == 0 else (t.strftime("%H:%M") if self.clock_24h else (f"{t.hour % 12 or 12}{'am' if t.hour < 12 else 'pm'}"))
            p.setFont(font(20, QFont.DemiBold if i == 0 else QFont.Normal))
            p.setPen(WHITE if i == 0 else DIM)
            p.drawText(QRectF(x, card.top() + 10, col, 28), Qt.AlignCenter, label)
            draw_icon(p, QPointF(x + col / 2, card.top() + 72), 58, h.code, h.is_day)
            p.setFont(font(26))
            p.setPen(WHITE)
            p.drawText(QRectF(x, card.top() + 104, col, 32), Qt.AlignCenter, wx.format_temp(h.temperature, self.temperature_unit))
            if h.precip_probability >= 10:
                p.setFont(font(17))
                p.setPen(RAIN_BLUE)
                p.drawText(QRectF(x, card.top() + 134, col, 24), Qt.AlignCenter, f"{h.precip_probability}%")

    def _paint_days(self, p: QPainter, f: wx.Forecast) -> None:
        days = f.daily[:7]
        card = QRectF(50, 660, 1500, 190)
        self._card(p, card)
        if not days:
            return
        lo = min(d.temp_min for d in days)
        hi = max(d.temp_max for d in days)
        span = max(1.0, hi - lo)
        today = f.local_now().date().isoformat()
        col = card.width() / len(days)
        for i, d in enumerate(days):
            x = card.left() + col * i
            date = datetime.fromisoformat(d.date)
            label = "Today" if d.date == today else date.strftime("%a")
            p.setFont(font(22, QFont.DemiBold if d.date == today else QFont.Normal))
            p.setPen(WHITE)
            p.drawText(QRectF(x, card.top() + 10, col, 30), Qt.AlignCenter, label)
            draw_icon(p, QPointF(x + col / 2, card.top() + 78), 64, d.code, True)
            # high / low, with a little range bar
            p.setFont(font(24))
            p.drawText(QRectF(x, card.top() + 116, col / 2 - 6, 30), Qt.AlignRight | Qt.AlignVCenter, wx.format_temp(d.temp_max, self.temperature_unit))
            p.setPen(DIM)
            p.drawText(QRectF(x + col / 2 + 6, card.top() + 116, col / 2, 30), Qt.AlignLeft | Qt.AlignVCenter, wx.format_temp(d.temp_min, self.temperature_unit))
            bar = QRectF(x + 30, card.top() + 154, col - 60, 6)
            p.setPen(Qt.NoPen)
            p.setBrush(rgb(255, 255, 255, 40))
            p.drawRoundedRect(bar, 3, 3)
            a = bar.left() + bar.width() * (d.temp_min - lo) / span
            b = bar.left() + bar.width() * (d.temp_max - lo) / span
            p.setBrush(rgb(255, 196, 90))
            p.drawRoundedRect(QRectF(a, bar.top(), max(6, b - a), bar.height()), 3, 3)
            if d.precip_probability >= 10:
                p.setFont(font(17))
                p.setPen(RAIN_BLUE)
                p.drawText(QRectF(x, card.top() + 162, col, 24), Qt.AlignCenter, f"{d.precip_probability}%")
