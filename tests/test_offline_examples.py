"""Smoke-test the examples that promise offline, deterministic runs.

``examples/demo.py``, ``examples/offline_testing.py``,
``examples/smart_services.py``, and ``examples/mcp_tools.py`` are the
four examples the README's no-setup story relies on (no model server, no
API key, no network). They must keep exiting 0 with their promised output
markers. ``mcp_tools.py`` additionally needs the optional ``[mcp]``
extra; it is skipped when fastmcp is not installed so a bare dev
environment can still run this gate.
The live-endpoint examples (``quickstart.py``, ``streaming_events.py``,
``custom_tools.py``) target a real OpenAI-compatible server; they degrade
gracefully without one and are intentionally not run here.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

OFFLINE_EXAMPLES = {
    "demo.py": "real engine output",
    "offline_testing.py": "deterministic run passed",
    "smart_services.py": "real engine output",
    "mcp_tools.py": "real engine output",
}


def test_offline_examples_run_clean() -> None:
    for name, marker in OFFLINE_EXAMPLES.items():
        if name == "mcp_tools.py" and importlib.util.find_spec("fastmcp") is None:
            continue  # optional [mcp] extra not installed
        proc = subprocess.run(
            [sys.executable, str(REPO / "examples" / name)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=REPO,
        )
        assert proc.returncode == 0, (
            f"{name} exited {proc.returncode}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
        assert marker in proc.stdout, (
            f"{name} ran but its promised output marker {marker!r} is gone;\n"
            f"stdout: {proc.stdout}"
        )
