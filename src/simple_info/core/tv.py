"""TV listings for UK Freeview channels.

The listings are the open-source Freeview guide at
https://github.com/dp247/Freeview-EPG: one XMLTV file covering about 280
channels for the next week, rebuilt twice a day (no sign-up). It's a few
megabytes, so it's downloaded at most every few hours and kept on disk;
only the channels on the board are read out of it.

Everything that touches the network returns None on failure rather than
raising: the board carries on with the copy on disk.
"""
from __future__ import annotations

import gzip
import os
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from simple_info.core.http import SSL_CONTEXT

GUIDE_URL = "https://raw.githubusercontent.com/dp247/Freeview-EPG/master/epg.xml"
TIMEOUT_SECONDS = 60
MAX_AGE_SECONDS = 6 * 3600  # download a fresh guide when the copy on disk is older than this

# A sensible first set of radio stations: BBC Radio Scotland and the national stations.
DEFAULT_RADIO = ["BBCRScotland.uk", "bauer:mf1", "bauer:ghs", "BBCR1.uk", "BBCR2.uk", "BBCR3.uk", "BBCR4FM.uk", "BBCR5L.uk", "BBCR6M.uk",
                 "ClassicFM.uk"]

# A sensible first set: the main channels, as seen in the north of Scotland.
DEFAULT_CHANNELS = ["BBCOneScotHD.uk", "BBCTwoHD.uk", "STVNorth.uk", "Channel4Scotland.uk", "5.uk", "BBCScotland.uk",
                    "BBCFourHD.uk", "ITV2.uk", "E4.uk", "More4.uk", "Film4.uk", "BBCNews.uk"]


@dataclass
class Channel:
    id: str  # XMLTV id, "BBCOneScotHD.uk"
    name: str  # "BBC One Scotland HD"

    @property
    def short_name(self) -> str:
        """The name without the "HD" that most of them carry."""
        name = self.name
        for tail in (" HD",):
            if name.endswith(tail):
                name = name[: -len(tail)]
        return name

    @property
    def is_radio(self) -> bool:
        lowered = self.name.lower()
        bbc_radio = self.id.startswith("BBCR") and not self.id.startswith("BBCRed")  # (BBC Red Button is TV)
        return bbc_radio or "radio" in lowered or lowered in RADIO_NAMES


RADIO_NAMES = {"capital", "capital xtra", "classic fm", "heart 80s", "heart 90s", "heart dance", "heart radio", "lbc",
               "lbc news", "planet rock", "smooth radio", "talksport", "virgin radio", "now 70s", "now 80s",
               "now 90s & 00s", "now rock", "premier radio", "panjab radio", "bfbs radio", "rnib connect", "rté 2fm",
               "rté lyric fm", "rté radio 1", "rté raidió na gaeltachta", "bbc world service", "bbc asian network",
               "radio x", "gigs"}


@dataclass
class Programme:
    start: datetime  # aware
    stop: datetime
    title: str
    description: str = ""
    episode: str = ""  # "S1E5", when known

    def on_at(self, when: datetime) -> bool:
        return self.start <= when < self.stop

    def progress(self, when: datetime) -> float:
        span = (self.stop - self.start).total_seconds()
        return max(0.0, min(1.0, (when - self.start).total_seconds() / span)) if span > 0 else 0.0


@dataclass
class Listings:
    channels: list[Channel]  # the board's channels, in the board's order
    programmes: dict[str, list[Programme]] = field(default_factory=dict)  # channel id -> its programmes, in order
    guide_date: float = 0.0  # when the guide file was downloaded

    def on_now(self, channel_id: str, when: datetime) -> Optional[Programme]:
        return next((p for p in self.programmes.get(channel_id, []) if p.on_at(when)), None)

    def next_after(self, channel_id: str, when: datetime) -> Optional[Programme]:
        return next((p for p in self.programmes.get(channel_id, []) if p.start >= when), None)


def parse_time(text: str) -> Optional[datetime]:
    """XMLTV times: "20261020224000 +0100"."""
    try:
        return datetime.strptime(text.strip(), "%Y%m%d%H%M%S %z")
    except (AttributeError, ValueError):
        try:
            return datetime.strptime(text.strip()[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except (AttributeError, ValueError):
            return None


def guide_path(cache_dir: Path) -> Path:
    return cache_dir / "tv-guide.xml"


_download_lock = threading.Lock()  # (the TV and radio boards share the guide)


def download_guide(path: Path, max_age: float = MAX_AGE_SECONDS, force: bool = False) -> bool:
    """Fetch a fresh guide if the one on disk is old (or missing). Returns
    whether there's a usable guide on disk afterwards."""
    with _download_lock:
        return _download_guide(path, max_age, force)


def _download_guide(path: Path, max_age: float, force: bool) -> bool:
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        age = None
    if age is not None and age < max_age and not force:
        return True
    request = urllib.request.Request(GUIDE_URL, headers={"User-Agent": "Simple-Info/1", "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=SSL_CONTEXT) as response:
            data = response.read()
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        if b"<tv" not in data[:2000]:
            return age is not None
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(".part")
        part.write_bytes(data)
        os.replace(part, path)  # never leave a half-written guide
        return True
    except (OSError, EOFError):
        return age is not None


def read_channels(path: Path, radio: bool = False) -> list[Channel]:
    """Every TV channel in the guide (or, with radio, every radio station), by name."""
    channels = []
    try:
        for _, el in ET.iterparse(path, events=("end",)):
            if el.tag == "channel":
                c = Channel(el.get("id") or "", (el.findtext("display-name") or el.get("id") or "").strip())
                if c.id and c.is_radio == radio:
                    channels.append(c)
                el.clear()
            elif el.tag == "programme":
                break  # the channels all come first
    except (OSError, ET.ParseError):
        return []
    return sorted(channels, key=lambda c: c.name.lower())


def read_listings(path: Path, channel_ids: list[str], start: datetime, end: datetime) -> Optional[Listings]:
    """The chosen channels' programmes overlapping [start, end)."""
    wanted = set(channel_ids)
    names: dict[str, str] = {}
    programmes: dict[str, list[Programme]] = {c: [] for c in channel_ids}
    try:
        for _, el in ET.iterparse(path, events=("end",)):
            if el.tag == "channel":
                if el.get("id") in wanted:
                    names[el.get("id")] = (el.findtext("display-name") or el.get("id")).strip()
                el.clear()
            elif el.tag == "programme":
                cid = el.get("channel")
                if cid in wanted:
                    begin, stop = parse_time(el.get("start", "")), parse_time(el.get("stop", ""))
                    if begin and stop and begin < end and stop > start:
                        episode = next((e.text or "" for e in el.findall("episode-num") if (e.text or "").startswith("S")), "")
                        programmes[cid].append(Programme(begin, stop, (el.findtext("title") or "").strip() or "?",
                                                         (el.findtext("desc") or "").strip(), episode))
                el.clear()
        mtime = path.stat().st_mtime
    except (OSError, ET.ParseError):
        return None
    for items in programmes.values():
        items.sort(key=lambda p: p.start)
    channels = [Channel(c, names.get(c, c)) for c in channel_ids if c in names]
    return Listings(channels, {c.id: programmes[c.id] for c in channels}, mtime)


def fetch(cache_dir: Path, channel_ids: list[str], now: Optional[datetime] = None) -> Optional[Listings]:
    """The board's listings from now until this time tomorrow, downloading
    a fresh guide first if the copy on disk is old."""
    path = guide_path(cache_dir)
    if not download_guide(path):
        return None
    now = now or datetime.now(timezone.utc)
    return read_listings(path, channel_ids, now - timedelta(hours=3), now + timedelta(hours=27))
