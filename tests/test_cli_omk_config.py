"""Tests for :class:`OmkConfig` load/save round-trip and coexistence with
:class:`CLIConfig` in the same TOML file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oh_my_harness.kb.cli.config import (
    CONFIG_DIR_ENV,
    CLIConfig,
    OmkConfig,
    OmkCoreConfig,
    OmkHarnessConfig,
    OmkQdrantConfig,
    add_universe,
    load_config,
    load_omk_config,
    omk_config_path,
    save_config,
    save_omk_config,
)


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate config writes to tmp_path for every test."""
    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path / "config"))


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


class TestOmkConfigDefaults:
    def test_load_returns_defaults_when_file_absent(self) -> None:
        cfg = load_omk_config()
        assert cfg.qdrant.port == 6333
        assert cfg.harness.active == "claude-code"
        assert cfg.qdrant.container_name == "oh-my-harness-qdrant"

    def test_core_notes_root_default_contains_oh_my_harness(self) -> None:
        cfg = load_omk_config()
        assert "oh-my-harness" in str(cfg.core.notes_root)

    def test_core_default_universe_is_default(self) -> None:
        cfg = load_omk_config()
        assert cfg.core.default_universe == "default"


# ---------------------------------------------------------------------------
# Round-trip: save → load
# ---------------------------------------------------------------------------


class TestOmkConfigRoundTrip:
    def test_save_and_load_core_notes_root(self, tmp_path: Path) -> None:
        notes = tmp_path / "my-notes"
        cfg = OmkConfig(
            core=OmkCoreConfig(notes_root=notes, default_universe="work"),
        )
        save_omk_config(cfg)
        loaded = load_omk_config()
        assert loaded.core.notes_root == notes

    def test_save_and_load_core_default_universe(self) -> None:
        cfg = OmkConfig(core=OmkCoreConfig(default_universe="my-universe"))
        save_omk_config(cfg)
        loaded = load_omk_config()
        assert loaded.core.default_universe == "my-universe"

    def test_save_and_load_qdrant_port(self) -> None:
        cfg = OmkConfig(qdrant=OmkQdrantConfig(port=6334))
        save_omk_config(cfg)
        loaded = load_omk_config()
        assert loaded.qdrant.port == 6334

    def test_save_and_load_qdrant_container_name(self) -> None:
        cfg = OmkConfig(qdrant=OmkQdrantConfig(container_name="my-qdrant"))
        save_omk_config(cfg)
        loaded = load_omk_config()
        assert loaded.qdrant.container_name == "my-qdrant"

    def test_save_and_load_harness_active(self) -> None:
        cfg = OmkConfig(harness=OmkHarnessConfig(active="claude-code"))
        save_omk_config(cfg)
        loaded = load_omk_config()
        assert loaded.harness.active == "claude-code"

    def test_save_returns_path(self, tmp_path: Path) -> None:
        cfg = OmkConfig()
        path = save_omk_config(cfg)
        assert path.exists()
        assert path.suffix == ".toml"

    def test_save_creates_parent_dir_if_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        new_dir = tmp_path / "brand-new-dir"
        monkeypatch.setenv(CONFIG_DIR_ENV, str(new_dir))
        cfg = OmkConfig()
        save_omk_config(cfg)
        assert new_dir.exists()


# ---------------------------------------------------------------------------
# Coexistence: OmkConfig and CLIConfig in the same file
# ---------------------------------------------------------------------------


class TestOmkAndCliConfigCoexistence:
    def test_cli_config_survives_omk_save(self, tmp_path: Path) -> None:
        """Writing OmkConfig must not destroy CLIConfig (universes/active)."""
        # First write CLIConfig
        cli_cfg = add_universe(
            CLIConfig(),
            name="my-universe",
            notes_root=tmp_path / "notes",
        )
        save_config(cli_cfg)

        # Then write OmkConfig
        omk_cfg = OmkConfig(qdrant=OmkQdrantConfig(port=7000))
        save_omk_config(omk_cfg)

        # Load CLIConfig — must still have the universe
        loaded_cli = load_config()
        assert loaded_cli.has("my-universe"), "CLIConfig data was lost after OmkConfig save"

    def test_omk_config_survives_cli_save(self, tmp_path: Path) -> None:
        """Writing CLIConfig must not destroy OmkConfig ([core]/[qdrant]/[harness])."""
        # First write OmkConfig
        omk_cfg = OmkConfig(qdrant=OmkQdrantConfig(port=7000))
        save_omk_config(omk_cfg)

        # Then write CLIConfig
        cli_cfg = add_universe(
            CLIConfig(),
            name="another-universe",
            notes_root=tmp_path / "notes",
        )
        save_config(cli_cfg)

        # Load OmkConfig — port must still be 7000
        loaded_omk = load_omk_config()
        assert loaded_omk.qdrant.port == 7000, "OmkConfig data was lost after CLIConfig save"

    def test_both_configs_readable_after_joint_write(self, tmp_path: Path) -> None:
        """Write both configs independently and read them back."""
        cli_cfg = add_universe(
            CLIConfig(), name="default", notes_root=tmp_path / "notes"
        )
        save_config(cli_cfg)

        omk_cfg = OmkConfig(
            core=OmkCoreConfig(default_universe="default"),
            harness=OmkHarnessConfig(active="claude-code"),
        )
        save_omk_config(omk_cfg)

        loaded_cli = load_config()
        loaded_omk = load_omk_config()

        assert loaded_cli.has("default")
        assert loaded_omk.harness.active == "claude-code"

    def test_omk_config_path_same_as_config_path(self) -> None:
        from oh_my_harness.kb.cli.config import config_path

        assert omk_config_path() == config_path()
