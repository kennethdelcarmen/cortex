"""Dependency regression tests."""

import subprocess
import sys


def test_fastmcp_import_has_no_deprecation_warnings() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-W",
            "error::DeprecationWarning",
            "-c",
            "import cortex_backend.app",
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
