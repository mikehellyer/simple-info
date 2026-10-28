import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from simple_info.core import tv

GUIDE = b"""<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="BBCOneScotHD.uk"><display-name lang="en">BBC One Scotland HD</display-name></channel>
  <channel id="STVNorth.uk"><display-name lang="en">STV North HD</display-name></channel>
  <channel id="BBCRScotland.uk"><display-name lang="en">BBC Radio Scotland</display-name></channel>
  <channel id="Capital.uk"><display-name lang="en">Capital</display-name></channel>
  <programme start="20261021140000 +0100" stop="20261021143000 +0100" channel="BBCOneScotHD.uk">
    <title>Bargain Hunt</title><desc>Antiques.</desc><episode-num system="xmltv_ns">0.4.0</episode-num><episode-num>S12E5</episode-num>
  </programme>
  <programme start="20261021143000 +0100" stop="20261021150000 +0100" channel="BBCOneScotHD.uk"><title>Shift the Thrift</title></programme>
  <programme start="20261021150000 +0100" stop="20261021154500 +0100" channel="BBCOneScotHD.uk"><title>Escape to the Country</title></programme>
  <programme start="20261021140000 +0100" stop="20261021150000 +0100" channel="STVNorth.uk"><title>Dickinson's Real Deal</title></programme>
  <programme start="20261022200000 +0100" stop="20261022210000 +0100" channel="STVNorth.uk"><title>Next week's thing</title></programme>
  <programme start="20261021140000 +0100" stop="20261021150000 +0100" channel="BBCRScotland.uk"><title>Radio</title></programme>
</tv>
"""


def test_read_channels_leaves_out_radio(tmp_path):
    path = tmp_path / "guide.xml"
    path.write_bytes(GUIDE)
    channels = tv.read_channels(path)
    assert [(c.id, c.short_name) for c in channels] == [("BBCOneScotHD.uk", "BBC One Scotland"), ("STVNorth.uk", "STV North")]


def test_read_listings_keeps_the_chosen_channels_in_the_window(tmp_path):
    path = tmp_path / "guide.xml"
    path.write_bytes(GUIDE)
    start = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    listings = tv.read_listings(path, ["STVNorth.uk", "BBCOneScotHD.uk", "Missing.uk"], start, start + timedelta(hours=6))
    assert [c.id for c in listings.channels] == ["STVNorth.uk", "BBCOneScotHD.uk"]
    bbc = listings.programmes["BBCOneScotHD.uk"]
    assert [p.title for p in bbc] == ["Bargain Hunt", "Shift the Thrift", "Escape to the Country"]
    assert bbc[0].episode == "S12E5" and bbc[0].description == "Antiques."
    assert [p.title for p in listings.programmes["STVNorth.uk"]] == ["Dickinson's Real Deal"]  # (next week's is outside)
    now = datetime(2026, 10, 21, 13, 40, tzinfo=timezone.utc)  # 14:40 in the UK
    on = listings.on_now("BBCOneScotHD.uk", now)
    assert on.title == "Shift the Thrift" and round(on.progress(now), 2) == 0.33
    assert listings.next_after("BBCOneScotHD.uk", now).title == "Escape to the Country"
    assert tv.read_listings(tmp_path / "nope.xml", ["X"], start, start) is None


class _Response:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_only_when_the_copy_on_disk_is_old(tmp_path):
    path = tmp_path / "guide.xml"
    with patch("urllib.request.urlopen", return_value=_Response(GUIDE)) as opened:
        assert tv.download_guide(path) and path.read_bytes() == GUIDE
        assert tv.download_guide(path) and opened.call_count == 1  # fresh enough: not again
        old = time.time() - tv.MAX_AGE_SECONDS - 60
        os.utime(path, (old, old))
        assert tv.download_guide(path) and opened.call_count == 2
    old = time.time() - tv.MAX_AGE_SECONDS - 60
    os.utime(path, (old, old))
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert tv.download_guide(path)  # offline, but the old copy will do
        assert not tv.download_guide(tmp_path / "none.xml")
    with patch("urllib.request.urlopen", return_value=_Response(b"<html>not a guide</html>")):
        assert not tv.download_guide(tmp_path / "bad.xml")


def test_parse_time():
    assert tv.parse_time("20261020224000 +0100") == datetime(2026, 10, 20, 21, 40, tzinfo=timezone.utc)
    assert tv.parse_time("nonsense") is None


# (as in the real guide, every channel comes before the first programme)
GUIDE_WITH_RADIO = GUIDE.replace(b"  <programme ", b"""  <channel id="BBCRedButton1.uk"><display-name lang="en">BBC Red Button 1</display-name></channel>
  <channel id="ClassicFM.uk"><display-name lang="en">Classic FM</display-name></channel>
  <programme start="20261021140000 +0100" stop="20261021160000 +0100" channel="ClassicFM.uk"><title>Anne-Marie Minhall</title></programme>
  <programme """, 1)


def test_radio_stations_are_listed_on_their_own(tmp_path):
    path = tmp_path / "guide.xml"
    path.write_bytes(GUIDE_WITH_RADIO)
    assert [c.short_name for c in tv.read_channels(path, radio=True)] == ["BBC Radio Scotland", "Capital", "Classic FM"]
    assert "BBC Red Button 1" in [c.short_name for c in tv.read_channels(path)]  # (TV, though its id starts BBCR)
