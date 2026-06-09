"""Manifest for pulled resources — ``~/.claude/.omk-manifest.json``.

Schema notes
------------
- ``content_version`` is stored as a **raw string** extracted from the HTML
  comment ``<!-- content_version: N ... -->``.  Do NOT coerce to semver.
  All resources must use the same format (currently integer, e.g. ``1``).
- ``local_path`` is stored tilde-literal; expand with
  ``Path(local_path).expanduser()`` at write-time only.
- ``sha256`` is computed over the UTF-8 bytes of the file as written
  (i.e. ``content.encode("utf-8")``).
- Top-level ``pulled_at`` records when the last pull happened.
- Per-resource ``pulled_at`` records when that specific resource was pulled.
- Both timestamps are ISO-8601 UTC strings.
- ``load_manifest`` returns ``None`` when the manifest file is absent so that
  callers can distinguish "never pulled" from an empty manifest.

The ``home=`` parameter on ``load_manifest`` / ``save_manifest`` exists for
test injection; pass ``tmp_path`` from a pytest fixture to avoid touching
the real ``~/.claude/`` directory.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

MANIFEST_FILENAME = ".omk-manifest.json"
MANIFEST_PATH: Path = Path("~/.claude") / MANIFEST_FILENAME


@dataclass
class ResourceRecord:
    """Per-resource entry in the manifest.

    Attributes:
        uri:             Full MCP resource URI.
        local_path:      Tilde-literal destination path.
        content_version: Raw string from the ``content_version`` comment.
        pulled_at:       ISO-8601 UTC timestamp of the last pull for this resource.
        sha256:          SHA-256 hex digest of the UTF-8 bytes written to disk.
    """

    uri: str
    local_path: str
    content_version: str
    pulled_at: str
    sha256: str


@dataclass
class Manifest:
    """Top-level manifest structure.

    Attributes:
        pulled_at:  ISO-8601 UTC timestamp of the last ``pull --all`` or single pull.
        resources:  Map of ``short_id`` → ``ResourceRecord``.
    """

    pulled_at: str
    resources: dict[str, ResourceRecord]


def _resolve_manifest_path(home: Path | None) -> Path:
    """Return the absolute path to the manifest file.

    When ``home`` is provided (test injection) it is used instead of
    ``Path.home()``; the manifest sits at ``<home>/.claude/.omk-manifest.json``.
    """
    if home is not None:
        return home / ".claude" / MANIFEST_FILENAME
    return MANIFEST_PATH.expanduser()


def load_manifest(home: Path | None = None) -> Manifest | None:
    """Load the manifest from disk.

    Returns ``None`` when the manifest file does not exist.
    ``home`` can be set to a temporary directory for tests.
    """
    path = _resolve_manifest_path(home)
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    resources = {
        short_id: ResourceRecord(**rec)
        for short_id, rec in raw.get("resources", {}).items()
    }
    return Manifest(pulled_at=raw["pulled_at"], resources=resources)


def save_manifest(m: Manifest, home: Path | None = None) -> None:
    """Persist the manifest to disk (creates parent directory if needed).

    ``home`` can be set to a temporary directory for tests.
    """
    path = _resolve_manifest_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "pulled_at": m.pulled_at,
        "resources": {
            short_id: asdict(rec) for short_id, rec in m.resources.items()
        },
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
