"""Keeping the screen awake: no screensaver, no blanking, no lock, while
Simple-Info is open.

Each platform has its own way of asking:
- Linux: over D-Bus, trying the freedesktop screensaver service (KDE,
  COSMIC, Xfce…), then the desktop portal, then GNOME's session manager.
- macOS: the built-in `caffeinate` tool, tied to this process.
- Windows: SetThreadExecutionState, as video players do.

Never raises: if nothing works Simple-Info simply runs as before.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional

APP = "Simple-Info"
REASON = "Showing the information board"

_ES_CONTINUOUS, _ES_SYSTEM_REQUIRED, _ES_DISPLAY_REQUIRED = 0x80000000, 0x00000001, 0x00000002
_IDLE, _SUSPEND = 8, 4  # inhibit flags, as the portal and GNOME count them


class KeepAwake:
    def __init__(self):
        self.method: Optional[str] = None  # how it's being kept awake, for the log
        self._conn = None
        self._release = None

    @property
    def active(self) -> bool:
        return self.method is not None

    def start(self) -> Optional[str]:
        if self.active:
            return self.method
        try:
            if sys.platform == "win32":
                self._start_windows()
            elif sys.platform == "darwin":
                self._start_macos()
            else:
                self._start_linux()
        except Exception:
            self.method, self._release = None, None
        return self.method

    def stop(self) -> None:
        if self._release is not None:
            try:
                self._release()
            except Exception:
                pass
        self.method, self._release = None, None

    # --- Windows

    def _start_windows(self) -> None:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        if kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED):
            self.method = "SetThreadExecutionState"
            self._release = lambda: kernel32.SetThreadExecutionState(_ES_CONTINUOUS)

    # --- macOS

    def _start_macos(self) -> None:
        # -d: keep the display awake, -i: and the system; -w: until we exit.
        process = subprocess.Popen(["caffeinate", "-d", "-i", "-w", str(os.getpid())])
        self.method = "caffeinate"
        self._release = process.terminate

    # --- Linux

    def _start_linux(self) -> None:
        from jeepney import DBusAddress, new_method_call
        from jeepney.io.blocking import open_dbus_connection

        conn = open_dbus_connection(bus="SESSION")

        def call(address, method, signature, body):
            reply = conn.send_and_get_reply(new_method_call(address, method, signature, body), timeout=2)
            if reply.header.message_type.name == "error":
                raise RuntimeError(reply.body)
            return reply.body

        screensaver = DBusAddress("/org/freedesktop/ScreenSaver", bus_name="org.freedesktop.ScreenSaver",
                                  interface="org.freedesktop.ScreenSaver")

        def via_screensaver():
            cookie = call(screensaver, "Inhibit", "ss", (APP, REASON))[0]
            return lambda: call(screensaver, "UnInhibit", "u", (cookie,))

        portal = DBusAddress("/org/freedesktop/portal/desktop", bus_name="org.freedesktop.portal.Desktop",
                             interface="org.freedesktop.portal.Inhibit")

        def via_portal():
            handle = call(portal, "Inhibit", "sua{sv}", ("", _IDLE | _SUSPEND, {"reason": ("s", REASON)}))[0]
            request = DBusAddress(handle, bus_name="org.freedesktop.portal.Desktop", interface="org.freedesktop.portal.Request")
            return lambda: call(request, "Close", "", ())

        gnome = DBusAddress("/org/gnome/SessionManager", bus_name="org.gnome.SessionManager", interface="org.gnome.SessionManager")

        def via_gnome():
            cookie = call(gnome, "Inhibit", "susu", (APP, 0, REASON, _IDLE | _SUSPEND))[0]
            return lambda: call(gnome, "Uninhibit", "u", (cookie,))

        attempts = [("freedesktop ScreenSaver", via_screensaver), ("desktop portal", via_portal), ("GNOME session", via_gnome)]
        for name, attempt in attempts:
            try:
                release = attempt()
            except Exception:
                continue
            # The inhibit lasts as long as this connection, so keep it open.
            self._conn = conn
            self.method = name

            def release_and_close(release=release):
                try:
                    release()
                finally:
                    conn.close()
                    self._conn = None

            self._release = release_and_close
            return
        conn.close()
