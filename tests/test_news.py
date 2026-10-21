from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from simple_info.core import news as nw

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:media="http://search.yahoo.com/mrss/" xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0"><channel>
<title>BBC News</title>
<item><title>Search resumes for missing fishermen</title><description>Two men have been missing since Sunday.</description>
  <link>https://www.bbc.co.uk/news/a1</link><pubDate>Wed, 21 Oct 2026 09:58:42 GMT</pubDate>
  <media:thumbnail width="240" height="134" url="https://ichef.bbci.co.uk/ace/standard/240/cpsprodpb/ce6a/live/x.jpg"/></item>
<item><title>A Guardian &amp; friends story</title><description>&lt;p&gt;Student activists &lt;a href="x"&gt;seem&lt;/a&gt; set&lt;/p&gt;</description>
  <dc:date>2026-10-21T07:00:04Z</dc:date>
  <media:content width="140" url="https://i.guim.co.uk/small.jpg"/><media:content width="700" url="https://i.guim.co.uk/big.jpg"/></item>
<item><title>Sky story</title><enclosure url="https://e3.365dm.com/26/10/1920x1080/pic.jpg" type="image/jpeg"/></item>
<item><title></title></item>
</channel></rss>"""


class _Response:
    def __init__(self, data):
        self._data = data

    def read(self, n=-1):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_parse_feed_reads_titles_summaries_times_and_pictures():
    bbc, guardian, sky = nw.parse_feed(FEED, "BBC News")
    assert (bbc.title, bbc.summary, bbc.source) == ("Search resumes for missing fishermen", "Two men have been missing since Sunday.", "BBC News")
    assert bbc.published == datetime(2026, 10, 21, 9, 58, 42, tzinfo=timezone.utc)
    assert guardian.title == "A Guardian & friends story" and guardian.summary == "Student activists seem set"
    assert guardian.image == "https://i.guim.co.uk/big.jpg" and guardian.published.year == 2026
    assert sky.image.endswith("1920x1080/pic.jpg") and sky.published is None
    assert nw.parse_feed(b"not xml") == []


def test_pictures_are_asked_for_at_a_sensible_size():
    assert nw.sized("https://ichef.bbci.co.uk/ace/standard/240/cpsprodpb/x.jpg", 480) == "https://ichef.bbci.co.uk/ace/standard/480/cpsprodpb/x.jpg"
    assert nw.sized("https://e3.365dm.com/26/10/1920x1080/pic.jpg", 240) == "https://e3.365dm.com/26/10/384x216/pic.jpg"
    assert nw.sized("https://i.guim.co.uk/big.jpg", 240) == "https://i.guim.co.uk/big.jpg"


def test_fetch_feed_and_ago():
    with patch("urllib.request.urlopen", return_value=_Response(FEED)):
        assert len(nw.fetch_feed("bbc/scotland")) == 3
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert nw.fetch_feed("bbc/scotland") is None
    assert nw.fetch_feed("nope") is None
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    assert nw.ago(now - timedelta(seconds=30), now) == "just now"
    assert nw.ago(now - timedelta(minutes=12), now) == "12 min ago"
    assert nw.ago(now - timedelta(hours=1, minutes=5), now) == "1 hour ago"
    assert nw.ago(now - timedelta(hours=5), now) == "5 hours ago"
    assert nw.ago(None, now) == ""
