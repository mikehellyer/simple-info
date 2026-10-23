"""`Simple-Info --remote-test`: check both remote controls and print a
report (for working out why the TV remote or the phone page isn't working)."""
from __future__ import annotations

import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from simple_info.core import cec
from simple_info.core.remote_server import RemoteServer, lan_address
from simple_info.core.settings import SettingsStore


def say(text: str = "") -> None:
    print(text, flush=True)


def _run(args: list[str], seconds: float = 10) -> str:
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=seconds)
        return (done.stdout + done.stderr).strip()
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return out.strip()
    except OSError as error:
        return f"(couldn't run {args[0]}: {error})"


def all_addresses() -> list[str]:
    """Every IPv4 address this machine has, besides loopback."""
    found = set()
    if shutil.which("hostname"):
        for part in _run(["hostname", "-I"]).split():
            if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", part):
                found.add(part)
    found.add(lan_address())
    return sorted(a for a in found if not a.startswith("127."))


def check_tv() -> None:
    say("== TV remote (HDMI-CEC) ==")
    devices = cec.cec_devices()
    say(f"CEC devices: {', '.join(str(d) for d in devices) or 'none'}")
    if not devices:
        say("  -> No HDMI-CEC here. On a Raspberry Pi with Raspberry Pi OS (Bookworm) /dev/cec0 should exist.")
        return
    tool = shutil.which("cec-ctl")
    say(f"cec-ctl: {tool or 'NOT INSTALLED'}")
    if not tool:
        say("  -> Install it with:  sudo apt install v4l-utils")
        return
    for dev in devices:
        say(f"-- {dev} --")
        out = _run(cec.register_args(tool, dev))
        if "Physical Address" not in out:
            out = _run(cec.register_args(tool, dev, menus=False))
        menu = _run(cec.menu_status_args(tool, dev))
        say(f"told the TV our menu is open: {'yes' if 'Transmit' in menu or 'OK' in menu or not menu else menu[:200]}")
        phys = re.search(r"Physical Address\s*:\s*([0-9a-f.]+)", out)
        logical = re.search(r"Logical Address\s*:\s*(\d+)", out)
        say(f"registered as playback device: physical address {phys.group(1) if phys else '?'}, "
            f"logical address {logical.group(1) if logical else '?'}")
        if phys and phys.group(1) == "f.f.f.f":
            say("  -> f.f.f.f means nothing is connected on this HDMI port (try the other one).")
            continue
        topology = _run([tool, "-d", str(dev), "-S"], 20)
        tv_lines = [line.strip() for line in topology.splitlines() if re.search(r"(TV|Television|OSD Name|Vendor|Power Status)", line)]
        say("devices the TV reports on HDMI:")
        for line in tv_lines[:12] or ["(none — the TV didn't answer: is HDMI-CEC switched on in the TV's settings?)"]:
            say(f"    {line}")
    say("input devices made for remote controls:")
    try:
        names = re.findall(r'N: Name="([^"]+)"', Path("/proc/bus/input/devices").read_text())
        cec_inputs = [n for n in names if re.search(r"cec|hdmi", n, re.I)]
        say("    " + (", ".join(cec_inputs) or "none found"))
    except OSError:
        say("    (couldn't read /proc/bus/input/devices)")
    dev = next((d for d in devices if "f.f.f.f" not in _run([tool, "-d", str(d)])), devices[0])
    say()
    from simple_info.core.tv_keys import ACTIONS, TvKeyReader

    reader = TvKeyReader()
    reading = reader.start()
    say(f"Now press some buttons on the TV remote (arrows, OK, back, the coloured ones) for 15 seconds…")
    monitor = _run([tool, "-d", str(dev), "-M"], 15)
    keys = reader.take()
    reader.stop()
    say(f"Linux key presses from the remote: {', '.join(keys) or 'none'}")
    if not reading:
        say(f"  -> couldn't read the remote's input device: {'; '.join(reader.errors) or 'none found'}")
    unknown = sorted({k for k in keys if k not in ACTIONS})
    if unknown:
        say(f"  (not used by Simple-Info yet: {', '.join(unknown)})")
    presses = re.findall(r"USER_CONTROL_PRESSED.*?(?:ui-cmd|ui_cmd)[^:]*:\s*([\w\- ]+)", monitor, re.S)
    received = len(re.findall(r"USER_CONTROL_PRESSED", monitor))
    say(f"button presses the TV sent: {received}")
    if presses:
        say("    " + ", ".join(p.strip() for p in presses[:20]))
    elif received == 0:
        say("  -> The TV sent nothing. Check HDMI-CEC is on in the TV's settings, the Pi's input is the one showing,")
        say("     and try switching the TV off and on again (some TVs only list new devices then).")
    other = [line for line in monitor.splitlines() if "Received from" in line][:6]
    if other:
        say("other messages from the TV:")
        for line in other:
            say(f"    {line.strip()}")


def check_phone() -> None:
    say("== Phone remote ==")
    settings = SettingsStore().settings
    say(f"phone remote setting: {'on' if settings.phone_remote else 'OFF (turn it on in Settings → Phone remote)'}")
    port = settings.remote_port
    addresses = all_addresses()
    say(f"this machine's addresses: {', '.join(addresses) or 'none'}")
    say(f"hostname: {socket.gethostname()}  (so also http://{socket.gethostname()}.local:{port}/ on most phones)")
    server = RemoteServer(lambda: {"ok": True}, port=port)
    if server.start():
        own = "free (Simple-Info isn't running, or its phone remote is off)"
    else:
        own = f"in use: {server.error}  (normally that's Simple-Info itself, running)"
    say(f"port {port}: {own}")
    for address in addresses:
        try:
            with urllib.request.urlopen(f"http://{address}:{port}/", timeout=3) as r:
                ok = b"Info Remote" in r.read()
            say(f"    http://{address}:{port}/  -> {'reachable, page OK' if ok else 'answers, but not the Simple-Info page?'}")
        except OSError as error:
            say(f"    http://{address}:{port}/  -> NOT reachable from this machine ({error})")
    server.stop()
    firewall = _run(["sh", "-c", "command -v ufw >/dev/null && ufw status 2>/dev/null | head -1"])
    if firewall:
        say(f"firewall: {firewall}")
    say("If it's reachable here but not from the phone: make sure the phone is on the same Wi-Fi (not a guest")
    say("network, and not on mobile data), and that the router doesn't keep devices apart ('AP/client isolation').")


def main() -> int:
    from simple_info import __version__

    say(f"Simple-Info {__version__} remote test")
    say()
    if sys.platform.startswith("linux"):
        check_tv()
    else:
        say("== TV remote: HDMI-CEC is only supported on Linux (e.g. a Raspberry Pi) ==")
    say()
    check_phone()
    return 0
