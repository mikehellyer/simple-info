"""Reading the TV remote's buttons straight from Linux (evdev).

Over HDMI-CEC, Linux turns the TV remote's buttons into key presses on an
input device of their own ("vc4-hdmi-0" and the like on a Pi). The arrows
are ordinary keys and reach the app through the desktop, but OK, Exit,
the coloured buttons and the number keys have no meaning to a desktop's
keyboard layout, so it drops them. Reading the device directly gets them
all. (Needs read access to /dev/input: Raspberry Pi OS's own user has it.)

Plain Python: a thread per device puts key codes on a queue, which the
GUI polls.
"""
from __future__ import annotations

import queue
import re
import struct
import threading
from pathlib import Path
from typing import Optional

EVENT = struct.Struct("llHHi")  # struct input_event: time (2 longs), type, code, value
EV_KEY = 1

# Linux key codes the TV remote's buttons arrive as (see linux/input-event-codes.h)
KEY_NAMES = {
    1: "KEY_ESC", 2: "KEY_1", 3: "KEY_2", 4: "KEY_3", 5: "KEY_4", 6: "KEY_5", 7: "KEY_6", 8: "KEY_7", 9: "KEY_8",
    10: "KEY_9", 11: "KEY_0", 28: "KEY_ENTER", 96: "KEY_KPENTER", 103: "KEY_UP", 105: "KEY_LEFT", 106: "KEY_RIGHT",
    108: "KEY_DOWN", 113: "KEY_MUTE", 114: "KEY_VOLUMEDOWN", 115: "KEY_VOLUMEUP", 119: "KEY_PAUSE", 128: "KEY_STOP",
    139: "KEY_MENU", 158: "KEY_BACK", 163: "KEY_NEXTSONG", 164: "KEY_PLAYPAUSE", 165: "KEY_PREVIOUSSONG",
    167: "KEY_RECORD", 168: "KEY_REWIND", 174: "KEY_EXIT", 207: "KEY_PLAY", 208: "KEY_FASTFORWARD",
    352: "KEY_OK", 353: "KEY_SELECT", 358: "KEY_INFO", 362: "KEY_PROGRAM", 365: "KEY_EPG", 370: "KEY_SUBTITLE",
    398: "KEY_RED", 399: "KEY_GREEN", 400: "KEY_YELLOW", 401: "KEY_BLUE", 402: "KEY_CHANNELUP", 403: "KEY_CHANNELDOWN",
    **{512 + n: f"KEY_NUMERIC_{n}" for n in range(10)},
}

# What each button does on the board. The arrows aren't here: they already
# reach the app through the desktop (◀ ▶ switch boards).
ACTIONS = {
    "KEY_OK": "next", "KEY_SELECT": "next", "KEY_CHANNELUP": "next", "KEY_NEXTSONG": "next",
    "KEY_EXIT": "previous", "KEY_BACK": "previous", "KEY_CHANNELDOWN": "previous", "KEY_PREVIOUSSONG": "previous",
    "KEY_INFO": "refresh", "KEY_EPG": "refresh",
    "KEY_PLAYPAUSE": "hold", "KEY_PAUSE": "hold", "KEY_PLAY": "hold",
    "KEY_RED": "cycle", "KEY_GREEN": "refresh", "KEY_YELLOW": "weather_preview", "KEY_BLUE": "phone_qr",
    **{f"KEY_NUMERIC_{n}": f"board_{n}" for n in range(1, 10)},
    **{f"KEY_{n}": f"board_{n}" for n in range(1, 10)},
}


def remote_input_devices(devices_file: Path = Path("/proc/bus/input/devices")) -> list[tuple[str, Path]]:
    """(name, /dev/input/eventN) for each HDMI-CEC remote-control input."""
    try:
        text = devices_file.read_text()
    except OSError:
        return []
    found = []
    for block in text.split("\n\n"):
        name = re.search(r'N: Name="([^"]*)"', block)
        handlers = re.search(r"H: Handlers=([^\n]*)", block)
        if not name or not handlers:
            continue
        if re.search(r"cec|hdmi", name.group(1), re.I):
            event = re.search(r"\b(event\d+)\b", handlers.group(1))
            if event:
                found.append((name.group(1), Path("/dev/input") / event.group(1)))
    return found


class TvKeyReader:
    """Reads key presses from the remote-control input devices."""

    def __init__(self):
        self.keys: "queue.Queue[str]" = queue.Queue()
        self.devices: list[tuple[str, Path]] = []
        self.errors: list[str] = []
        self._stop = threading.Event()

    def start(self, devices: Optional[list[tuple[str, Path]]] = None) -> bool:
        self.devices = remote_input_devices() if devices is None else devices
        started = False
        for name, path in self.devices:
            try:
                handle = open(path, "rb", buffering=0)
            except OSError as error:
                self.errors.append(f"{path} ({name}): {error}")
                continue
            threading.Thread(target=self._read, args=(handle,), daemon=True).start()
            started = True
        return started

    def _read(self, handle) -> None:
        with handle:
            while not self._stop.is_set():
                data = handle.read(EVENT.size)
                if not data or len(data) < EVENT.size:
                    return
                _, _, kind, code, value = EVENT.unpack(data)
                if kind == EV_KEY and value == 1:  # pressed (not released or held)
                    self.keys.put(KEY_NAMES.get(code, f"KEY_{code}"))

    def take(self) -> list[str]:
        out = []
        while True:
            try:
                out.append(self.keys.get_nowait())
            except queue.Empty:
                return out

    def stop(self) -> None:
        self._stop.set()
