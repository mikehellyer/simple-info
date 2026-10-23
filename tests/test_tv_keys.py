
from simple_info.core import tv_keys

DEVICES = """I: Bus=0011 Vendor=0001 Product=0001 Version=ab41
N: Name="AT Translated Set 2 keyboard"
H: Handlers=sysrq kbd event3 leds

I: Bus=0000 Vendor=0000 Product=0000 Version=0001
N: Name="vc4-hdmi-0"
P: Phys=vc4-hdmi-0/input0
H: Handlers=kbd event5

"""


def test_finds_the_cec_remote_input(tmp_path):
    f = tmp_path / "devices"
    f.write_text(DEVICES)
    assert tv_keys.remote_input_devices(f) == [("vc4-hdmi-0", tv_keys.Path("/dev/input/event5"))]


def test_reads_key_presses_only(tmp_path):
    fifo = tmp_path / "event0"
    events = b"".join(tv_keys.EVENT.pack(0, 0, t, code, value) for t, code, value in (
        (1, 352, 1),  # OK pressed
        (1, 352, 0),  # released
        (0, 0, 0),  # a sync event
        (1, 398, 1),  # red pressed
        (1, 398, 2),  # held (repeat)
    ))
    fifo.write_bytes(events)
    reader = tv_keys.TvKeyReader()
    assert reader.start([("test", fifo)])
    import time
    for _ in range(50):
        if reader.keys.qsize() >= 2:
            break
        time.sleep(0.01)
    assert reader.take() == ["KEY_OK", "KEY_RED"]


def test_buttons_map_to_board_actions():
    assert tv_keys.ACTIONS["KEY_OK"] == "next"
    assert tv_keys.ACTIONS["KEY_EXIT"] == "previous"
    assert tv_keys.ACTIONS["KEY_NUMERIC_3"] == "board_3"
    assert tv_keys.ACTIONS["KEY_RED"] == "cycle"


def test_arrows_are_read_directly_too():
    # (they reach the app through the desktop only while it has the focus)
    assert tv_keys.ACTIONS["KEY_LEFT"] == "previous" and tv_keys.ACTIONS["KEY_RIGHT"] == "next"
    assert tv_keys.ACTIONS["KEY_UP"] == "page_previous" and tv_keys.ACTIONS["KEY_DOWN"] == "page_next"
    assert tv_keys.ACTIONS["KEY_ENTER"] == "next"


def test_playback_buttons_work_the_board_when_a_tv_sends_nothing_else():
    a = tv_keys.ACTIONS
    assert (a["KEY_PREVIOUSSONG"], a["KEY_NEXTSONG"]) == ("previous", "next")
    assert (a["KEY_REWIND"], a["KEY_FASTFORWARD"]) == ("page_previous", "page_next")
    assert a["KEY_STOP"] == "hold"


def test_registering_asks_the_tv_for_its_navigation_keys(monkeypatch):
    from pathlib import Path
    from simple_info.core import cec

    ran = []

    class Done:
        returncode, stderr = 0, ""

    monkeypatch.setattr(cec, "cec_devices", lambda: [Path("/dev/cec0")])
    monkeypatch.setattr(cec.shutil, "which", lambda name: "/usr/bin/cec-ctl")
    monkeypatch.setattr(cec.subprocess, "run", lambda args, **k: ran.append(args) or Done())
    assert "menu announced" in cec.register_with_tv()
    assert "--playback" in ran[0] and "--rc-src-dev-root" in ran[0]
    assert ran[1][-2:] == ["--menu-status", "menu-state=activated"] and "--active-source" not in " ".join(ran[1])
