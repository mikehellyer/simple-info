"""The sport board's backgrounds: a floodlit stadium at night, seen from
high in the stand, with the pitch marked out for the sport on show.

- football: touchlines, halfway line, centre circle, penalty areas, goals
- rugby: try lines, 22s, dashed 10 m and 5 m lines, H-shaped posts
- cricket: an oval with the boundary rope, the brown pitch, creases, stumps
- baseball: the diamond from behind home plate, infield dirt, bases, mound

Each is drawn once for each window size and kept; only the floodlights'
glow breathes a little. The pitch is laid out in real units (metres, or
feet for baseball) and put into perspective by `Projection`.
"""
from __future__ import annotations

import math
import random
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPen

from simple_info.core import sports as sp
from simple_info.gui.boards.station import cover
from simple_info.gui.paint import H, W, alpha, mix, poly, radial, rgb, vgrad

HORIZON = 150.0
K = 570.0  # how far below the horizon things are at depth z=1
Z_NEAR, Z_FAR = 0.7, 3.0
GRASS_DARK, GRASS_LIGHT = rgb(30, 92, 44), rgb(40, 112, 54)
LINE = rgb(236, 240, 232, 210)
DIRT = rgb(150, 98, 60)
LIGHTS = [(140, 96), (560, 70), (1040, 70), (1460, 96)]  # floodlight towers' lamp banks
LAMP = rgb(255, 250, 225)


class Projection:
    """Field units (x across, d away from us) to screen points."""

    def __init__(self, d_near: float, d_far: float, scale: float):
        self.d_near, self.d_far, self.scale = d_near, d_far, scale

    def z(self, d: float) -> float:
        return Z_NEAR + (Z_FAR - Z_NEAR) * (d - self.d_near) / (self.d_far - self.d_near)

    def __call__(self, x: float, d: float) -> QPointF:
        z = max(0.2, self.z(d))
        return QPointF(W / 2 + x * self.scale / z, HORIZON + K / z)

    def height(self, d: float, h: float) -> float:
        """Screen pixels for something h tall standing at depth d."""
        return h * self.scale / max(0.2, self.z(d))

    def path(self, pts, closed: bool = False) -> QPainterPath:
        path = QPainterPath()
        for i, (x, d) in enumerate(pts):
            pt = self(x, d)
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        if closed:
            path.closeSubpath()
        return path

    def line(self, p: QPainter, x1, d1, x2, d2, steps: int = 1) -> None:
        p.drawPath(self.path([(x1 + (x2 - x1) * i / steps, d1 + (d2 - d1) * i / steps) for i in range(steps + 1)]))

    def ellipse(self, cx, cd, rx, rd, a0=0.0, a1=360.0, steps=72) -> list[tuple[float, float]]:
        return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / steps)),
                 cd + rd * math.sin(math.radians(a0 + (a1 - a0) * i / steps))) for i in range(steps + 1)]


# the stand's far edge is where the grass ends; each sport's projection puts it at about y = 340
PROJECTIONS = {
    sp.FOOTBALL: Projection(-6, 74, 23.0),
    sp.RUGBY: Projection(-6, 76, 21.0),
    sp.CRICKET: Projection(-10, 150, 15.0),
    sp.BASEBALL: Projection(-60, 430, 7.4),
}
FAR_EDGE = {sp.FOOTBALL: 76, sp.RUGBY: 78, sp.CRICKET: 148, sp.BASEBALL: 425}


class Stadium:
    def __init__(self):
        self._cache: dict = {}
        self.t = 0.0

    def step(self, dt: float) -> None:
        self.t += dt

    def paint(self, p: QPainter, target: QRectF, sport: str) -> None:
        size = (int(target.width()), int(target.height()))
        img: Optional[QImage] = self._cache.get((sport, size))
        if img is None:
            if len(self._cache) > 8:
                self._cache.clear()
            img = QImage(max(1, size[0]), max(1, size[1]), QImage.Format_RGB32)
            cp = QPainter(img)
            s, x, y = cover(QRectF(0, 0, *size))
            cp.translate(x, y)
            cp.scale(s, s)
            cp.setRenderHint(QPainter.Antialiasing)
            self._paint_ground(cp, sport)
            cp.end()
            self._cache[(sport, size)] = img
        p.drawImage(target.topLeft(), img)

        s, x, y = cover(target)
        p.save()
        p.translate(x, y)
        p.scale(s, s)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for i, (lx, ly) in enumerate(LIGHTS):
            k = 0.9 + 0.1 * math.sin(self.t * 0.8 + i * 1.7)
            p.setBrush(radial(lx, ly, 150, (0, alpha(LAMP, 110 * k)), (0.3, alpha(LAMP, 40 * k)), (1, alpha(LAMP, 0))))
            p.drawEllipse(QPointF(lx, ly), 150, 150)
        p.restore()

    # --- drawn once

    def _paint_ground(self, p: QPainter, sport: str) -> None:
        proj = PROJECTIONS.get(sport, PROJECTIONS[sp.FOOTBALL])
        far = FAR_EDGE.get(sport, 76)
        edge_y = proj(0, far).y()
        # night sky
        p.fillRect(QRectF(-400, -400, W + 800, H + 800), vgrad(-100, edge_y, rgb(6, 10, 22), rgb(20, 28, 48)))
        self._paint_stand(p, edge_y)
        self._paint_grass(p, proj, far, sport)
        {sp.FOOTBALL: self._football, sp.RUGBY: self._rugby, sp.CRICKET: self._cricket,
         sp.BASEBALL: self._baseball}.get(sport, self._football)(p, proj)
        self._paint_floodlights(p, edge_y)
        # darker towards the edges and the bottom, so the cards stand out
        p.setPen(Qt.NoPen)
        p.setBrush(radial(W / 2, H * 0.45, 1050, (0, rgb(0, 0, 0, 30)), (0.75, rgb(0, 0, 0, 110)), (1, rgb(0, 0, 0, 160))))
        p.drawRect(QRectF(-400, -400, W + 800, H + 800))

    def _paint_stand(self, p: QPainter, edge_y: float) -> None:
        top = 120.0
        p.setPen(Qt.NoPen)
        p.setBrush(vgrad(top, edge_y, rgb(26, 30, 40), rgb(14, 16, 22)))
        p.drawRect(QRectF(-400, top, W + 800, edge_y - top + 4))
        # the roof's edge
        p.setBrush(rgb(40, 46, 58))
        p.drawRect(QRectF(-400, top - 14, W + 800, 16))
        # the crowd: little dots of colour in rows, lit from the pitch side
        rng = random.Random(7)
        rows = int((edge_y - top - 20) / 9)
        for r in range(rows):
            y = top + 14 + r * 9
            light = 0.35 + 0.65 * r / max(1, rows)
            x = -400 + rng.uniform(0, 6)
            while x < W + 400:
                c = rng.choice(((200, 60, 60), (60, 90, 190), (230, 230, 230), (230, 200, 60), (60, 60, 70), (120, 60, 140)))
                p.setBrush(rgb(c[0] * light * 0.55, c[1] * light * 0.55, c[2] * light * 0.55))
                p.drawEllipse(QPointF(x, y + rng.uniform(-1.5, 1.5)), 2.6, 3.2)
                x += rng.uniform(5.5, 8.0)
        # advertising hoardings along the front of the stand
        p.setBrush(vgrad(edge_y - 16, edge_y, rgb(20, 60, 110), rgb(12, 36, 70)))
        p.drawRect(QRectF(-400, edge_y - 16, W + 800, 18))

    def _paint_grass(self, p: QPainter, proj: Projection, far: float, sport: str) -> None:
        near = proj.d_near - 30
        width = 600 if sport in (sp.BASEBALL, sp.CRICKET) else 160
        p.setPen(Qt.NoPen)
        p.setBrush(GRASS_DARK)
        p.drawPath(proj.path([(-width, near), (width, near), (width, far), (-width, far)], closed=True))
        # mown stripes, across the pitch (along it for cricket, which is mown along the wicket)
        p.setBrush(GRASS_LIGHT)
        if sport == sp.CRICKET:
            for i in range(-12, 12, 2):
                x = i * 6.0
                p.drawPath(proj.path([(x, near), (x + 6, near), (x + 6, far), (x, far)], closed=True))
        else:
            step = 12.0 if sport == sp.BASEBALL else 5.25
            i = 0
            x = -width
            while x < width:
                if i % 2 == 0:
                    p.drawPath(proj.path([(x, near), (x + step, near), (x + step, far), (x, far)], closed=True))
                x += step
                i += 1
        # the light falls off towards us
        p.setBrush(vgrad(proj(0, far).y(), H, rgb(255, 255, 240, 18), rgb(0, 0, 0, 60)))
        p.drawRect(QRectF(-400, proj(0, far).y(), W + 800, H + 400))

    def _pen(self, p: QPainter, width: float = 2.4) -> None:
        p.setPen(QPen(LINE, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)

    def _football(self, p: QPainter, proj: Projection) -> None:
        L, Wd = 52.5, 68.0
        self._pen(p)
        p.drawPath(proj.path([(-L, 0), (L, 0), (L, Wd), (-L, Wd)], closed=True))
        proj.line(p, 0, 0, 0, Wd, 12)
        p.drawPath(proj.path(proj.ellipse(0, Wd / 2, 9.15, 9.15)))
        for side in (-1, 1):
            x = side * L
            p.drawPath(proj.path([(x, Wd / 2 - 20.15), (x - side * 16.5, Wd / 2 - 20.15), (x - side * 16.5, Wd / 2 + 20.15), (x, Wd / 2 + 20.15)]))
            p.drawPath(proj.path([(x, Wd / 2 - 9.16), (x - side * 5.5, Wd / 2 - 9.16), (x - side * 5.5, Wd / 2 + 9.16), (x, Wd / 2 + 9.16)]))
            # the D at the edge of the box
            arc = [(x - side * 11 + side * -9.15 * math.cos(math.radians(a)), Wd / 2 + 9.15 * math.sin(math.radians(a)))
                   for a in range(-53, 54, 6)]
            p.drawPath(proj.path(arc))
            # goal: posts and crossbar, 2.44 m tall
            for d in (Wd / 2 - 3.66, Wd / 2 + 3.66):
                foot = proj(x, d)
                p.drawLine(foot, QPointF(foot.x(), foot.y() - proj.height(d, 2.44)))
            a, b = proj(x, Wd / 2 - 3.66), proj(x, Wd / 2 + 3.66)
            p.drawLine(QPointF(a.x(), a.y() - proj.height(Wd / 2 - 3.66, 2.44)), QPointF(b.x(), b.y() - proj.height(Wd / 2 + 3.66, 2.44)))
        p.setPen(Qt.NoPen)
        p.setBrush(LINE)
        for x in (-41.5, 0, 41.5):
            c = proj(x, Wd / 2)
            p.drawEllipse(c, 2.5, 1.6)

    def _rugby(self, p: QPainter, proj: Projection) -> None:
        L, Wd = 50.0, 70.0
        self._pen(p)
        p.drawPath(proj.path([(-L - 10, 0), (L + 10, 0), (L + 10, Wd), (-L - 10, Wd)], closed=True))
        for x in (-L, L, -28, 28, 0):  # try lines, 22s, halfway
            proj.line(p, x, 0, x, Wd, 12)
        dashed = QPen(LINE, 2.0, Qt.CustomDashLine)
        dashed.setDashPattern([6, 6])
        p.setPen(dashed)
        for x in (-40, -10, 10, 40):  # the dashed 10 m and 5 m lines
            proj.line(p, x, 0, x, Wd, 12)
        for d in (5, 15, Wd - 15, Wd - 5):
            proj.line(p, -L, d, L, d, 20)
        # H-shaped posts: uprights 5.6 m apart and 16 m tall, crossbar at 3 m
        p.setPen(QPen(rgb(245, 245, 240), 3.2, Qt.SolidLine, Qt.FlatCap))
        for x in (-L, L):
            feet = []
            for d in (Wd / 2 - 2.8, Wd / 2 + 2.8):
                foot = proj(x, d)
                p.drawLine(foot, QPointF(foot.x(), foot.y() - proj.height(d, 16)))
                feet.append((foot, d))
            (a, da), (b, db) = feet
            p.drawLine(QPointF(a.x(), a.y() - proj.height(da, 3)), QPointF(b.x(), b.y() - proj.height(db, 3)))
            # padding at the foot of the posts
            p.setPen(Qt.NoPen)
            p.setBrush(rgb(200, 40, 40))
            for foot, d in feet:
                h = proj.height(d, 1.6)
                p.drawRect(QRectF(foot.x() - h * 0.18, foot.y() - h, h * 0.36, h))
            p.setPen(QPen(rgb(245, 245, 240), 3.2, Qt.SolidLine, Qt.FlatCap))

    def _cricket(self, p: QPainter, proj: Projection) -> None:
        centre = 75.0
        # the outfield's edge, then the boundary rope a little inside it
        p.setPen(QPen(rgb(240, 240, 240, 220), 3))
        p.setBrush(Qt.NoBrush)
        p.drawPath(proj.path(proj.ellipse(0, centre, 66, 66, 0, 360, 120)))
        # the square: slightly lighter, finer grass
        p.setPen(Qt.NoPen)
        p.setBrush(rgb(70, 132, 70, 120))
        p.drawPath(proj.path([(-12, centre - 14), (12, centre - 14), (12, centre + 14), (-12, centre + 14)], closed=True))
        # the pitch: 20.12 m between the stumps, 3.05 m wide, worn brown
        p.setBrush(DIRT.lighter(115))
        p.drawPath(proj.path([(-1.6, centre - 11), (1.6, centre - 11), (1.6, centre + 11), (-1.6, centre + 11)], closed=True))
        self._pen(p, 2.0)
        for end in (-1, 1):
            d = centre + end * 10.06
            proj.line(p, -1.5, d, 1.5, d)  # bowling crease, through the stumps
            pc = centre + end * (10.06 - 1.22)
            proj.line(p, -1.6, pc, 1.6, pc)  # popping crease
            for x in (-1.32, 1.32):  # return creases
                proj.line(p, x, d, x, pc)
            # stumps, 0.71 m tall
            p.setPen(QPen(rgb(240, 225, 190), 2.2, Qt.SolidLine, Qt.FlatCap))
            for x in (-0.11, 0, 0.11):
                foot = proj(x, d)
                p.drawLine(foot, QPointF(foot.x(), foot.y() - proj.height(d, 0.71)))
            self._pen(p, 2.0)
        # the 30-yard circle, dotted
        dotted = QPen(LINE, 2.0, Qt.CustomDashLine)
        dotted.setDashPattern([1.5, 6])
        p.setPen(dotted)
        p.drawPath(proj.path(proj.ellipse(0, centre, 27.4, 27.4, 0, 360, 90)))

    def _baseball(self, p: QPainter, proj: Projection) -> None:
        r2 = math.sqrt(2) / 2
        base = 90.0 * r2  # bases are 90 ft apart, the diamond turned 45°
        home, first, second, third = (0, 0), (base, base), (0, 2 * base), (-base, base)
        # outfield wall: 330 ft down the lines, 400 ft to centre
        fence = []
        for a in range(-45, 46, 3):
            dist = 330 + 70 * math.cos(math.radians(a * 2))
            fence.append((dist * math.sin(math.radians(a)), dist * math.cos(math.radians(a))))
        p.setPen(Qt.NoPen)
        p.setBrush(DIRT.darker(115))  # warning track
        track = [(x * 1.04, d * 1.04) for x, d in fence]
        p.drawPath(proj.path([home] + track, closed=True))
        p.setBrush(GRASS_LIGHT)
        p.drawPath(proj.path([home] + fence, closed=True))
        for i in range(0, len(fence) - 1, 2):  # outfield stripes, fanning out
            p.setBrush(GRASS_DARK)
            p.drawPath(proj.path([home, fence[i], fence[i + 1]], closed=True))
        # the infield dirt: an arc 95 ft round the pitcher's mound, and round the plate
        p.setBrush(DIRT)
        arc = [(95 * math.sin(math.radians(a)), 60.5 + 95 * math.cos(math.radians(a))) for a in range(-50, 51, 4)]
        p.drawPath(proj.path([home] + arc, closed=True))
        p.setBrush(GRASS_LIGHT)
        inset = 9.0
        p.drawPath(proj.path([(0, inset * 1.6), (base - inset, base), (0, 2 * base - inset), (-base + inset, base)], closed=True))
        p.setBrush(DIRT)
        p.drawPath(proj.path(proj.ellipse(0, 0, 13, 13)))
        p.drawPath(proj.path(proj.ellipse(0, 60.5, 9, 9)))  # the mound
        # foul lines, out to the wall
        self._pen(p, 2.6)
        for side in (-1, 1):
            proj.line(p, 0, 0, side * 330 * r2, 330 * r2, 10)
        # bases and the plate
        p.setPen(Qt.NoPen)
        p.setBrush(rgb(250, 250, 250))
        for x, d in (first, second, third):
            p.drawPath(proj.path([(x - 1.2, d), (x, d - 1.2), (x + 1.2, d), (x, d + 1.2)], closed=True))
        p.drawPath(proj.path([(-0.7, 0.7), (0.7, 0.7), (0.7, 0), (0, -0.7), (-0.7, 0)], closed=True))
        p.setBrush(rgb(240, 240, 240))
        p.drawPath(proj.path(proj.ellipse(0, 60.5, 1.0, 0.4)))  # the rubber

    def _paint_floodlights(self, p: QPainter, edge_y: float) -> None:
        for lx, ly in LIGHTS:
            # the pylon, down behind the stand
            p.setPen(QPen(rgb(30, 34, 42), 6))
            p.drawLine(QPointF(lx, ly + 20), QPointF(lx, ly + 70))
            # beams down onto the pitch
            p.setPen(Qt.NoPen)
            p.setBrush(vgrad(ly, edge_y + 300, alpha(LAMP, 26), alpha(LAMP, 0)))
            p.drawPolygon(poly((lx - 40, ly + 10), (lx + 40, ly + 10), (W / 2 + (lx - W / 2) * 0.3 + 260, edge_y + 300),
                               (W / 2 + (lx - W / 2) * 0.3 - 260, edge_y + 300)))
            # the lamp bank: a grid of bright lamps
            p.setBrush(rgb(40, 44, 52))
            p.drawRoundedRect(QRectF(lx - 46, ly - 20, 92, 40), 4, 4)
            p.setBrush(LAMP)
            for r in range(3):
                for c in range(6):
                    p.drawEllipse(QPointF(lx - 37 + c * 14.8, ly - 11 + r * 11), 4.6, 4.2)
