"""The weather board's background: the sky as it really is outside.

The colour follows the time of day (dawn and dusk glow, stars and the moon
at night) and the weather drifts across it — clouds, rain, snow, fog and
lightning — so the kind of day it is shows before a word is read. Drawn on
the 1600×900 virtual canvas, stretched to fill the window.
"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen

from simple_info.core.sky import Light
from simple_info.core.weather import SceneWeather
from simple_info.gui.paint import H, W, alpha, mix, radial, rgb, scaled, soft_blob, vgrad

SUN_ARC_BOTTOM = 980.0  # the sun and moon rise and set below the bottom edge
SUN_ARC_HEIGHT = 920.0  # …and at their highest, are just below the top edge


class WeatherSky:
    def __init__(self):
        self.weather = SceneWeather()
        self.light = Light(1.0, 0.0, 0.5, -1.0, False)
        self.moon_phase = 0.3
        self.t = 0.0
        self._rng = random.Random(1)
        self._cloud_sprites: list[QImage] = []
        self._cloud_key = None
        self._clouds: list[list[float]] = []
        self._rain: list[list[float]] = []
        self._snow: list[list[float]] = []
        self._fog_sprite = soft_blob(256, rgb(255, 255, 255, 255))
        self._flash = 0.0  # seconds left of the current lightning flash
        self._bolt: list[tuple[float, float]] = []
        self._next_flash = 6.0
        self._stars = [(self._rng.uniform(0, W), self._rng.uniform(0, H * 0.8), self._rng.uniform(0.6, 2.0)) for _ in range(220)]

    def set_conditions(self, weather: SceneWeather, light: Light, moon_phase: float) -> None:
        self.weather, self.light, self.moon_phase = weather, light, moon_phase

    @property
    def lightning(self) -> float:
        """0..1 brightness of a lightning flash right now."""
        if self._flash <= 0:
            return 0.0
        k = 1 - self._flash / 0.45
        return max(0.0, math.sin(k * math.pi * 3) * (1 - k)) if k < 1 else 0.0

    def colours(self) -> tuple[QColor, QColor]:
        """The sky's colour at the top and the bottom of the window."""
        l, w = self.light, self.weather
        top = mix(rgb(6, 10, 28), rgb(52, 112, 192), l.daylight)
        bottom = mix(rgb(22, 32, 62), rgb(150, 192, 230), l.daylight)
        if l.golden > 0:
            g = l.golden * (1 - w.clouds * 0.55)
            top = mix(top, rgb(70, 72, 140), g * 0.5)
            bottom = mix(bottom, rgb(250, 150, 92) if not l.morning else rgb(252, 176, 120), g * 0.85)
        if w.clouds > 0.5:
            k = (w.clouds - 0.5) * 2
            dull = mix(rgb(20, 22, 30), rgb(150, 158, 170), l.daylight)
            top = mix(top, scaled(dull, 0.85 - w.rain * 0.25), k * 0.85)
            bottom = mix(bottom, scaled(dull, 1.1 - w.rain * 0.2), k * 0.75)
        return top, bottom

    # --- animation

    def step(self, dt: float) -> None:
        self.t += dt
        w = self.weather
        drift = 1 if w.wind_from_west else -1
        rng = self._rng

        want = int(2 + w.clouds * 13)
        while len(self._clouds) < want:
            self._clouds.append(self._new_cloud(anywhere=True))
        del self._clouds[want:]
        speed = 6 + w.wind * 45
        for c in self._clouds:
            c[0] += drift * speed * c[3] * dt
            if (drift > 0 and c[0] > W + 250) or (drift < 0 and c[0] < -650):
                c[:] = self._new_cloud(anywhere=False)

        want = int(w.rain * 420)
        while len(self._rain) < want:
            self._rain.append(self._new_drop(anywhere=True))
        del self._rain[want:]
        lean = drift * (60 + w.wind * 420)
        for d in self._rain:
            d[0] += lean * dt
            d[1] += d[2] * dt
            if d[1] > H + 30 or d[0] < -50 or d[0] > W + 50:
                d[:] = self._new_drop(anywhere=False)

        want = int(w.snow * 360)
        while len(self._snow) < want:
            self._snow.append(self._new_flake(anywhere=True))
        del self._snow[want:]
        for f in self._snow:
            f[0] += (drift * (12 + w.wind * 140) + math.sin(self.t * 1.3 + f[4]) * 18) * dt
            f[1] += f[2] * dt
            if f[1] > H + 10 or f[0] < -30 or f[0] > W + 30:
                f[:] = self._new_flake(anywhere=False)

        if self._flash > 0:
            self._flash -= dt
        if w.thunder:
            self._next_flash -= dt
            if self._next_flash <= 0:
                self._next_flash = rng.uniform(7, 22)
                self._flash = 0.45
                self._bolt = self._make_bolt()

    def _new_cloud(self, anywhere: bool) -> list[float]:
        rng = self._rng
        drift = 1 if self.weather.wind_from_west else -1
        x = rng.uniform(-400, W) if anywhere else (-600 if drift > 0 else W + 200)
        # x, y, scale, speed factor, sprite index
        return [x, rng.uniform(-60, 620), rng.uniform(0.7, 1.7), rng.uniform(0.6, 1.3), rng.randrange(4)]

    def _new_drop(self, anywhere: bool) -> list[float]:
        rng = self._rng
        x = rng.uniform(-200, W + 200)
        y = rng.uniform(-50, H) if anywhere else rng.uniform(-80, -10)
        # x, y, speed, length
        return [x, y, rng.uniform(800, 1150), rng.uniform(14, 28)]

    def _new_flake(self, anywhere: bool) -> list[float]:
        rng = self._rng
        x = rng.uniform(-60, W + 60)
        y = rng.uniform(-20, H) if anywhere else rng.uniform(-40, -5)
        size = rng.uniform(1.4, 4.2)
        # x, y, speed (bigger = nearer = faster), size, phase
        return [x, y, 22 + size * 14, size, rng.uniform(0, 6.3)]

    def _make_bolt(self) -> list[tuple[float, float]]:
        rng = self._rng
        x, y = rng.uniform(150, 1450), 20.0
        pts = [(x, y)]
        while y < 640:
            y += rng.uniform(25, 60)
            x += rng.uniform(-45, 45)
            pts.append((x, y))
        return pts

    # --- painting

    def paint(self, p: QPainter, target: QRectF) -> None:
        p.save()
        p.translate(target.topLeft())
        p.scale(target.width() / W, target.height() / H)  # stretched to fill: it's only sky
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        self._paint_sky(p)
        self._paint_clouds(p)
        if self._flash > 0 and self._bolt:
            self._paint_bolt(p)
        self._paint_precipitation(p)
        self._paint_fog(p)
        k = self.lightning
        if k > 0:
            p.fillRect(QRectF(0, 0, W, H), rgb(220, 226, 255, 110 * k))
        # A veil, darker towards the bottom where the forecast cards sit, so
        # the words stay easy to read in any weather.
        p.fillRect(QRectF(0, 0, W, H), vgrad(0, H, (0, rgb(0, 0, 0, 30)), (0.45, rgb(0, 0, 0, 75)), (1, rgb(0, 0, 0, 140))))
        p.restore()

    def _paint_sky(self, p: QPainter) -> None:
        l, w = self.light, self.weather
        top, bottom = self.colours()
        p.fillRect(QRectF(0, 0, W, H), vgrad(0, H, top, bottom))

        visible = 1 - w.clouds
        if l.daylight < 0.6 and visible > 0.05:
            p.setPen(Qt.NoPen)
            k = (0.6 - l.daylight) / 0.6 * visible
            for x, y, s in self._stars:
                twinkle = 0.5 + 0.5 * math.sin(x * 3.1 + self.t * (0.6 + s * 0.4))
                p.setBrush(rgb(255, 255, 240, 220 * k * (0.35 + 0.65 * twinkle)))
                p.drawEllipse(QPointF(x, y), s * 0.8, s * 0.8)

        def arc(progress: float) -> QPointF:
            return QPointF(100 + progress * 1400, SUN_ARC_BOTTOM - math.sin(progress * math.pi) * SUN_ARC_HEIGHT)

        if 0 <= l.sun_progress <= 1 and w.clouds < 0.9:
            c = arc(l.sun_progress)
            glare = (1 - w.clouds * 0.9) ** 1.2
            sun = mix(rgb(255, 222, 120), rgb(255, 150, 70), l.golden)
            p.setPen(Qt.NoPen)
            # the glare brightens the sky around it, rather than painting over it
            p.setCompositionMode(QPainter.CompositionMode_Screen)
            p.setBrush(radial(c.x(), c.y(), 320, (0, alpha(sun, 230 * glare)), (0.15, alpha(sun, 120 * glare)),
                              (0.45, alpha(sun, 35 * glare)), (1, alpha(sun, 0))))
            p.drawEllipse(c, 320, 320)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            core = mix(sun, rgb(255, 255, 245), 0.7)
            p.setBrush(radial(c.x(), c.y(), 110, (0, alpha(core, 220 * glare)), (0.35, alpha(sun, 110 * glare)), (1, alpha(sun, 0))))
            p.drawEllipse(c, 110, 110)
            p.setBrush(alpha(core, 255 * max(0.3, glare)))
            p.drawEllipse(c, 34, 34)
        if 0 <= l.night_progress <= 1 and l.daylight < 0.7:
            self._paint_moon(p, arc(l.night_progress), (1 - w.clouds * 0.85) * (1 - l.daylight))

    def _paint_moon(self, p: QPainter, c: QPointF, visibility: float) -> None:
        if visibility <= 0.03:
            return
        r = 30
        p.setPen(Qt.NoPen)
        p.setBrush(radial(c.x(), c.y(), 160, (0, rgb(220, 225, 255, 70 * visibility)), (1, rgb(220, 225, 255, 0))))
        p.drawEllipse(c, 160, 160)
        p.setBrush(rgb(60, 66, 90, 120 * visibility))
        p.drawEllipse(c, r, r)
        p.setBrush(rgb(244, 242, 226, 255 * visibility))
        p.drawPath(moon_shape(c.x(), c.y(), r, self.moon_phase))

    def _paint_clouds(self, p: QPainter) -> None:
        key = (round(self.light.daylight, 1), round(self.light.golden, 1), round(self.weather.clouds, 1), round(self.weather.rain, 1))
        if key != self._cloud_key:
            self._cloud_key = key
            self._cloud_sprites = [self._make_cloud_sprite(i) for i in range(4)]
        for x, y, s, _, i in self._clouds:
            img = self._cloud_sprites[int(i)]
            p.drawImage(QRectF(x, y, img.width() * s, img.height() * s), img)

    def _make_cloud_sprite(self, seed: int) -> QImage:
        l, w = self.light, self.weather
        rng = random.Random(seed)
        heavy = max(0.0, (w.clouds - 0.55) * 2.2) + w.rain * 0.6
        day = mix(rgb(250, 250, 252), rgb(128, 134, 146), min(1, heavy))
        colour = mix(rgb(34, 38, 54), day, l.daylight)
        if l.golden > 0:
            colour = mix(colour, rgb(250, 176, 150), l.golden * 0.5 * (1 - heavy * 0.6))
        img = QImage(520, 260, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        blob = soft_blob(160, alpha(colour, 230 if heavy < 0.5 else 245))
        shade = soft_blob(160, alpha(scaled(colour, 0.78), 200))
        for _ in range(9):
            # Every blob stays wholly inside the sprite, so no hard edges.
            r = rng.uniform(60, 110)
            cx = rng.uniform(r, 520 - r)
            cy = rng.uniform(r * 0.7, 260 - r * 0.6 - 16)
            p.drawImage(QRectF(cx - r, cy - r * 0.7 + 14, r * 2, r * 1.3), shade)
            p.drawImage(QRectF(cx - r, cy - r * 0.7, r * 2, r * 1.3), blob)
        p.end()
        return img

    def _paint_bolt(self, p: QPainter) -> None:
        k = self.lightning
        path = QPainterPath()
        path.moveTo(*self._bolt[0])
        for pt in self._bolt[1:]:
            path.lineTo(*pt)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(rgb(200, 210, 255, 90 * k), 10))
        p.drawPath(path)
        p.setPen(QPen(rgb(255, 255, 255, 255 * k), 2.5))
        p.drawPath(path)

    def _paint_fog(self, p: QPainter) -> None:
        w, l = self.weather, self.light
        if w.fog <= 0:
            return
        colour = mix(rgb(70, 76, 90), rgb(214, 218, 222), l.daylight)
        p.fillRect(QRectF(0, 0, W, H), vgrad(0, H, (0, alpha(colour, 50 * w.fog)), (0.6, alpha(colour, 120 * w.fog)), (1, alpha(colour, 90 * w.fog))))
        p.setOpacity(0.5 * w.fog)
        for i in range(7):
            x = ((self.t * (8 + i * 3) + i * 420) % (W + 1200)) - 700
            y = 180 + i * 100
            p.drawImage(QRectF(x, y - 90, 900, 180), self._fog_sprite)
        p.setOpacity(1.0)

    def _paint_precipitation(self, p: QPainter) -> None:
        w, l = self.weather, self.light
        if self._rain:
            drift = 1 if w.wind_from_west else -1
            lean = drift * (60 + w.wind * 420) / 1000
            colour = mix(rgb(120, 130, 150), rgb(200, 210, 225), l.daylight)
            p.setPen(QPen(alpha(colour, 120), 1.3))
            for x, y, _, length in self._rain:
                p.drawLine(QPointF(x, y), QPointF(x - lean * length, y - length))
        if self._snow:
            p.setPen(Qt.NoPen)
            p.setBrush(alpha(mix(rgb(170, 176, 196), rgb(255, 255, 255), l.daylight), 225))
            for x, y, _, size, _ in self._snow:
                p.drawEllipse(QPointF(x, y), size, size)


def moon_shape(cx: float, cy: float, r: float, phase: float) -> QPainterPath:
    """The lit part of the moon for a phase (0 new .. 0.5 full .. 1 new),
    waxing lit on the right as seen from the northern hemisphere."""
    path = QPainterPath()
    waxing = phase < 0.5
    # The terminator is an ellipse whose half-width runs r..-r across each half.
    k = math.cos(2 * math.pi * phase)  # 1 new, -1 full
    steps = 40
    path.moveTo(cx, cy - r)
    side = 1 if waxing else -1
    for i in range(steps + 1):  # the bright limb
        a = -math.pi / 2 + math.pi * i / steps
        path.lineTo(cx + side * r * math.cos(a), cy + r * math.sin(a))
    for i in range(steps + 1):  # back up along the terminator
        a = math.pi / 2 - math.pi * i / steps
        path.lineTo(cx + side * r * k * math.cos(a), cy + r * math.sin(a))
    path.closeSubpath()
    return path
