import json
from datetime import date, datetime, timezone
from unittest.mock import patch

from simple_info.core import bauer

DAY = {"2026-10-29": [
    {"start": "2026-10-29T14:00:00+00:00", "duration": 14400, "title": "Garry Spence", "shortdesc": "Spence vs Shazam."},
    {"start": "2026-10-29T18:00:00+00:00", "duration": 14400, "title": "Callum Gallacher"},
    {"start": "nonsense", "duration": 60, "title": "Broken"},
]}
NEXT_DAY = {"2026-10-30": [
    {"start": "2026-10-29T22:00:00+00:00", "duration": 10800, "title": "Callum Gallacher"},  # (listed on both days)
    {"start": "2026-10-30T01:00:00+00:00", "duration": 10800, "title": "Mary Mandefield"},
]}


class _Response:
    def __init__(self, data):
        self._data = json.dumps(data).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_parse_schedule():
    garry, callum = bauer.parse_schedule(DAY)
    assert (garry.title, garry.description, garry.start) == ("Garry Spence", "Spence vs Shazam.", datetime(2026, 10, 29, 14, tzinfo=timezone.utc))
    assert (garry.stop - garry.start).total_seconds() == 4 * 3600 and callum.title == "Callum Gallacher"
    assert bauer.parse_schedule({"error": "invalid parameters"}) == [] and bauer.parse_schedule(None) == []


def test_fetch_asks_for_today_and_tomorrow_and_drops_repeats():
    urls = []

    def fake(request, **kwargs):
        urls.append(request.full_url)
        return _Response(DAY if "2026-10-29/" in request.full_url else NEXT_DAY)

    with patch("urllib.request.urlopen", side_effect=fake):
        programmes = bauer.fetch_schedule("bauer:mf1", date(2026, 10, 29))
    assert urls == [f"{bauer.API_URL}/schedule/mf1/2026-10-29/2026-10-30", f"{bauer.API_URL}/schedule/mf1/2026-10-30/2026-10-31"]
    starts = [(p.start.hour, p.title) for p in programmes]
    assert starts == [(14, "Garry Spence"), (18, "Callum Gallacher"), (22, "Callum Gallacher"), (1, "Mary Mandefield")]
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert bauer.fetch_schedule("bauer:mf1") is None
    assert bauer.fetch_schedule("BBCR1.uk") is None


def test_the_stations_mike_asked_for():
    assert bauer.NAMES["bauer:mf1"] == "MFR" and bauer.NAMES["bauer:ghs"].startswith("MFR 2")
    assert all(bauer.is_bauer(c.id) for c in bauer.channels())
