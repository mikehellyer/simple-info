from unittest.mock import MagicMock, patch

from simple_info.core import platform_info
from simple_info.core.keep_awake import KeepAwake


def test_macos_runs_caffeinate_tied_to_this_process():
    process = MagicMock()
    with patch("simple_info.core.keep_awake.sys.platform", "darwin"), patch(
        "simple_info.core.keep_awake.subprocess.Popen", return_value=process
    ) as popen:
        k = KeepAwake()
        assert k.start() == "caffeinate"
        args = popen.call_args.args[0]
        assert args[:4] == ["caffeinate", "-d", "-i", "-w"]
        k.stop()
    process.terminate.assert_called_once()
    assert not k.active


def test_failure_is_quiet():
    with patch("simple_info.core.keep_awake.sys.platform", "darwin"), patch(
        "simple_info.core.keep_awake.subprocess.Popen", side_effect=OSError("no caffeinate")
    ):
        k = KeepAwake()
        assert k.start() is None
        assert not k.active
        k.stop()  # harmless


def test_raspberry_pi_detection(tmp_path):
    model = tmp_path / "model"
    model.write_text("Raspberry Pi 5 Model B Rev 1.0\x00")
    assert platform_info.is_raspberry_pi(model)
    model.write_text("Some PC")
    assert not platform_info.is_raspberry_pi(model)
    assert not platform_info.is_raspberry_pi(tmp_path / "missing")


def test_debian_arch_names():
    assert platform_info.debian_arch("x86_64") == "amd64"
    assert platform_info.debian_arch("aarch64") == "arm64"
