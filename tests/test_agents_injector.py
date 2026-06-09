"""Unit tests for :func:`oh_my_harness.kb.agents.injector.inject_block`."""

from __future__ import annotations

import pytest

from oh_my_harness.kb.agents.injector import (
    END_MARKER,
    START_MARKER,
    InjectAction,
    MalformedBlockError,
    inject_block,
)

_BLOCK = "# kb-mcp rules\nsome content here"
_DIFFERENT_BLOCK = "# kb-mcp rules\ndifferent universe content"


def _wrap(block: str) -> str:
    return f"{START_MARKER}\n{block.rstrip()}\n{END_MARKER}\n"


class TestInjectBlockCreated:
    def test_none_content_returns_created_action(self) -> None:
        _, action = inject_block(None, _BLOCK)
        assert action == InjectAction.CREATED

    def test_none_content_returns_wrapped_block_only(self) -> None:
        content, _ = inject_block(None, _BLOCK)
        assert content == _wrap(_BLOCK)
        assert START_MARKER in content
        assert END_MARKER in content


class TestInjectBlockInserted:
    def test_empty_string_returns_inserted_action(self) -> None:
        _, action = inject_block("", _BLOCK)
        assert action == InjectAction.INSERTED

    def test_empty_string_starts_with_marker(self) -> None:
        content, _ = inject_block("", _BLOCK)
        # Empty file: starts directly with the block marker
        assert content.startswith(START_MARKER)

    def test_user_text_no_markers_returns_inserted(self) -> None:
        _, action = inject_block("# My CLAUDE.md\n\nSome instructions here.\n", _BLOCK)
        assert action == InjectAction.INSERTED

    def test_block_prepended_before_user_text(self) -> None:
        """Bug 3 fix: block is at the TOP, user text follows below."""
        user_text = "# My CLAUDE.md\n\nSome instructions here.\n"
        content, _ = inject_block(user_text, _BLOCK)
        # Block must appear before user text
        assert content.startswith(START_MARKER)
        block_end_idx = content.find(END_MARKER) + len(END_MARKER)
        tail = content[block_end_idx:]
        assert "# My CLAUDE.md" in tail
        assert "Some instructions here." in tail

    def test_user_text_preserved_after_block(self) -> None:
        user_text = "# My CLAUDE.md\n\nSome instructions here.\n"
        content, _ = inject_block(user_text, _BLOCK)
        assert _wrap(_BLOCK) in content
        assert "# My CLAUDE.md" in content
        assert "Some instructions here." in content

    def test_wrapped_block_at_start(self) -> None:
        user_text = "# My CLAUDE.md\n\nSome instructions here.\n"
        content, _ = inject_block(user_text, _BLOCK)
        # Block must be at the very start of the file
        assert content.index(START_MARKER) < content.index("# My CLAUDE.md")


class TestInjectBlockUnchanged:
    def test_same_block_returns_unchanged(self) -> None:
        initial, _ = inject_block(None, _BLOCK)
        _, action = inject_block(initial, _BLOCK)
        assert action == InjectAction.UNCHANGED

    def test_unchanged_content_is_identical(self) -> None:
        initial, _ = inject_block(None, _BLOCK)
        content, _ = inject_block(initial, _BLOCK)
        assert content == initial


class TestInjectBlockReplaced:
    def test_different_block_returns_replaced(self) -> None:
        initial, _ = inject_block(None, _BLOCK)
        _, action = inject_block(initial, _DIFFERENT_BLOCK)
        assert action == InjectAction.REPLACED

    def test_replaced_content_contains_new_block(self) -> None:
        initial, _ = inject_block(None, _BLOCK)
        content, _ = inject_block(initial, _DIFFERENT_BLOCK)
        assert _DIFFERENT_BLOCK.rstrip() in content

    def test_user_text_preserved_on_replace(self) -> None:
        user_text = "# Project rules\n\nDo not disturb.\n"
        inserted, _ = inject_block(user_text, _BLOCK)
        replaced, action = inject_block(inserted, _DIFFERENT_BLOCK)
        assert action == InjectAction.REPLACED
        assert "# Project rules" in replaced
        assert "Do not disturb." in replaced

    def test_user_text_after_markers_preserved_on_replace(self) -> None:
        after_text = "After text.\n"
        before_text = "Before text.\n"
        initial = (
            f"{START_MARKER}\n{_BLOCK.rstrip()}\n{END_MARKER}\n\n"
            f"{before_text}\n"
            f"{after_text}"
        )
        content, action = inject_block(initial, _DIFFERENT_BLOCK)
        assert action == InjectAction.REPLACED
        assert "Before text." in content
        assert "After text." in content

    def test_universe_update_replaces_correctly(self) -> None:
        block_v1 = "# rules\nactive universe: my-universe"
        block_v2 = "# rules\nactive universe: other-universe"
        initial, _ = inject_block(None, block_v1)
        content, action = inject_block(initial, block_v2)
        assert action == InjectAction.REPLACED
        assert "other-universe" in content
        assert "my-universe" not in content


class TestInjectBlockPrepend:
    """Tests for the prepend-first behaviour (Bug 3 fix)."""

    def test_inserted_block_is_at_file_start(self) -> None:
        user_text = "Some existing content.\n"
        content, action = inject_block(user_text, _BLOCK)
        assert action == InjectAction.INSERTED
        assert content.startswith(START_MARKER)

    def test_replaced_block_stays_at_file_start(self) -> None:
        # First insert
        content_v1, _ = inject_block("User notes.\n", _BLOCK)
        # Now replace with new block
        content_v2, _ = inject_block(content_v1, _DIFFERENT_BLOCK)
        assert content_v2.startswith(START_MARKER)

    def test_legacy_appended_block_moved_to_top(self) -> None:
        """Bug 5 fix: block present at non-top position is moved to top on next write."""
        user_text = "# User Content\n\nImportant.\n"
        # Simulate the old append behavior: user content then block
        legacy = user_text + "\n" + _wrap(_BLOCK)
        # A second inject with the SAME block should move it to the top
        content, _action = inject_block(legacy, _BLOCK)
        # Block is at the top now
        assert content.startswith(START_MARKER)
        # User content is preserved
        assert "# User Content" in content
        assert "Important." in content
        # No duplicate markers
        assert content.count(START_MARKER) == 1
        assert content.count(END_MARKER) == 1


class TestInjectBlockCRLF:
    def test_crlf_content_finds_markers(self) -> None:
        crlf_content = f"{START_MARKER}\r\n{_BLOCK.rstrip()}\r\n{END_MARKER}\r\n"
        _, action = inject_block(crlf_content, _BLOCK)
        assert action == InjectAction.UNCHANGED


class TestInjectBlockMalformed:
    def test_end_before_start_raises(self) -> None:
        malformed = f"{END_MARKER}\n{START_MARKER}\n"
        with pytest.raises(MalformedBlockError):
            inject_block(malformed, _BLOCK)

    def test_only_start_marker_raises(self) -> None:
        malformed = f"Some text\n{START_MARKER}\nsome content\n"
        with pytest.raises(MalformedBlockError):
            inject_block(malformed, _BLOCK)

    def test_only_end_marker_raises(self) -> None:
        malformed = f"Some text\n{END_MARKER}\nsome content\n"
        with pytest.raises(MalformedBlockError):
            inject_block(malformed, _BLOCK)

    def test_duplicate_start_markers_raises(self) -> None:
        duplicate = (
            f"{START_MARKER}\n{START_MARKER}\n{_BLOCK.rstrip()}\n{END_MARKER}\n"
        )
        with pytest.raises(MalformedBlockError):
            inject_block(duplicate, _BLOCK)
