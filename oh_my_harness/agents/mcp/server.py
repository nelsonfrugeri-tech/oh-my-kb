"""``o-agents-mcp`` — agents-side stdio MCP server.

Minimal scaffolding with zero tools registered.  The sole purpose of this
module is to give issue #56 a stable base to land ``develop_leap_update``
and future agent tools on top of, without needing to set up the transport
from scratch.

Structure mirrors ``oh_my_harness.kb.mcp.server``:
- :class:`AgentsServerContext` — frozen dataclass, fields added by #56
- :func:`build_context` — returns a default :class:`AgentsServerContext`
- :func:`build_server` — wires the :class:`Server` with empty tool handlers
- :func:`_log_startup` — logs boot message to stderr
- :func:`_serve` — asyncio coroutine that runs the stdio transport
- :func:`main` — entry point (registered as ``o-agents-mcp`` in pyproject.toml)
"""

from __future__ import annotations

import asyncio
import signal
import sys
from dataclasses import dataclass
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

SERVER_NAME = "o-agents-mcp"


@dataclass(frozen=True, slots=True)
class AgentsServerContext:
    """Runtime snapshot for the agents MCP server.

    Intentionally empty for now — issue #56 will add concrete fields
    (e.g. workspace config, tool registries) as the agent surface grows.
    """


def build_context() -> AgentsServerContext:
    """Construct the server context from the current environment.

    Issue #56 will extend this to read env-vars and build concrete deps.
    """
    return AgentsServerContext()


def build_server(context: AgentsServerContext) -> Server[Any, Any]:
    """Construct a :class:`Server` with empty tool stubs.

    Zero tools are registered here.  Issue #56 will add ``develop_leap_update``
    and friends by extending *this* function.

    Args:
        context: Runtime snapshot (unused at this stage; reserved for #56).

    Returns:
        Configured :class:`Server` instance ready to run the stdio transport.
    """
    server: Server[Any, Any] = Server(SERVER_NAME)

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return []

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        return [TextContent(type="text", text=f"unknown tool: {name}")]

    return server


def _log_startup(context: AgentsServerContext) -> None:
    print(
        (
            f"{SERVER_NAME} ready\n"
            f"  tools      : (nenhuma — placeholder, ver issue #56)"
        ),
        file=sys.stderr,
        flush=True,
    )


async def _serve() -> None:
    context = build_context()
    server = build_server(context)
    _log_startup(context)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    """``[project.scripts] o-agents-mcp`` entry point."""

    def _handle_sigterm(signum: int, frame: object) -> None:
        # SIGTERM is the standard shutdown signal in containers and systemd.
        # Without this handler asyncio.run raises SystemExit with no message,
        # making container logs silent on graceful shutdown.
        print(f"{SERVER_NAME} stopped (SIGTERM)", file=sys.stderr)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        print(f"{SERVER_NAME} stopped", file=sys.stderr)


if __name__ == "__main__":  # pragma: no cover
    main()
