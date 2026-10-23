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


# Telling the TV that we have menus to find our way round (CEC 2.0's remote
# control profile) makes many TVs send the arrows and OK as well as the
# playback buttons; older TVs go by <Menu Status> "activated" instead.
MENU_FEATURES = ["--rc-src-dev-root", "--rc-src-contents", "--rc-src-media-top", "--rc-src-media-context"]


def register_args(tool: str, dev: Path, menus: bool = True) -> list[str]:
    return [tool, "-d", str(dev), "--playback", "--osd-name", NAME] + (MENU_FEATURES if menus else [])


def menu_status_args(tool: str, dev: Path) -> list[str]:
    """Tell the TV our menu is open (it then passes on its navigation keys).
    (Not <Active Source>, which would switch the TV over to us.)"""
    return [tool, "-d", str(dev), "--to", "0", "--menu-status", "menu-state=activated"]


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
            done = subprocess.run(register_args(tool, dev), capture_output=True, text=True, timeout=10)
            if done.returncode != 0:  # an older cec-ctl without the menu options: plain registration
                done = subprocess.run(register_args(tool, dev, menus=False), capture_output=True, text=True, timeout=10)
            result = "ok" if done.returncode == 0 else (done.stderr.strip() or str(done.returncode))
            menu = subprocess.run(menu_status_args(tool, dev), capture_output=True, text=True, timeout=10)
            result += ", menu announced" if menu.returncode == 0 else f", menu not announced ({menu.stderr.strip() or menu.returncode})"
            results.append(f"{dev.name}: {result}")
        except (OSError, subprocess.TimeoutExpired) as error:
            results.append(f"{dev.name}: {error}")
    return "HDMI-CEC " + ", ".join(results)
