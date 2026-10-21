import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # Qt's GUI module can't load on some bare CI machines
    pytest.skip("Qt GUI not available", allow_module_level=True)

from simple_info.core import weather as wx
from simple_info.core.settings import Settings
from simple_info.gui.boards.base import Board
from simple_info.gui.boards.weather import WeatherBoard
from simple_info.gui.stage import Stage

from test_weather import PAYLOAD


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_fetch_schedule():
    board = Board()
    board.refresh_seconds, board.retry_seconds = 100, 10
    assert board.due(0.0)
    board.begin_fetch()
    assert not board.due(1000.0)  # not while a fetch is running
    board.end_fetch(True, now=50.0)
    assert not board.due(149.0) and board.due(150.0)
    board.begin_fetch()
    board.end_fetch(False, now=200.0)
    assert board.due(210.0)
    board.fetch_now()
    assert board.due(0.0)


def test_weather_board_takes_a_forecast_and_remembers_it(app, tmp_path):
    board = WeatherBoard(tmp_path)
    assert board.forecast is None and board.status
    forecast = wx.parse_forecast(PAYLOAD, "Keswick")
    assert board.on_fetched((wx.Location("Keswick", 54.6, -3.1), forecast)) is True
    assert board.forecast is forecast and board.status == ""
    assert WeatherBoard(tmp_path).forecast is not None  # cached for the next start
    assert board.on_fetched(None) is False
    assert "offline" in board.status and board.forecast is forecast


def test_weather_board_fetches_for_the_chosen_place(app, tmp_path, monkeypatch):
    board = WeatherBoard(tmp_path)
    board.configure(Settings())
    asked = []
    monkeypatch.setattr(wx, "locate_by_ip", lambda: None)
    monkeypatch.setattr(wx, "fetch_forecast", lambda loc: asked.append(loc.name))
    assert board.fetch_job()() == (None, None)  # nowhere known yet
    board.begin_fetch()
    board.end_fetch(True)
    board.configure(Settings(location_mode="manual", location_name="Keswick", latitude=54.6, longitude=-3.1))
    assert board.due()  # a new place is fetched straight away
    board.fetch_job()()
    assert asked == ["Keswick"]


def test_previews_cycle_back_to_live(app, tmp_path):
    board = WeatherBoard(tmp_path)
    seen = {board.cycle_weather_preview() for _ in range(len(wx.PREVIEWS) + 1)}
    assert board.weather_preview is None and "Live weather" in seen
    for _ in range(5):
        board.cycle_time_preview()
    assert board.time_preview is None


class _Plain(Board):
    key, title = "plain", "Plain"


def test_stage_switches_boards_and_draws_them(app, tmp_path):
    weather = WeatherBoard(tmp_path)
    weather.on_fetched((None, wx.parse_forecast(PAYLOAD, "Keswick")))
    stage = Stage([weather, _Plain()])
    stage.resize(800, 450)
    seen = []
    stage.board_changed.connect(seen.append)
    stage.next_board()
    stage.next_board()
    stage.previous_board()
    assert seen == ["plain", "weather", "plain"]
    assert stage.show_key("weather") and not stage.show_key("nope")
    for light in (False, True):
        stage.set_light_graphics(light)
        for _ in range(3):
            stage._tick()
        assert not stage.grab().isNull()


def test_stage_cycles_on_its_own(app, tmp_path):
    stage = Stage([_Plain(), WeatherBoard(tmp_path)])
    stage.cycle, stage.cycle_seconds = True, 0.05
    stage._on_board = 1.0
    stage._tick()
    assert stage.index == 1


def test_train_board_fetches_for_the_chosen_station(app, monkeypatch):
    from simple_info.core import trains as tr
    from simple_info.gui.boards.trains import TrainBoard

    from test_trains import PAYLOAD

    board = TrainBoard()
    board.configure(Settings())
    assert board.fetch_job() is None  # no station yet: nothing to fetch
    asked = []

    def fake_fetch(crs, kind, rows, filter_crs, token):
        asked.append((crs, kind, filter_crs))
        return tr.parse_board(PAYLOAD, kind)

    monkeypatch.setattr(tr, "fetch_board", fake_fetch)
    board.configure(Settings(train_station_crs="KGX", train_station_name="London Kings Cross", train_mode="both", train_filter_crs="YRK"))
    assert board.due()
    assert board.on_fetched(board.fetch_job()()) is True
    assert asked == [("KGX", tr.DEPARTURES, "YRK"), ("KGX", tr.ARRIVALS, "YRK")]
    assert board.showing(0) == tr.DEPARTURES and board.showing(25) == tr.ARRIVALS
    assert board.on_fetched({tr.DEPARTURES: None, tr.ARRIVALS: None}) is False
    assert board.offline and tr.DEPARTURES in board.boards  # keeps the last trains

    stage = Stage([board])
    stage.resize(800, 450)
    for _ in range(3):
        stage._tick()
    assert not stage.grab().isNull()


def test_currency_board_follows_the_settings(app, tmp_path, monkeypatch):
    from simple_info.core import currency as cx
    from simple_info.gui.boards.currency import CurrencyBoard

    from test_currency import COINS, SERIES

    asked = []

    def fake_fetch(base, codes, crypto):
        asked.append((base, codes, crypto))
        _, rates = cx.parse_series(SERIES, codes)
        return cx.Rates(base, "2026-10-20", rates, cx.parse_coins(COINS) if crypto else [], time.time())

    monkeypatch.setattr(cx, "fetch", fake_fetch)
    board = CurrencyBoard(tmp_path)
    board.configure(Settings(currency_codes="USD,EUR,GBP"))  # (GBP is the base: left out)
    assert board.on_fetched(board.fetch_job()()) is True
    assert asked == [("GBP", ["USD", "EUR"], True)]
    assert CurrencyBoard(tmp_path).rates is not None  # cached for the next start
    board.configure(Settings(currency_base="EUR", currency_codes="USD"))
    assert board.rates is None and board.due()  # a new base: the old rates no longer apply
    assert board.on_fetched(None) is False and "connection" in board.status

    board.on_fetched(fake_fetch("GBP", ["EUR", "USD"], True))
    stage = Stage([board])
    stage.resize(800, 450)
    for _ in range(3):
        stage._tick()
    assert not stage.grab().isNull()


def test_settings_tidy_the_currency_list(tmp_path):
    import json

    from simple_info.core.settings import SettingsStore

    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"currency_base": "XXX", "currency_codes": "USD,nope,EUR,USD"}))
    s = SettingsStore(path).settings
    assert s.currency_base == "GBP" and s.currency_codes == "USD,EUR"


def test_sport_board_pages_and_refresh_rate(app, monkeypatch):
    from simple_info.core import sports as sp
    from simple_info.gui.boards import sport as sport_board

    from test_sports import CRICKET, STANDINGS, board as scoreboard, event

    def fake(key, cache=None):
        if key.startswith("cricket"):
            return sp.fetch_cricket(key, lambda url: CRICKET)
        live = key == "soccer/eng.1"
        payload = scoreboard([event("1", "2026-10-18T14:00Z", "in" if live else "post", "Celtic", "Hearts", "2", "1", "62'"),
                              event("2", "2030-10-24T14:00Z", "pre", "Rangers", "Dundee")])
        return sp.CompetitionData(key, sp.BY_KEY[key].name, sp.parse_scoreboard(payload),
                                  sp.parse_standings(STANDINGS, sp.BY_KEY[key].sport), time.time())

    monkeypatch.setattr(sp, "fetch_competition", fake)
    b = sport_board.SportBoard()
    b.configure(Settings(sport_competitions="soccer/sco.1,baseball/mlb"))
    assert b.page_count() == 2
    assert b.on_fetched(b.fetch_job()()) is True
    assert b.refresh_seconds == sport_board.QUIET_REFRESH
    b.configure(Settings(sport_competitions="soccer/eng.1,soccer/sco.1"))
    b.on_fetched(b.fetch_job()())
    assert b.refresh_seconds == sport_board.LIVE_REFRESH  # a game is on: check every minute
    for d in b.data.values():
        d.fetched_at = time.time()
    asked = []
    monkeypatch.setattr(sp, "fetch_competition", lambda key, cache=None: asked.append(key))
    b.fetch_job()()
    assert asked == ["soccer/eng.1"]  # …but only the competition with the game on

    stage = Stage([b, _Plain()])
    stage.resize(800, 450)
    for _ in range(2):
        stage._tick()
    assert stage.turn_page(1) and b.page == 1
    assert stage.turn_page(1) and b.page == 0
    stage._on_page = 100.0  # time's up: on to the next page
    stage._tick()
    assert b.page == 1
    stage.cycle, stage._on_page = True, 100.0  # moving on by itself: after the last page, the next board
    stage._tick()
    assert stage.index == 1
    assert not stage.turn_page(1)  # (a board with one page has nothing to turn)
    b.configure(Settings(sport_competitions="cricket/international,baseball/mlb"))
    b.on_fetched(b.fetch_job()())
    stage.show_board(0)
    for page in range(2):
        b.set_page(page)
        stage._tick()
        assert not stage.grab().isNull()


def test_tv_board_pages_and_drawing(app, tmp_path, monkeypatch):
    from datetime import datetime, timezone

    from simple_info.core import tv
    from simple_info.gui.boards.tv import TvBoard, badge_colour

    from test_tv import GUIDE

    (tmp_path / "tv-guide.xml").write_bytes(GUIDE)
    monkeypatch.setattr(tv, "download_guide", lambda path, **k: path.exists())
    board = TvBoard(tmp_path)
    ids = ["BBCOneScotHD.uk", "STVNorth.uk"] + [f"X{i}.uk" for i in range(10)]
    board.configure(Settings(tv_channels=",".join(ids)))
    assert board.page_count() == 2
    now = datetime(2026, 10, 21, 13, 40, tzinfo=timezone.utc)
    assert board.on_fetched(tv.fetch(tmp_path, ids, now)) is True
    assert [c.id for c in board.listings.channels] == ["BBCOneScotHD.uk", "STVNorth.uk"]
    assert board.on_fetched(None) is False and board.listings is not None
    assert badge_colour("BBC One Scotland") != badge_colour("STV North")
    stage = Stage([board])
    stage.resize(800, 450)
    for page in range(2):
        board.set_page(page)
        stage._tick()
        assert not stage.grab().isNull()
