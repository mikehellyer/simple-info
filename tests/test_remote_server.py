import json
import urllib.error
import urllib.request

import pytest

from simple_info.core import remote_server
from simple_info.core.remote_server import RemoteServer, valid_command


@pytest.fixture
def server():
    state = {"board": "weather", "paused": False}
    s = RemoteServer(lambda: state, port=0, host="127.0.0.1")
    assert s.start()
    yield s
    s.stop()


def call(server, path, body=None, pin=""):
    url = f"http://127.0.0.1:{server.port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"X-Info-Pin": pin, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_serves_the_page_and_the_state(server):
    status, body = call(server, "/")
    assert status == 200 and b"Info Remote" in body
    status, body = call(server, "/api/state")
    assert status == 200 and json.loads(body)["board"] == "weather"


def test_commands_are_queued_for_the_gui(server):
    assert call(server, "/api/command", {"action": "board", "value": "sport"})[0] == 200
    assert call(server, "/api/command", {"action": "page", "value": 3})[0] == 200
    assert call(server, "/api/command", {"action": "pause", "value": "toggle"})[0] == 200
    assert server.take_commands() == [("board", "sport"), ("page", 3), ("pause", "toggle")]
    assert server.take_commands() == []


def test_unknown_or_bad_commands_are_refused(server):
    assert call(server, "/api/command", {"action": "format_disk", "value": "now"})[0] == 400
    assert call(server, "/api/command", {"action": "pause", "value": "forever"})[0] == 400
    assert call(server, "/api/command", {"action": "page", "value": 400})[0] == 400
    assert server.take_commands() == []


def test_pin_is_required_when_set():
    s = RemoteServer(lambda: {"ok": True}, port=0, pin="1234", host="127.0.0.1")
    assert s.start()
    try:
        assert call(s, "/api/state")[0] == 401
        assert call(s, "/api/command", {"action": "refresh", "value": "now"})[0] == 401
        assert call(s, "/api/state", pin="1234")[0] == 200
        assert call(s, "/")[0] == 200  # the page itself loads, then asks for the PIN
    finally:
        s.stop()


def test_valid_commands():
    assert valid_command("board", "trains")
    assert valid_command("page", "next") and valid_command("page", 0)
    assert not valid_command("page", True) and not valid_command("page", "sideways")
    assert valid_command("cycle", "toggle") and not valid_command("chime", "now")


def test_qr_code_and_address():
    matrix = remote_server.qr_matrix("http://192.168.1.20:8765/")
    assert len(matrix) == len(matrix[0]) >= 21
    assert remote_server.lan_address().count(".") == 3
