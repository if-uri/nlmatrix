"""Gen 5 live — opt-in: runs the SAME checker as offline Gen 5 against the real
dashboard. Skips cleanly when :8194 is not running, so it never reddens CI; when
the dashboard is up it asserts the deployed system is honest on cross-target
routing (unreachable target → block, explicit node wins, never a silent host run).
"""
import socket

import pytest

import gen5_live as live


def _dashboard_up(host="127.0.0.1", port=8194) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@pytest.mark.skipif(not _dashboard_up(), reason="dashboard :8194 not running (live test is opt-in)")
def test_live_cross_target_is_honest():
    assert live.main([]) == 0, "live cross-target routing violated a Gen 5 invariant"
