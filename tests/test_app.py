import sys
from unittest.mock import patch

from simple_info import app


def test_self_test_passes():
    with patch.object(sys, "argv", ["Simple-Info", "--self-test"]):
        assert app.main() == 0
