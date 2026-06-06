"""Block injector — inserts/replaces the omk:rules block in a harness rules file."""

from __future__ import annotations

from enum import StrEnum

START_MARKER = "<!-- omk:rules:start -->"
END_MARKER = "<!-- omk:rules:end -->"


class InjectAction(StrEnum):
    CREATED = "created"
    INSERTED = "inserted"
    REPLACED = "replaced"
    UNCHANGED = "unchanged"


class MalformedBlockError(ValueError):
    """Raised when markers are present but malformed (swapped, unpaired, duplicated)."""


def inject_block(
    current_content: str | None,
    new_block: str,
    start_marker: str = START_MARKER,
    end_marker: str = END_MARKER,
) -> tuple[str, InjectAction]:
    """Inject *new_block* into *current_content* between the omk:rules markers.

    Returns a ``(new_content, action)`` tuple.  *current_content* of ``None``
    means the file does not exist yet; the block is written as the entire file.
    """
    wrapped = f"{start_marker}\n{new_block.rstrip()}\n{end_marker}\n"

    if current_content is None:
        return (wrapped, InjectAction.CREATED)

    # Normalize CRLF to LF so marker search and rebuilt comparison work on Windows
    current_content = current_content.replace("\r\n", "\n")

    i = current_content.find(start_marker)
    j = current_content.find(end_marker)

    if i == -1 and j == -1:
        # No markers — append after a blank line separator
        prefix = current_content
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if prefix:
            prefix += "\n"
        return (prefix + wrapped, InjectAction.INSERTED)

    if not (i != -1 and j != -1 and i < j):
        raise MalformedBlockError(
            f"malformed omk:rules markers in file: "
            f"start at {i}, end at {j}. Fix manually."
        )

    # Check for duplicate start markers between first start and end
    second_start = current_content.find(start_marker, i + len(start_marker))
    if second_start != -1 and second_start < j:
        raise MalformedBlockError("duplicate omk:rules:start markers found")

    before = current_content[:i]
    after = current_content[j + len(end_marker):]

    if before.endswith("\n"):
        before = before[:-1]
    if after.startswith("\n"):
        after = after[1:]

    rebuilt = (
        (before + "\n" if before else "")
        + wrapped
        + (after if after.endswith("\n") or not after else after + "\n")
    )

    if rebuilt == current_content:
        return (current_content, InjectAction.UNCHANGED)
    return (rebuilt, InjectAction.REPLACED)
