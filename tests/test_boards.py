import os

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
