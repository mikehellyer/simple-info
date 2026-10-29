import json

from simple_info.core.settings import Settings, SettingsStore


def test_defaults_when_no_file(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    assert store.settings == Settings()


def test_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    store.update(location_mode="manual", location_name="Keswick", latitude=54.6, longitude=-3.13, cycle_seconds=45)
    again = SettingsStore(path)
    assert again.settings.location_name == "Keswick" and again.settings.cycle_seconds == 45


def test_bad_values_are_ignored_or_clamped(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "temperature_unit": "K", "graphics": "ultra", "cycle_seconds": 1, "latitude": 12, "cycle_boards": "yes",
        "location_mode": "manual", "location_name": "",
    }))
    s = SettingsStore(path).settings
    assert s.temperature_unit == "C"
    assert s.graphics == "auto"
    assert s.cycle_seconds == 5
    assert s.latitude == 12.0
    assert s.cycle_boards is False
    assert s.location_mode == "auto"  # manual with no place falls back


def test_start_fullscreen_is_off_by_default_and_remembered(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    assert store.settings.start_fullscreen is False
    store.update(start_fullscreen=True)
    assert SettingsStore(path).settings.start_fullscreen is True


def test_an_unchanged_radio_list_moves_on_to_the_new_default_but_a_chosen_one_stays(tmp_path):
    old = "BBCRScotland.uk,BBCR1.uk,BBCR2.uk,BBCR3.uk,BBCR4FM.uk,BBCR5L.uk,BBCR6M.uk,ClassicFM.uk"
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"radio_channels": old}))
    s = SettingsStore(path).settings
    assert s.radio_channels == Settings().radio_channels and "bauer:mf1" in s.radio_channels and "bauer:ghs" in s.radio_channels
    path.write_text(json.dumps({"radio_channels": "ClassicFM.uk,BBCR4FM.uk"}))
    assert SettingsStore(path).settings.radio_channels == "ClassicFM.uk,BBCR4FM.uk"
