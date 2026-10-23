"""Live train departures and arrivals for stations in Great Britain.

The data is National Rail's live departure boards (Darwin), read through
Huxley 2 (https://huxley2.azurewebsites.net), a free public service that
turns them into plain JSON and needs no sign-up. (It's someone else's
server, so nothing private is ever sent to it: only station codes.)
National Rail asks for its data to be credited "Powered by National Rail
Enquiries", which the board shows.

Everything that touches the network returns None (or []) on failure
rather than raising: the board keeps showing the last trains it had.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from simple_info.core.http import SSL_CONTEXT

TIMEOUT_SECONDS = 10
HUXLEY_URL = "https://huxley2.azurewebsites.net"
DEPARTURES, ARRIVALS = "departures", "arrivals"

# How each train is getting on, for colouring.
ON_TIME, LATE, CANCELLED, UNKNOWN = "on_time", "late", "cancelled", "unknown"


@dataclass
class Station:
    name: str
    crs: str  # the three-letter station code, e.g. "KGX"


@dataclass
class CallingPoint:
    name: str
    scheduled: str  # "12:53"
    expected: str  # "12:58", "On time", "Cancelled", "Delayed"… ("" if it has already been)
    actual: str = ""  # for stops already made, when the train really left


@dataclass
class Service:
    scheduled: str  # "11:40": departure time on a departures board, arrival time on arrivals
    expected: str  # "On time", "11:50", "Delayed", "Cancelled"
    destination: str
    origin: str
    via: str = ""
    platform: str = ""
    operator: str = ""
    cancelled: bool = False
    coaches: int = 0
    reason: str = ""  # why it's late or cancelled
    calling_points: list[CallingPoint] = field(default_factory=list)  # after here (departures) or before (arrivals)

    @property
    def status(self) -> str:
        if self.cancelled or self.expected.lower() == "cancelled":
            return CANCELLED
        if self.expected.lower() == "on time" or (self.expected and self.expected == self.scheduled):
            return ON_TIME
        if self.expected.lower() == "delayed" or re.fullmatch(r"\d\d:\d\d", self.expected):
            return LATE
        return UNKNOWN

    @property
    def expected_text(self) -> str:
        """The expected column, the way station boards put it."""
        status = self.status
        if status == CANCELLED:
            return "Cancelled"
        if status == ON_TIME:
            return "On time"
        if re.fullmatch(r"\d\d:\d\d", self.expected):
            return f"Exp {self.expected}"
        return self.expected or "—"


@dataclass
class TrainBoard:
    station: str
    crs: str
    kind: str  # DEPARTURES or ARRIVALS
    services: list[Service]
    messages: list[str]  # station notices, as plain text
    fetched_at: float


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _places(locations) -> tuple[str, str]:
    """('Leeds & Harrogate', 'via Wakefield') from Huxley's origin/destination list."""
    names, via = [], ""
    for loc in locations or []:
        if not isinstance(loc, dict):
            continue
        name = _text(loc.get("locationName"))
        if name:
            names.append(name)
        via = via or _text(loc.get("via"))
    return " & ".join(names), via


def clean_message(raw: str) -> str:
    """A station notice as plain text: Darwin sends little bits of HTML."""
    text = re.sub(r"<\s*(br|/?p)\b[^>]*>", " ", raw or "", flags=re.I)  # line breaks become spaces
    text = re.sub(r"<[^>]+>", "", text)  # other tags (links…) just go
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _calling_points(groups, previous: bool) -> list[CallingPoint]:
    """The first list of calling points (a train that splits has more)."""
    for group in groups or []:
        points = group.get("callingPoint") if isinstance(group, dict) else None
        if points:
            return [
                CallingPoint(
                    name=_text(p.get("locationName")),
                    scheduled=_text(p.get("st")),
                    expected=_text(p.get("et")),
                    actual=_text(p.get("at")) if previous else "",
                )
                for p in points if isinstance(p, dict) and p.get("locationName")
            ]
    return []


def parse_board(payload: dict, kind: str, fetched_at: Optional[float] = None) -> TrainBoard:
    services = []
    for s in payload.get("trainServices") or []:
        if not isinstance(s, dict):
            continue
        destination, via = _places(s.get("destination"))
        origin, _ = _places(s.get("origin"))
        if kind == ARRIVALS:
            scheduled, expected = _text(s.get("sta")), _text(s.get("eta"))
            points = _calling_points(s.get("previousCallingPoints"), previous=True)
        else:
            scheduled, expected = _text(s.get("std")), _text(s.get("etd"))
            points = _calling_points(s.get("subsequentCallingPoints"), previous=False)
        cancelled = bool(s.get("isCancelled"))
        services.append(Service(
            scheduled=scheduled,
            expected=expected,
            destination=destination or "Unknown",
            origin=origin,
            via=via,
            platform=_text(s.get("platform")),
            operator=_text(s.get("operator")),
            cancelled=cancelled,
            coaches=int(s.get("length") or 0),
            reason=_text(s.get("cancelReason") if cancelled else s.get("delayReason")) or _text(s.get("delayReason")),
            calling_points=points,
        ))
    messages = []
    for m in payload.get("nrccMessages") or []:
        text = clean_message(m.get("value") if isinstance(m, dict) else str(m))
        if text:
            messages.append(text)
    return TrainBoard(
        station=_text(payload.get("locationName")),
        crs=_text(payload.get("crs")),
        kind=kind,
        services=services,
        messages=messages,
        fetched_at=fetched_at if fetched_at is not None else time.time(),
    )


def _get_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "Simple-Info/1", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=SSL_CONTEXT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def board_url(crs: str, kind: str, rows: int = 10, filter_crs: str = "", base_url: str = HUXLEY_URL) -> str:
    path = f"{base_url.rstrip('/')}/{kind}/{urllib.parse.quote(crs.upper())}"
    if filter_crs:
        path += f"/{'to' if kind == DEPARTURES else 'from'}/{urllib.parse.quote(filter_crs.upper())}"
    path += f"/{rows}"
    return f"{path}?{urllib.parse.urlencode({'expand': 'true'})}"


def fetch_board(crs: str, kind: str, rows: int = 10, filter_crs: str = "",
                base_url: str = HUXLEY_URL) -> Optional[TrainBoard]:
    if not re.fullmatch(r"[A-Za-z]{3}", crs or ""):
        return None
    data = _get_json(board_url(crs, kind, rows, filter_crs, base_url))
    if not isinstance(data, dict) or "locationName" not in data:
        return None
    try:
        return parse_board(data, kind)
    except (TypeError, ValueError, AttributeError):
        return None


def search_stations(query: str, base_url: str = HUXLEY_URL) -> list[Station]:
    """Stations whose name contains the query (or with that code), best first."""
    query = query.strip()
    if not query:
        return []
    data = _get_json(f"{base_url.rstrip('/')}/crs/{urllib.parse.quote(query)}")
    stations = []
    for r in data if isinstance(data, list) else []:
        if isinstance(r, dict) and r.get("crsCode") and r.get("stationName"):
            stations.append(Station(str(r["stationName"]), str(r["crsCode"]).upper()))
    if re.fullmatch(r"[A-Za-z]{3}", query) and not any(s.crs == query.upper() for s in stations):
        # typed a station code: the name search doesn't know codes, but a board does
        board = _get_json(board_url(query, DEPARTURES, 1, base_url=base_url))
        if isinstance(board, dict) and board.get("locationName") and board.get("crs"):
            stations.append(Station(str(board["locationName"]), str(board["crs"]).upper()))
    q = query.lower()

    def rank(s: Station) -> tuple:
        name = s.name.lower()
        return (s.crs != query.upper(), name != q, not name.startswith(q), "(bus)" in name, len(name))

    return sorted(stations, key=rank)


def calling_at_text(service: Service, kind: str) -> str:
    """'Calling at: Newark North Gate (12:58), Doncaster (13:19) and Leeds (13:49).'"""
    points = service.calling_points
    if kind == ARRIVALS:  # the first stop is where it started from, said already
        points = [p for p in points if p.name != service.origin]
    if not points:
        return ""

    def when(p: CallingPoint) -> str:
        if p.actual and p.actual.lower() not in ("on time", "no report"):
            return p.actual
        if re.fullmatch(r"\d\d:\d\d", p.expected):
            return p.expected
        if p.expected.lower() == "cancelled":
            return "cancelled"
        return p.scheduled

    names = [f"{p.name} ({when(p)})" for p in points]
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    if kind == ARRIVALS:
        return f"From {service.origin}, calling at {joined}."
    return f"Calling at: {joined}."
