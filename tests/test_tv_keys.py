
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
