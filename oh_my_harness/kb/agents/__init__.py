"""oh_my_harness.kb.agents — harness bootstrap utilities."""

from oh_my_harness.kb.agents.bootstrap import (
    BootstrapReport,
    NoActiveKbError,
    NoActiveUniverseError,  # backward-compatible alias
    bootstrap,
)

__all__ = [
    "BootstrapReport",
    "NoActiveKbError",
    "NoActiveUniverseError",
    "bootstrap",
]
