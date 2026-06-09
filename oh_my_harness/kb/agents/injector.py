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

    The block is always placed at the **top** of the file so that Claude Code
    gives it the highest priority when reading rules top-to-bottom.  Existing
    user content is preserved below the block.

    Returns a ``(new_content, action)`` tuple.  *current_content* of ``None``
    means the file does not exist yet; the block is written as the entire file.

    Idempotency contract
    --------------------
    * If the markers are already present anywhere in the file and the block
      content is identical, returns ``UNCHANGED`` — the file is not rewritten.
    * If the content differs the block is updated and moved to the top (Bug 5:
      handles legacy positions where the block was appended rather than prepended).
    * Surrounding user content (outside the markers) is always preserved.
    """
    wrapped = f"{start_marker}\n{new_block.rstrip()}\n{end_marker}\n"

    if current_content is None:
        return (wrapped, InjectAction.CREATED)

    # Normalize CRLF to LF so marker search and rebuilt comparison work on Windows
    current_content = current_content.replace("\r\n", "\n")

    i = current_content.find(start_marker)
    j = current_content.find(end_marker)

    if i == -1 and j == -1:
        # No markers — prepend block before existing content (Bug 3 fix: prepend-first).
        if not current_content:
            return (wrapped, InjectAction.INSERTED)
        # Ensure exactly one newline between block and existing content
        suffix = current_content
        if not suffix.startswith("\n"):
            suffix = "\n" + suffix
        return (wrapped + suffix, InjectAction.INSERTED)

    if not (i != -1 and j != -1 and i < j):
        raise MalformedBlockError(
            f"malformed omk:rules markers in file: "
            f"start at {i}, end at {j}. Fix manually."
        )

    # Check for duplicate start markers between first start and end
    second_start = current_content.find(start_marker, i + len(start_marker))
    if second_start != -1 and second_start < j:
        raise MalformedBlockError("duplicate omk:rules:start markers found")

    # Extract existing block content (between markers, exclusive of markers themselves)
    existing_block_content = current_content[i + len(start_marker) + 1 : j].rstrip("\n")
    new_block_stripped = new_block.rstrip()

    # Extract user content before and after the block
    before = current_content[:i].strip("\n")
    after = current_content[j + len(end_marker) :].strip("\n")

    # Build the canonical layout: block on top, user content below
    parts: list[str] = [wrapped]
    if before:
        parts.append("\n" + before + "\n")
    if after:
        parts.append("\n" + after + "\n")
    rebuilt = "".join(parts)

    # Idempotency: if the rebuilt result equals current content AND block unchanged,
    # return UNCHANGED.  Also handles the case where the block is already at the top
    # and content is identical (Bug 5: accept block in any position if content matches).
    if existing_block_content == new_block_stripped:
        if rebuilt == current_content:
            return (current_content, InjectAction.UNCHANGED)
        # Block content is the same but it may be in the wrong position (legacy append).
        # Move it to the top — this counts as REPLACED to signal a write happened.
        return (rebuilt, InjectAction.REPLACED)

    return (rebuilt, InjectAction.REPLACED)
