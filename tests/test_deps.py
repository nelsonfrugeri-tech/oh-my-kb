"""Tests for oh_my_harness.kb.cli._deps — transitive dependency resolver."""

from __future__ import annotations

import pytest

from oh_my_harness.kb.cli._deps import (
    DependencyCycleError,
    ResolvedSet,
    resolve,
    resolve_all,
)
from oh_my_harness.kb.cli._remote import (
    AgentEntry,
    Dependencies,
    Manifest,
    SkillEntry,
    WorkflowEntry,
)

# ---------------------------------------------------------------------------
# Fixtures — minimal manifest for deterministic tests
# ---------------------------------------------------------------------------

_SKILLS = [
    SkillEntry(name="implement", version="1.0.0", path="assets/skills/implement", files=[]),
    SkillEntry(name="test", version="1.0.0", path="assets/skills/test", files=[]),
    SkillEntry(name="research", version="1.0.0", path="assets/skills/research", files=[]),
    SkillEntry(name="review", version="1.0.0", path="assets/skills/review", files=[]),
]

_AGENTS = [
    AgentEntry(
        name="developer",
        version="1.0.0",
        path="assets/agents/developer.md",
        sha256="abc",
        dependencies=Dependencies(skills=["implement", "test", "research"]),
    ),
    AgentEntry(
        name="qa",
        version="1.0.0",
        path="assets/agents/qa.md",
        sha256="def",
        dependencies=Dependencies(skills=["test", "research", "review"]),
    ),
    AgentEntry(
        name="tech-pm",
        version="1.0.0",
        path="assets/agents/tech-pm.md",
        sha256="ghi",
        dependencies=Dependencies(skills=["research", "review"]),
    ),
]

_WORKFLOWS = [
    WorkflowEntry(
        name="create-feature",
        version="1.0.0",
        path="assets/workflows/create-feature.ts",
        sha256="wf1",
        dependencies=Dependencies(agents=["developer", "qa", "tech-pm"]),
    ),
]

_MANIFEST = Manifest(
    schema_version=1,
    skills=_SKILLS,
    agents=_AGENTS,
    workflows=_WORKFLOWS,
)


# ---------------------------------------------------------------------------
# Skill resolve
# ---------------------------------------------------------------------------


class TestResolveSkill:
    def test_resolve_single_skill_returns_that_skill(self) -> None:
        rs = resolve(_MANIFEST, "skill", "implement")
        assert len(rs.skills) == 1
        assert rs.skills[0].name == "implement"
        assert rs.agents == []
        assert rs.workflows == []

    def test_resolve_unknown_skill_returns_empty(self) -> None:
        rs = resolve(_MANIFEST, "skill", "nonexistent")
        assert rs.skills == []

    def test_resolve_skill_no_duplicates(self) -> None:
        rs = resolve(_MANIFEST, "skill", "research")
        assert len(rs.skills) == 1


# ---------------------------------------------------------------------------
# Agent resolve
# ---------------------------------------------------------------------------


class TestResolveAgent:
    def test_resolve_agent_returns_agent_and_its_skills(self) -> None:
        rs = resolve(_MANIFEST, "agent", "developer")
        assert any(a.name == "developer" for a in rs.agents)
        skill_names = {s.name for s in rs.skills}
        assert "implement" in skill_names
        assert "test" in skill_names
        assert "research" in skill_names

    def test_skills_come_before_agents_in_result(self) -> None:
        rs = resolve(_MANIFEST, "agent", "developer")
        # ResolvedSet: skills list is populated before agents list
        assert len(rs.skills) > 0
        assert len(rs.agents) > 0

    def test_resolve_unknown_agent_returns_empty(self) -> None:
        rs = resolve(_MANIFEST, "agent", "unknown-agent")
        assert rs.agents == []
        assert rs.skills == []

    def test_no_duplicate_skills_across_agent_deps(self) -> None:
        # qa depends on [test, research, review]; developer on [implement, test, research]
        # Together 'test' and 'research' appear only once.
        manifest = Manifest(
            schema_version=1,
            skills=_SKILLS,
            agents=[_AGENTS[0], _AGENTS[1]],  # developer + qa
            workflows=[],
        )
        rs = resolve(manifest, "agent", "developer")
        skill_names = [s.name for s in rs.skills]
        assert skill_names.count("test") == 1
        assert skill_names.count("research") == 1


# ---------------------------------------------------------------------------
# Workflow resolve
# ---------------------------------------------------------------------------


class TestResolveWorkflow:
    def test_resolve_workflow_returns_all_three_tiers(self) -> None:
        rs = resolve(_MANIFEST, "workflow", "create-feature")
        assert len(rs.workflows) == 1
        assert rs.workflows[0].name == "create-feature"
        assert len(rs.agents) > 0
        assert len(rs.skills) > 0

    def test_topological_order_skills_before_agents_before_workflows(self) -> None:
        rs = resolve(_MANIFEST, "workflow", "create-feature")
        # All skills must be recorded in skills list; agents in agents; workflow in workflows.
        agent_names = {a.name for a in rs.agents}
        skill_names = {s.name for s in rs.skills}
        assert "developer" in agent_names
        assert "qa" in agent_names
        assert "tech-pm" in agent_names
        assert "implement" in skill_names
        assert "test" in skill_names
        assert "research" in skill_names
        assert "review" in skill_names

    def test_no_duplicate_skills_in_workflow_closure(self) -> None:
        rs = resolve(_MANIFEST, "workflow", "create-feature")
        skill_names = [s.name for s in rs.skills]
        # All skill names are unique
        assert len(skill_names) == len(set(skill_names))

    def test_no_duplicate_agents_in_workflow_closure(self) -> None:
        rs = resolve(_MANIFEST, "workflow", "create-feature")
        agent_names = [a.name for a in rs.agents]
        assert len(agent_names) == len(set(agent_names))

    def test_resolve_unknown_workflow_returns_empty(self) -> None:
        rs = resolve(_MANIFEST, "workflow", "nonexistent")
        assert rs.workflows == []
        assert rs.agents == []
        assert rs.skills == []


# ---------------------------------------------------------------------------
# resolve_all
# ---------------------------------------------------------------------------


class TestResolveAll:
    def test_resolve_all_skills_returns_all_skills(self) -> None:
        rs = resolve_all(_MANIFEST, "skill")
        assert len(rs.skills) == len(_SKILLS)
        skill_names = {s.name for s in rs.skills}
        assert "implement" in skill_names
        assert "test" in skill_names

    def test_resolve_all_agents_includes_skill_deps(self) -> None:
        rs = resolve_all(_MANIFEST, "agent")
        assert len(rs.agents) == len(_AGENTS)
        assert len(rs.skills) > 0

    def test_resolve_all_workflows_includes_full_closure(self) -> None:
        rs = resolve_all(_MANIFEST, "workflow")
        assert len(rs.workflows) == len(_WORKFLOWS)
        assert len(rs.agents) == len(_AGENTS)
        assert len(rs.skills) == len(_SKILLS)

    def test_no_duplicates_in_resolve_all(self) -> None:
        rs = resolve_all(_MANIFEST, "workflow")
        assert len(rs.skills) == len({s.name for s in rs.skills})
        assert len(rs.agents) == len({a.name for a in rs.agents})
        assert len(rs.workflows) == len({w.name for w in rs.workflows})


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


class TestCycleDetection:
    def test_detects_self_referencing_skill(self) -> None:
        """A skill name in its own skill_ancestors set triggers cycle detection."""
        from oh_my_harness.kb.cli._deps import _resolve_skill

        skill_idx = {"loop": SkillEntry("loop", "1.0.0", "p", [])}
        visited: set[str] = set()
        rs = ResolvedSet()
        with pytest.raises(DependencyCycleError, match="loop"):
            _resolve_skill("loop", skill_idx, visited, rs, frozenset({"loop"}))

    def test_detects_cycle_in_agent_resolution(self) -> None:
        """An agent name in its own agent_ancestors set triggers cycle detection."""
        from oh_my_harness.kb.cli._deps import _resolve_agent

        skill_idx: dict = {}
        agent_idx = {
            "a": AgentEntry("a", "1.0.0", "p", "h", Dependencies(skills=[]))
        }
        visited_skills: set[str] = set()
        visited_agents: set[str] = set()
        rs = ResolvedSet()
        with pytest.raises(DependencyCycleError, match="a"):
            _resolve_agent(
                "a", skill_idx, agent_idx, visited_skills, visited_agents, rs, frozenset({"a"})
            )

    def test_same_name_for_skill_and_agent_does_not_trigger_cycle(self) -> None:
        """A skill and an agent sharing the same name must NOT trigger cycle detection.

        This is the real-world case (e.g. 'ai-engineer' exists as both a skill
        and an agent).  The resolver uses separate namespace tracking for each kind.
        """
        from oh_my_harness.kb.cli._remote import Dependencies, SkillEntry

        shared_name = "ai-engineer"
        skill = SkillEntry(shared_name, "1.0.0", "p", [])
        agent = AgentEntry(
            shared_name, "1.0.0", "p", "h", Dependencies(skills=[shared_name])
        )
        manifest = Manifest(
            schema_version=1,
            skills=[skill],
            agents=[agent],
            workflows=[],
        )
        # Must not raise DependencyCycleError
        rs = resolve(manifest, "agent", shared_name)
        assert any(a.name == shared_name for a in rs.agents)
        assert any(s.name == shared_name for s in rs.skills)
