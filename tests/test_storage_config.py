import pytest

from oh_my_harness.kb.storage import DEFAULT_QDRANT_URL, QDRANT_URL_ENV, get_qdrant_url


def test_default_url_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(QDRANT_URL_ENV, raising=False)
    assert get_qdrant_url() == DEFAULT_QDRANT_URL


def test_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(QDRANT_URL_ENV, "http://qdrant.internal:6333")
    assert get_qdrant_url() == "http://qdrant.internal:6333"
