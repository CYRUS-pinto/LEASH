"""Tests for Acceptance Criterion 1:
`make demo` starts gateway + tool server + dashboard; one command, no manual DB setup.
"""

import subprocess
import sys
from pathlib import Path
import pytest
from leash.config import BASE_DIR


def test_make_demo_smoke():
    python_bin = sys.executable
    res = subprocess.run(
        [python_bin, "run_demo.py", "--test"],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert res.returncode == 0
    assert "LEASH Action-Control Gateway is LIVE" in res.stdout
    assert "Both services are healthy" in res.stdout
