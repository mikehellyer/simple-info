import json
from unittest.mock import patch

from simple_info.core import trains as tr

PAYLOAD = {
    "locationName": "London Kings Cross",
    "crs": "KGX",
    "nrccMessages": [{"value": "Trains to <b>Newcastle</b> may be delayed.<br>See the <a href=\"x\">National Rail website</a>."}],
    "trainServices": [
        {
            "std": "11:40", "etd": "11:50", "platform": "0", "operator": "LNER", "length": 9,
            "isCancelled": False, "delayReason": "This service has been delayed by a fault",
            "origin": [{"locationName": "London Kings Cross", "crs": "KGX"}],
            "destination": [{"locationName": "Bradford Forster Square", "crs": "BDQ", "via": "via Leeds"}],
            "subsequentCallingPoints": [{"callingPoint": [
                {"locationName": "Doncaster", "st": "13:16", "et": "13:19"},
                {"locationName": "Leeds", "st": "13:49", "et": "On time"},
            ]}],
        },
        {
            "std": "11:47", "etd": "On time", "operator": "LNER",
            "destination": [{"locationName": "York"}], "origin": [{"locationName": "London Kings Cross"}],
        },
        {
            "std": "11:54", "etd": "Cancelled", "isCancelled": True, "cancelReason": "A shortage of train crew",
            "destination": [{"locationName": "Kings Lynn"}, {"locationName": "Ely"}],
        },
        {"std": "12:00", "etd": "Delayed", "destination": [{"locationName": "Hull"}]},
    ],
}


def test_parse_departures():
    board = tr.parse_board(PAYLOAD, tr.DEPARTURES, fetched_at=5.0)
    assert (board.station, board.crs, board.kind, board.fetched_at) == ("London Kings Cross", "KGX", tr.DEPARTURES, 5.0)
    first, second, third, fourth = board.services
    assert (first.scheduled, first.destination, first.via, first.platform, first.coaches) == ("11:40", "Bradford Forster Square", "via Leeds", "0", 9)
    assert first.status == tr.LATE and first.expected_text == "Exp 11:50" and "fault" in first.reason
    assert second.status == tr.ON_TIME and second.expected_text == "On time" and second.platform == ""
    assert third.status == tr.CANCELLED and third.expected_text == "Cancelled" and third.destination == "Kings Lynn & Ely"
    assert third.reason == "A shortage of train crew"
    assert fourth.status == tr.LATE and fourth.expected_text == "Delayed"
    assert board.messages == ["Trains to Newcastle may be delayed. See the National Rail website."]
    assert tr.calling_at_text(first, tr.DEPARTURES) == "Calling at: Doncaster (13:19) and Leeds (13:49)."
    assert tr.calling_at_text(second, tr.DEPARTURES) == ""


def test_parse_arrivals_uses_arrival_times_and_previous_stops():
    payload = {"locationName": "Edinburgh", "crs": "EDB", "trainServices": [{
        "sta": "10:38", "eta": "11:52", "origin": [{"locationName": "London Kings Cross"}],
        "destination": [{"locationName": "Edinburgh"}],
        "previousCallingPoints": [{"callingPoint": [
            {"locationName": "London Kings Cross", "st": "06:00", "at": "06:00"},
            {"locationName": "York", "st": "08:36", "at": "08:40"},
            {"locationName": "Newcastle", "st": "10:26", "et": "11:30"},
        ]}],
    }]}
    board = tr.parse_board(payload, tr.ARRIVALS)
    s = board.services[0]
    assert (s.scheduled, s.expected_text, s.origin) == ("10:38", "Exp 11:52", "London Kings Cross")
    assert tr.calling_at_text(s, tr.ARRIVALS) == "From London Kings Cross, calling at York (08:40) and Newcastle (11:30)."


def test_parse_copes_with_missing_and_odd_fields():
    board = tr.parse_board({"locationName": "Nowhere", "trainServices": None, "nrccMessages": None}, tr.DEPARTURES)
    assert board.services == [] and board.messages == []
    board = tr.parse_board({"locationName": "X", "trainServices": [{"std": None, "destination": None}, "junk"]}, tr.DEPARTURES)
    assert board.services[0].destination == "Unknown" and board.services[0].expected_text == "—"


def test_board_url():
    assert tr.board_url("kgx", tr.DEPARTURES, 10, base_url="https://h") == "https://h/departures/KGX/10?expand=true"
    assert tr.board_url("EDB", tr.ARRIVALS, 5, "yrk", "https://h/") == "https://h/arrivals/EDB/from/YRK/5?expand=true"
    assert tr.board_url("EDB", tr.DEPARTURES, 5, "yrk", base_url="https://h").startswith("https://h/departures/EDB/to/YRK/5")


class _Response:
    def __init__(self, data):
        self._data = json.dumps(data).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_board_returns_none_when_offline_or_bad_code():
    assert tr.fetch_board("toolong", tr.DEPARTURES) is None
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert tr.fetch_board("KGX", tr.DEPARTURES) is None
    with patch("urllib.request.urlopen", return_value=_Response(PAYLOAD)):
        assert len(tr.fetch_board("KGX", tr.DEPARTURES).services) == 4


def test_search_stations_ranks_the_best_match_first():
    found = [{"stationName": "Bramley (West Yorkshire)", "crsCode": "BLE"}, {"stationName": "York", "crsCode": "YRK"},
             {"stationName": "Richmond, Nth Yorks (Bus)", "crsCode": "RMK"}]
    with patch("urllib.request.urlopen", return_value=_Response(found)):
        assert [s.crs for s in tr.search_stations("york")] == ["YRK", "BLE", "RMK"]
    # a code that the name search doesn't know is looked up through its board
    responses = iter([_Response([]), _Response({"locationName": "London Kings Cross", "crs": "KGX"})])
    with patch("urllib.request.urlopen", side_effect=lambda *a, **k: next(responses)):
        assert tr.search_stations("kgx") == [tr.Station("London Kings Cross", "KGX")]
    assert tr.search_stations("  ") == []


class _Http:
    def __init__(self, data, code=200):
        self._data = json.dumps(data).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_departures_come_from_national_rail_with_your_key_and_never_send_it_to_huxley():
    sent = []

    def fake(request, **kwargs):
        sent.append((request.full_url, dict(request.header_items())))
        return _Http(PAYLOAD)

    with patch("urllib.request.urlopen", side_effect=fake):
        board = tr.fetch_board("KGX", tr.DEPARTURES, 10, "yrk", key="secret-key")
    assert board.source == "National Rail" and board.note == "" and len(board.services) == 4
    url, headers = sent[0]
    assert url.startswith(tr.RDM_DEPARTURES_URL + "/GetDepBoardWithDetails/KGX") and "filterCrs=YRK" in url
    assert headers.get("X-apikey") == "secret-key" and "secret-key" not in url
    sent.clear()
    with patch("urllib.request.urlopen", side_effect=fake):
        board = tr.fetch_board("KGX", tr.ARRIVALS, 10, key="secret-key")  # arrivals: Huxley, without the key
    assert board.source == "Huxley 2"
    assert all("secret-key" not in u and "secret-key" not in h.values() for u, h in sent) and "huxley2" in sent[0][0]


def test_a_refused_key_falls_back_to_huxley_and_says_so():
    import urllib.error

    def fake(request, **kwargs):
        if "raildata" in request.full_url:
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)
        assert "secret" not in str(request.header_items())
        return _Http(PAYLOAD)

    with patch("urllib.request.urlopen", side_effect=fake):
        board = tr.fetch_board("KGX", tr.DEPARTURES, key="secret")
        assert tr.fetch_rdm_departures("KGX", "secret")[0] == tr.KEY_REFUSED
    assert board.source == "Huxley 2" and board.note == "National Rail refused your key"
    with patch("urllib.request.urlopen", return_value=_Http({"fault": {"faultstring": "Invalid ApiKey"}})):
        assert tr.fetch_rdm_departures("KGX", "bad") == (tr.KEY_REFUSED, None)
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert tr.fetch_rdm_departures("KGX", "k") == (tr.KEY_UNREACHABLE, None)


def test_marketplace_messages_use_a_capital_v():
    board = tr.parse_board({"locationName": "X", "nrccMessages": [{"Value": "\nDelays <a href='x'>here</a>."}]}, tr.DEPARTURES)
    assert board.messages == ["Delays here."]
