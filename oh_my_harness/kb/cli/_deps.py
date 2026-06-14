"""Transitive dependency resolver for manifest assets.

Pure module — no I/O, no HTTP.  Operates only on the in-memory
:class:`~oh_my_harness.kb.cli._remote.Manifest` dataclass.

Public API
----------
resolve(manifest, kind, name) -> ResolvedSet
    Return the full transitive closure for a single named asset.

resolve_all(manifest, kind) -> ResolvedSet
    Union of resolve() over every asset of *kind* in the manifest.

ResolvedSet
    Dataclass holding deduplicated, topologically-ordered lists:
    skills first (leaves), then agents, then workflows (roots).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from oh_my_harness.kb.cli._remote import (
    AgentEntry,
    Manifest,
    SkillEntry,
    WorkflowEntry,
)


class DependencyCycleError(RuntimeError):
    """Raised when a dependency cycle is detected in the manifest graph."""


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ResolvedSet:
    """Deduplicated, topologically-ordered dependency closure.

    Leaves come first: skills → agents → workflows.
    """

    skills: list[SkillEntry] = field(default_factory=list)
    agents: list[AgentEntry] = field(default_factory=list)
    workflows: list[WorkflowEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _skill_index(manifest: Manifest) -> dict[str, SkillEntry]:
    return {e.name: e for e in manifest.skills}


def _agent_index(manifest: Manifest) -> dict[str, AgentEntry]:
    return {e.name: e for e in manifest.agents}


def _workflow_index(manifest: Manifest) -> dict[str, WorkflowEntry]:
    return {e.name: e for e in manifest.workflows}


def _resolve_skill(
    name: str,
    skill_idx: dict[str, SkillEntry],
    visited_skills: set[str],
    result: ResolvedSet,
    skill_ancestors: frozenset[str],
) -> None:
    """DFS over skills — they are leaves, so no recursion beyond dedup."""
    if name in visited_skills:
        return
    if name in skill_ancestors:
        raise DependencyCycleError(f"dependency cycle detected involving skill '{name}'")
    if name not in skill_idx:
        # Unknown skill dep — skip silently (validation is the script's job).
        return
    visited_skills.add(name)
    result.skills.append(skill_idx[name])


def _resolve_agent(
    name: str,
    skill_idx: dict[str, SkillEntry],
    agent_idx: dict[str, AgentEntry],
    visited_skills: set[str],
    visited_agents: set[str],
    result: ResolvedSet,
    agent_ancestors: frozenset[str],
) -> None:
    if name in visited_agents:
        return
    if name in agent_ancestors:
        raise DependencyCycleError(f"dependency cycle detected involving agent '{name}'")
    if name not in agent_idx:
        return
    entry = agent_idx[name]
    # Resolve skill deps of this agent first (leaves before node).
    # Skills have their own independent ancestor namespace.
    for skill_name in entry.dependencies.skills:
        _resolve_skill(skill_name, skill_idx, visited_skills, result, frozenset())
    visited_agents.add(name)
    result.agents.append(entry)


def _resolve_workflow(
    name: str,
    skill_idx: dict[str, SkillEntry],
    agent_idx: dict[str, AgentEntry],
    workflow_idx: dict[str, WorkflowEntry],
    visited_skills: set[str],
    visited_agents: set[str],
    visited_workflows: set[str],
    result: ResolvedSet,
    wf_ancestors: frozenset[str],
) -> None:
    if name in visited_workflows:
        return
    if name in wf_ancestors:
        raise DependencyCycleError(f"dependency cycle detected involving workflow '{name}'")
    if name not in workflow_idx:
        return
    entry = workflow_idx[name]
    # Resolve agent deps (which themselves pull their skill deps).
    # Agents have their own independent ancestor namespace.
    for agent_name in entry.dependencies.agents:
        _resolve_agent(
            agent_name,
            skill_idx,
            agent_idx,
            visited_skills,
            visited_agents,
            result,
            frozenset(),
        )
    # Also resolve any direct skill deps on the workflow (future-proof).
    for skill_name in entry.dependencies.skills:
        _resolve_skill(skill_name, skill_idx, visited_skills, result, frozenset())
    visited_workflows.add(name)
    result.workflows.append(entry)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve(
    manifest: Manifest,
    kind: Literal["skill", "agent", "workflow"],
    name: str,
) -> ResolvedSet:
    """Return the full transitive dependency closure for *name* of *kind*.

    The result is deduplicated and topologically ordered so that leaves
    (skills) come before agents and agents before workflows.

    Raises
    ------
    DependencyCycleError
        If a dependency cycle is detected within the same asset type.
    """
    skill_idx = _skill_index(manifest)
    agent_idx = _agent_index(manifest)
    workflow_idx = _workflow_index(manifest)

    result = ResolvedSet()
    visited_skills: set[str] = set()
    visited_agents: set[str] = set()
    visited_workflows: set[str] = set()

    if kind == "skill":
        _resolve_skill(name, skill_idx, visited_skills, result, frozenset())
    elif kind == "agent":
        _resolve_agent(
            name,
            skill_idx,
            agent_idx,
            visited_skills,
            visited_agents,
            result,
            frozenset(),
        )
    elif kind == "workflow":
        _resolve_workflow(
            name,
            skill_idx,
            agent_idx,
            workflow_idx,
            visited_skills,
            visited_agents,
            visited_workflows,
            result,
            frozenset(),
        )
    else:
        raise ValueError(f"unknown kind: {kind!r}")  # pragma: no cover

    return result


def resolve_all(
    manifest: Manifest,
    kind: Literal["skill", "agent", "workflow"],
) -> ResolvedSet:
    """Resolve every asset of *kind* and union the results.

    Equivalent to calling :func:`resolve` on each name and merging, with
    full deduplication and topological ordering preserved.
    """
    skill_idx = _skill_index(manifest)
    agent_idx = _agent_index(manifest)
    workflow_idx = _workflow_index(manifest)

    result = ResolvedSet()
    visited_skills: set[str] = set()
    visited_agents: set[str] = set()
    visited_workflows: set[str] = set()

    if kind == "skill":
        for skill_entry in manifest.skills:
            _resolve_skill(skill_entry.name, skill_idx, visited_skills, result, frozenset())
    elif kind == "agent":
        for agent_entry in manifest.agents:
            _resolve_agent(
                agent_entry.name,
                skill_idx,
                agent_idx,
                visited_skills,
                visited_agents,
                result,
                frozenset(),
            )
    elif kind == "workflow":
        for wf_entry in manifest.workflows:
            _resolve_workflow(
                wf_entry.name,
                skill_idx,
                agent_idx,
                workflow_idx,
                visited_skills,
                visited_agents,
                visited_workflows,
                result,
                frozenset(),
            )
    else:
        raise ValueError(f"unknown kind: {kind!r}")  # pragma: no cover

    return result


__all__ = [
    "DependencyCycleError",
    "ResolvedSet",
    "resolve",
    "resolve_all",
]
