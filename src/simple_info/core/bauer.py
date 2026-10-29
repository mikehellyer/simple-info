"""Schedules for Bauer's local radio stations, which aren't on Freeview and
so aren't in the TV guide: MFR, and Greatest Hits Radio for the North of
Scotland (which MFR 2 became).

Bauer's own listening service (the one behind its Rayo / Planet Radio
websites and apps) gives each station's schedule a day at a time. Its
stations are known to the board as "bauer:<station code>", beside the
Freeview guide's ids.

Everything that touches the network returns None on failure rather than
raising.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, timedelta
from typing import Optional

from simple_info.core.http import SSL_CONTEXT
from simple_info.core.tv import Channel, Programme

API_URL = "https://listenapi.planetradio.co.uk/api9.2"
TIMEOUT_SECONDS = 10
PREFIX = "bauer:"

# (station code, name on the board)
STATIONS = [
    ("mf1", "MFR"),
    ("ghs", "MFR 2 · Greatest Hits"),  # Greatest Hits Radio (The North of Scotland), formerly MFR 2
    ("no1", "Northsound 1"),
]
NAMES = {f"{PREFIX}{code}": name for code, name in STATIONS}


def is_bauer(channel_id: str) -> bool:
    return channel_id.startswith(PREFIX)


def channels() -> list[Channel]:
    return [Channel(cid, name) for cid, name in NAMES.items()]


def _get_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "Simple-Info/1", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=SSL_CONTEXT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def parse_schedule(payload) -> list[Programme]:
    """Programmes from the service's {"2026-10-29": [{start, duration, title…}…]}."""
    programmes = []
    for shows in (payload.values() if isinstance(payload, dict) else []):
        for s in shows if isinstance(shows, list) else []:
            try:
                start = datetime.fromisoformat(str(s["start"]).replace("Z", "+00:00"))
                stop = start + timedelta(seconds=int(s.get("duration") or 0))
            except (KeyError, TypeError, ValueError):
                continue
            title = str(s.get("title") or "").strip()
            if title and stop > start:
                programmes.append(Programme(start, stop, title, str(s.get("shortdesc") or "").strip()))
    return sorted(programmes, key=lambda p: p.start)


def fetch_schedule(channel_id: str, today: Optional[date] = None) -> Optional[list[Programme]]:
    """Today's and tomorrow's programmes (the board looks four hours ahead,
    which can run past midnight)."""
    if not is_bauer(channel_id):
        return None
    code = channel_id[len(PREFIX):]
    today = today or date.today()
    programmes, got = [], False
    for day in (today, today + timedelta(days=1)):
        payload = _get_json(f"{API_URL}/schedule/{code}/{day.isoformat()}/{(day + timedelta(days=1)).isoformat()}")
        if isinstance(payload, dict) and "error" not in payload:
            got = True
            programmes += parse_schedule(payload)
    if not got:
        return None
    seen, unique = set(), []
    for p in programmes:  # (a day's last show can be listed on both days)
        if (p.start, p.title) not in seen:
            seen.add((p.start, p.title))
            unique.append(p)
    return unique
