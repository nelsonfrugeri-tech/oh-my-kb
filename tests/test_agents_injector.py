"""Unit tests for :func:`oh_my_kb.agents.injector.inject_block`."""

from __future__ import annotations

import pytest

from oh_my_kb.agents.injector import (
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

    def test_empty_string_no_leading_blank_line(self) -> None:
        content, _ = inject_block("", _BLOCK)
        # Empty file: no blank line prefix expected — starts directly with the marker
        assert content.startswith(START_MARKER)

    def test_user_text_no_markers_returns_inserted(self) -> None:
        _, action = inject_block("# My CLAUDE.md\n\nSome instructions here.\n", _BLOCK)
        assert action == InjectAction.INSERTED

    def test_user_text_preserved_before_block(self) -> None:
        user_text = "# My CLAUDE.md\n\nSome instructions here.\n"
        content, _ = inject_block(user_text, _BLOCK)
        assert content.startswith(user_text)

    def test_wrapped_block_appended_after_blank_line(self) -> None:
        user_text = "# My CLAUDE.md\n\nSome instructions here.\n"
        content, _ = inject_block(user_text, _BLOCK)
        assert _wrap(_BLOCK) in content
        # A blank line separates user text from the injected block
        assert "\n\n" + START_MARKER in content


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

    def test_user_text_before_markers_preserved_on_replace(self) -> None:
        user_text = "# Project rules\n\nDo not disturb.\n"
        inserted, _ = inject_block(user_text, _BLOCK)
        replaced, action = inject_block(inserted, _DIFFERENT_BLOCK)
        assert action == InjectAction.REPLACED
        assert "# Project rules" in replaced
        assert "Do not disturb." in replaced

    def test_user_text_after_markers_preserved_on_replace(self) -> None:
        after_text = "After text.\n"
        initial = (
            f"Before text.\n\n"
            f"{START_MARKER}\n{_BLOCK.rstrip()}\n{END_MARKER}\n\n"
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
