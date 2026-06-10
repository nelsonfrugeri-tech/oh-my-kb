"""``omh resource`` — subgroup for managing MCP resources.

MCP server availability is not required; resources are resolved directly
from the installed package.

Subcommands:
    list    — list all available resources with URI and destination path.
    pull    — download one or all resources to ``~/.claude/``.
    diff    — compare local resources with the current server version.
    update  — apply server updates and regenerate ``~/.claude/CLAUDE.md``.
"""

from __future__ import annotations

import typer

from oh_my_harness.kb.cli.resource.diff_cmd import diff_cmd
from oh_my_harness.kb.cli.resource.list_cmd import list_cmd
from oh_my_harness.kb.cli.resource.pull_cmd import pull_cmd
from oh_my_harness.kb.cli.resource.update_cmd import update_cmd

resource_app = typer.Typer(
    help="Manage MCP resources (list, pull, diff, update).",
    no_args_is_help=True,
)

resource_app.command("list")(list_cmd)
resource_app.command("pull")(pull_cmd)
resource_app.command("diff")(diff_cmd)
resource_app.command("update")(update_cmd)

__all__ = ["resource_app"]
