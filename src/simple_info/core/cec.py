"""Letting the TV's remote control Simple-Info, over HDMI-CEC (Linux, e.g. a
Raspberry Pi behind the TV).

Registering as a CEC "playback device" makes the TV send its remote's
button presses down the HDMI cable; Linux turns them into ordinary key
presses (arrows, OK, back, the coloured buttons), which the app maps to
its controls. Needs cec-ctl (from v4l-utils).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

NAME = "Simple-Info"


def cec_devices() -> list[Path]:
    if not sys.platform.startswith("linux"):
        return []
    return sorted(Path("/dev").glob("cec[0-9]*"))


def register_with_tv() -> str:
    """Register on every HDMI-CEC port. Returns a line for the log; never raises."""
    devices = cec_devices()
    if not devices:
        return "no HDMI-CEC devices here"
    tool = shutil.which("cec-ctl")
    if not tool:
        return "cec-ctl not found (install v4l-utils)"
    results = []
    for dev in devices:
        try:
            done = subprocess.run([tool, "-d", str(dev), "--playback", "--osd-name", NAME],
                                  capture_output=True, text=True, timeout=10)
            results.append(f"{dev.name}: {'ok' if done.returncode == 0 else (done.stderr.strip() or done.returncode)}")
        except (OSError, subprocess.TimeoutExpired) as error:
            results.append(f"{dev.name}: {error}")
    return "HDMI-CEC " + ", ".join(results)
