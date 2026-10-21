"""News headlines from RSS feeds: BBC News (the UK, the world, Scotland
and its regions, and the subjects), Sky News and The Guardian.

Feeds are free and meant for exactly this. Each story comes with its
picture, which is fetched at a size to suit the board.

Everything that touches the network returns None on failure rather than
raising: the board keeps showing the last headlines it had.
"""
from __future__ import annotations

import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

from simple_info.core.http import SSL_CONTEXT

TIMEOUT_SECONDS = 10
MEDIA = "{http://search.yahoo.com/mrss/}"
MAX_IMAGE_BYTES = 3 * 1024 * 1024


@dataclass(frozen=True)
class Feed:
    key: str
    name: str
    url: str

    @property
    def source(self) -> str:
        return self.name.split(" – ")[0].split(":")[0]


_BBC = "https://feeds.bbci.co.uk/news"
FEEDS = [
    Feed("bbc/top", "BBC News – Top stories", f"{_BBC}/rss.xml"),
    Feed("bbc/uk", "BBC News – UK", f"{_BBC}/uk/rss.xml"),
    Feed("bbc/world", "BBC News – World", f"{_BBC}/world/rss.xml"),
    Feed("bbc/scotland", "BBC News – Scotland", f"{_BBC}/scotland/rss.xml"),
    Feed("bbc/ne-scotland", "BBC News – NE Scotland, Orkney & Shetland", f"{_BBC}/scotland/north_east_orkney_and_shetland/rss.xml"),
    Feed("bbc/highlands", "BBC News – Highlands & Islands", f"{_BBC}/scotland/highlands_and_islands/rss.xml"),
    Feed("bbc/glasgow", "BBC News – Glasgow & West Scotland", f"{_BBC}/scotland/glasgow_and_west/rss.xml"),
    Feed("bbc/edinburgh", "BBC News – Edinburgh, Fife & East Scotland", f"{_BBC}/scotland/edinburgh_east_and_fife/rss.xml"),
    Feed("bbc/england", "BBC News – England", f"{_BBC}/england/rss.xml"),
    Feed("bbc/wales", "BBC News – Wales", f"{_BBC}/wales/rss.xml"),
    Feed("bbc/ni", "BBC News – Northern Ireland", f"{_BBC}/northern_ireland/rss.xml"),
    Feed("bbc/politics", "BBC News – Politics", f"{_BBC}/politics/rss.xml"),
    Feed("bbc/business", "BBC News – Business", f"{_BBC}/business/rss.xml"),
    Feed("bbc/technology", "BBC News – Technology", f"{_BBC}/technology/rss.xml"),
    Feed("bbc/science", "BBC News – Science & Environment", f"{_BBC}/science_and_environment/rss.xml"),
    Feed("bbc/health", "BBC News – Health", f"{_BBC}/health/rss.xml"),
    Feed("bbc/entertainment", "BBC News – Entertainment & Arts", f"{_BBC}/entertainment_and_arts/rss.xml"),
    Feed("bbc/sport", "BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml"),
    Feed("sky/home", "Sky News", "https://feeds.skynews.com/feeds/rss/home.xml"),
    Feed("sky/world", "Sky News – World", "https://feeds.skynews.com/feeds/rss/world.xml"),
    Feed("guardian/uk", "The Guardian – UK", "https://www.theguardian.com/uk/rss"),
    Feed("guardian/world", "The Guardian – World", "https://www.theguardian.com/world/rss"),
]
BY_KEY = {f.key: f for f in FEEDS}
DEFAULT_KEYS = ["bbc/top", "bbc/scotland", "bbc/ne-scotland", "bbc/world"]


@dataclass
class Story:
    title: str
    summary: str
    link: str
    published: Optional[datetime]  # aware
    image: str  # picture URL ("" if none)
    source: str = ""  # "BBC News", "Sky News"…


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def clean(text: str) -> str:
    """Plain text from a feed's (sometimes HTML) text."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _published(item) -> Optional[datetime]:
    raw = _text(item.findtext("pubDate")) or _text(item.findtext("{http://purl.org/dc/elements/1.1/}date"))
    if not raw:
        return None
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        try:
            when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _picture(item) -> str:
    """The best picture: the widest of media:content, else media:thumbnail, else an image enclosure."""
    best, width = "", -1
    for el in item.findall(f"{MEDIA}content") + item.findall(f"{MEDIA}thumbnail"):
        url = _text(el.get("url"))
        if not url or (el.get("type") and not el.get("type", "").startswith("image")):
            continue
        try:
            w = int(el.get("width") or 0)
        except ValueError:
            w = 0
        if w > width:
            best, width = url, w
    if not best:
        for el in item.findall("enclosure"):
            if _text(el.get("type")).startswith("image") and el.get("url"):
                return _text(el.get("url"))
    return best


def parse_feed(data: bytes, source: str = "") -> list[Story]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    channel = root.find("channel")
    if channel is None:
        return []
    stories = []
    for item in channel.findall("item"):
        title = clean(item.findtext("title"))
        if not title:
            continue
        summary = clean(item.findtext("description"))
        if summary == title:
            summary = ""
        stories.append(Story(title, summary, _text(item.findtext("link")), _published(item), _picture(item), source))
    return stories


def sized(url: str, width: int) -> str:
    """The same picture at about the width wanted, where the site lets us ask."""
    if "ichef.bbci.co.uk" in url:  # BBC: …/standard/240/… (also takes 480, 624, 800)
        size = min((240, 480, 624, 800), key=lambda s: abs(s - width))
        return re.sub(r"/(standard|branded_news|branded_sport)/\d+/", lambda m: f"/{m.group(1)}/{size}/", url)
    if "365dm.com" in url:  # Sky: …/1920x1080/…
        size = "768x432" if width > 400 else "384x216"
        return re.sub(r"/\d+x\d+/", f"/{size}/", url)
    return url


def _get(url: str, limit: int = 4 * 1024 * 1024) -> Optional[bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "Simple-Info/1"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=SSL_CONTEXT) as response:
            return response.read(limit + 1)[: limit + 1]
    except (OSError, ValueError):
        return None


def fetch_feed(key: str) -> Optional[list[Story]]:
    feed = BY_KEY.get(key)
    if feed is None:
        return None
    data = _get(feed.url)
    if data is None:
        return None
    stories = parse_feed(data, feed.source)
    return stories or None


def fetch_image(url: str) -> Optional[bytes]:
    data = _get(url, MAX_IMAGE_BYTES)
    if not data or len(data) > MAX_IMAGE_BYTES:
        return None
    return data


def ago(when: Optional[datetime], now: Optional[datetime] = None) -> str:
    """"just now", "12 min ago", "3 hours ago", or the day and time."""
    if when is None:
        return ""
    now = now or datetime.now(timezone.utc)
    minutes = int((now - when).total_seconds() // 60)
    if minutes < 2:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    if minutes < 24 * 60:
        hours = minutes // 60
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    local = when.astimezone()
    return f"{local:%a} {local.day} {local:%b}"
