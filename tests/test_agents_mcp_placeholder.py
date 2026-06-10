"""Smoke test for the o-agents-mcp placeholder entry point (issue #58)."""

from __future__ import annotations

import subprocess
import sys


def test_agents_mcp_server_import() -> None:
    """The agents mcp server module must be importable without error."""
    import oh_my_harness.agents.mcp.server as mod

    assert hasattr(mod, "main")


def test_agents_mcp_main_exits_zero() -> None:
    """``o-agents-mcp`` placeholder must print its message and exit 0."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from oh_my_harness.agents.mcp.server import main; main()",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"unexpected returncode: {result.returncode}\n{result.stderr}"
    assert "o-agents-mcp" in result.stdout
    assert "not yet implemented" in result.stdout
    assert "issue #58" in result.stdout
