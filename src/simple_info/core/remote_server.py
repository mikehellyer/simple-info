"""The phone remote: a small web page served on the home network.

Pure Python (no Qt), so it can be tested on its own. The server runs on its
own thread. Commands from the page are put on a queue for the GUI thread to
carry out (it polls take_commands()), and the page's status comes from a
state() callable the GUI keeps up to date.
"""
from __future__ import annotations

import json
import queue
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Callable, Optional

DEFAULT_PORT = 8765

# What the page can ask for, and the values each accepts (None: any).
ACTIONS = {
    "board": None,  # a board's key: "weather", "trains", "sport"…
    "page": None,  # a page number (0, 1…), or "next" / "previous"
    "pause": ("toggle",),
    "cycle": ("toggle",),
    "refresh": ("now",),
    "fullscreen": ("toggle",),
}


def lan_address() -> str:
    """This machine's address on the home network (best guess)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # a reserved test address: nothing is actually sent
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def valid_command(action: str, value) -> bool:
    if action not in ACTIONS:
        return False
    allowed = ACTIONS[action]
    if action == "page":
        return value in ("next", "previous") or (isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 100)
    if allowed is None:
        return isinstance(value, str) and 0 < len(value) <= 40
    return value in allowed


class RemoteServer:
    def __init__(self, state: Callable[[], dict], port: int = DEFAULT_PORT, pin: str = "", host: str = "0.0.0.0"):
        self._state = state
        self.port = port
        self.pin = pin
        self._host = host
        self._commands: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.error = ""

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def url(self) -> str:
        return f"http://{lan_address()}:{self.port}/"

    def start(self) -> bool:
        if self.running:
            return True
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep quiet
                pass

            def _send(self, code: int, body: bytes, kind: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code: int, data: dict) -> None:
                self._send(code, json.dumps(data).encode(), "application/json")

            def _authorised(self) -> bool:
                return not server.pin or self.headers.get("X-Info-Pin", "") == server.pin

            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    self._send(200, _page(), "text/html; charset=utf-8")
                elif self.path == "/api/state":
                    if not self._authorised():
                        self._json(401, {"error": "pin"})
                        return
                    self._json(200, server._state())
                else:
                    self._json(404, {"error": "not found"})

            def do_POST(self):
                if self.path != "/api/command":
                    self._json(404, {"error": "not found"})
                    return
                if not self._authorised():
                    self._json(401, {"error": "pin"})
                    return
                try:
                    length = min(int(self.headers.get("Content-Length", "0")), 2000)
                    data = json.loads(self.rfile.read(length) or b"{}")
                    action, value = data.get("action"), data.get("value")
                except (ValueError, AttributeError):
                    self._json(400, {"error": "bad request"})
                    return
                if not valid_command(action, value):
                    self._json(400, {"error": "unknown command"})
                    return
                server._commands.put((action, value))
                self._json(200, {"ok": True})

        try:
            self._httpd = ThreadingHTTPServer((self._host, self.port), Handler)
        except OSError as error:
            self.error = str(error)
            self._httpd = None
            return False
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]  # (the real one, if 0 asked for any free port)
        self.error = ""
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    def take_commands(self) -> list[tuple[str, object]]:
        """Everything the page has asked for since last time."""
        out = []
        while True:
            try:
                out.append(self._commands.get_nowait())
            except queue.Empty:
                return out


def _page() -> bytes:
    return resources.files("simple_info.core").joinpath("remote.html").read_bytes()


def qr_matrix(text: str) -> list[list[bool]]:
    """The QR code for text, as rows of dark (True) / light modules,
    including the quiet border."""
    import qrcode

    code = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    code.add_data(text)
    code.make(fit=True)
    return code.get_matrix()
