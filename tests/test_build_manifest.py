"""Tests for scripts/build_manifest.py — manifest builder."""

from __future__ import annotations

import hashlib
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_file(path: Path, content: str) -> str:
    """Write *content* to *path* (creates parents) and return its sha256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Unit tests importing the builder functions directly
# ---------------------------------------------------------------------------


def _import_builders() -> tuple:
    """Import build_manifest helpers.  The module uses REPO_ROOT at import time,
    so we patch the module-level constant after importing."""
    import importlib
    import importlib.util
    import sys

    script = Path(__file__).parent.parent / "scripts" / "build_manifest.py"
    spec = importlib.util.spec_from_file_location("build_manifest", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_manifest"] = mod
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


class TestBuildManifestUnit:
    def test_skill_entry_includes_sha256(self, tmp_path: Path) -> None:
        mod = _import_builders()
        assets = tmp_path / "assets"
        content = "# Test skill\n"
        sha = _write_file(assets / "skills" / "my-skill" / "SKILL.md", content)
        mod.ASSETS_DIR = assets  # type: ignore[attr-defined]
        skills = mod.build_skills({})
        assert len(skills) == 1
        assert skills[0]["name"] == "my-skill"
        assert skills[0]["files"][0]["sha256"] == sha

    def test_skill_entry_preserves_existing_version(self, tmp_path: Path) -> None:
        mod = _import_builders()
        assets = tmp_path / "assets"
        _write_file(assets / "skills" / "my-skill" / "SKILL.md", "# content\n")
        mod.ASSETS_DIR = assets  # type: ignore[attr-defined]
        skills = mod.build_skills({"my-skill": "2.1.0"})
        assert skills[0]["version"] == "2.1.0"

    def test_skill_entry_defaults_to_1_0_0(self, tmp_path: Path) -> None:
        mod = _import_builders()
        assets = tmp_path / "assets"
        _write_file(assets / "skills" / "new-skill" / "SKILL.md", "# content\n")
        mod.ASSETS_DIR = assets  # type: ignore[attr-defined]
        skills = mod.build_skills({})
        assert skills[0]["version"] == "1.0.0"

    def test_agent_reads_skills_from_frontmatter(self, tmp_path: Path) -> None:
        mod = _import_builders()
        assets = tmp_path / "assets"
        content = "---\nname: dev\nskills:\n  - implement\n  - test\n---\n# Agent\n"
        _write_file(assets / "agents" / "dev.md", content)
        mod.ASSETS_DIR = assets  # type: ignore[attr-defined]
        agents = mod.build_agents({})
        assert len(agents) == 1
        assert agents[0]["dependencies"]["skills"] == ["implement", "test"]

    def test_agent_without_skills_has_no_deps(self, tmp_path: Path) -> None:
        mod = _import_builders()
        assets = tmp_path / "assets"
        content = "---\nname: minimal\n---\n# Minimal agent\n"
        _write_file(assets / "agents" / "minimal.md", content)
        mod.ASSETS_DIR = assets  # type: ignore[attr-defined]
        agents = mod.build_agents({})
        assert "dependencies" not in agents[0]

    def test_workflow_extracts_agent_types(self, tmp_path: Path) -> None:
        mod = _import_builders()
        assets = tmp_path / "assets"
        ts_content = (
            "const steps = [\n"
            "  { agentType: 'tech-pm', phase: 'start' },\n"
            "  { agentType: 'qa', phase: 'validate' },\n"
            "];\n"
        )
        _write_file(assets / "workflows" / "my-flow.ts", ts_content)
        mod.ASSETS_DIR = assets  # type: ignore[attr-defined]
        workflows = mod.build_workflows({})
        assert len(workflows) == 1
        deps = workflows[0]["dependencies"]["agents"]
        assert "tech-pm" in deps
        assert "qa" in deps

    def test_workflow_extracts_track_ternary_agents(self, tmp_path: Path) -> None:
        mod = _import_builders()
        assets = tmp_path / "assets"
        ts_content = (
            "const track = args?.track === 'ai-engineer' ? 'ai-engineer' : 'developer';\n"
        )
        _write_file(assets / "workflows" / "dynamic.ts", ts_content)
        mod.ASSETS_DIR = assets  # type: ignore[attr-defined]
        workflows = mod.build_workflows({})
        deps = workflows[0]["dependencies"]["agents"]
        assert "ai-engineer" in deps
        assert "developer" in deps

    def test_workflow_without_agent_types_has_no_deps(self, tmp_path: Path) -> None:
        mod = _import_builders()
        assets = tmp_path / "assets"
        ts_content = "export default async function run() { return 42; }\n"
        _write_file(assets / "workflows" / "simple.ts", ts_content)
        mod.ASSETS_DIR = assets  # type: ignore[attr-defined]
        workflows = mod.build_workflows({})
        assert "dependencies" not in workflows[0]

    def test_validate_raises_on_unknown_skill_dep(self, tmp_path: Path) -> None:
        mod = _import_builders()
        skills: list = []
        agents = [{"name": "dev", "dependencies": {"skills": ["nonexistent"]}}]
        workflows: list = []
        with __import__("pytest").raises(SystemExit):
            mod.validate(skills, agents, workflows)

    def test_validate_raises_on_unknown_agent_dep(self, tmp_path: Path) -> None:
        mod = _import_builders()
        skills: list = [{"name": "test"}]
        agents: list = []
        workflows = [{"name": "flow", "dependencies": {"agents": ["ghost"]}}]
        with __import__("pytest").raises(SystemExit):
            mod.validate(skills, agents, workflows)

    def test_validate_passes_when_deps_exist(self, tmp_path: Path) -> None:
        mod = _import_builders()
        skills = [{"name": "implement"}, {"name": "test"}]
        agents = [{"name": "dev", "dependencies": {"skills": ["implement", "test"]}}]
        workflows = [{"name": "flow", "dependencies": {"agents": ["dev"]}}]
        # Should not raise
        mod.validate(skills, agents, workflows)

    def test_idempotent_second_run(self, tmp_path: Path) -> None:
        """Running build twice without changes must produce identical JSON."""
        mod = _import_builders()
        assets = tmp_path / "assets"
        manifest_path = assets / "manifest.json"

        content = "---\nname: dev\nskills:\n  - implement\n---\n# Dev\n"
        _write_file(assets / "skills" / "implement" / "SKILL.md", "# impl\n")
        _write_file(assets / "agents" / "dev.md", content)

        mod.ASSETS_DIR = assets  # type: ignore[attr-defined]
        mod.MANIFEST_PATH = manifest_path  # type: ignore[attr-defined]

        mod.main()
        first = manifest_path.read_text(encoding="utf-8")

        mod.main()
        second = manifest_path.read_text(encoding="utf-8")

        assert first == second
