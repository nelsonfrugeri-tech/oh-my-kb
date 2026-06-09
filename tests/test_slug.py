from datetime import UTC, datetime

import pytest

from oh_my_harness.kb.core import generate_slug


@pytest.fixture
def created_at() -> datetime:
    return datetime(2026, 5, 31, 14, 30, tzinfo=UTC)


def test_basic_slug(created_at: datetime) -> None:
    assert generate_slug("Desenho das tools", created_at) == "2026-05-31-desenho-das-tools"


def test_strips_accents(created_at: datetime) -> None:
    assert (
        generate_slug("Decisão sobre índice", created_at)
        == "2026-05-31-decisao-sobre-indice"
    )


def test_punctuation_collapses_to_hyphens(created_at: datetime) -> None:
    assert generate_slug("Hello, World!!!", created_at) == "2026-05-31-hello-world"


def test_collapses_repeated_whitespace(created_at: datetime) -> None:
    assert (
        generate_slug("  Multiple   spaces  here ", created_at)
        == "2026-05-31-multiple-spaces-here"
    )


def test_lowercases_title(created_at: datetime) -> None:
    assert generate_slug("UPPER Case Title", created_at) == "2026-05-31-upper-case-title"


def test_uses_created_at_date_only() -> None:
    # Time-of-day is irrelevant — only the calendar date is used in the prefix.
    morning = datetime(2026, 1, 2, 1, 0, tzinfo=UTC)
    evening = datetime(2026, 1, 2, 23, 59, tzinfo=UTC)
    assert generate_slug("same day", morning) == generate_slug("same day", evening)
