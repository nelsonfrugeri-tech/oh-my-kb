#!/usr/bin/env python3
"""Rebuild ``assets/manifest.json`` from scratch by scanning the ``assets/`` tree.

This script is idempotent and CI-friendly: running it twice in a row with no
asset changes produces exactly the same JSON (sorted keys, stable ordering),
so ``git diff`` will show nothing.

Usage
-----
    python scripts/build_manifest.py

Or via the Makefile target:

    make manifest

What it does
------------
* **skills** — walks ``assets/skills/<name>/`` and records every file with its
  sha256.  No dependencies field (skills are leaves).
* **agents** — reads ``assets/agents/<name>.md``, computes sha256, and extracts
  ``skills: [...]`` from the YAML frontmatter to populate
  ``dependencies.skills``.
* **workflows** — reads ``assets/workflows/<name>.ts``, computes sha256, and
  extracts every ``agentType: '<name>'`` string via regex to populate
  ``dependencies.agents``.

Version preservation
--------------------
If an entry already exists in the current manifest, its ``version`` value is
carried forward.  New entries default to ``"1.0.0"``.

Validation
----------
Every dependency name must resolve to an existing entry in its respective
section.  Unknown dependency names cause the script to exit with a non-zero
code and a clear error message.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import frontmatter  # python-frontmatter

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
ASSETS_DIR = REPO_ROOT / "assets"
MANIFEST_PATH = ASSETS_DIR / "manifest.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _agent_type_regex() -> re.Pattern[str]:
    """Match ``agentType: 'name'`` string-literal patterns."""
    return re.compile(r"agentType\s*:\s*['\"]([^'\"]+)['\"]")


def _track_ternary_regex() -> re.Pattern[str]:
    """Match ``args?.track === 'X' ? 'X' : 'Y'`` ternary patterns.

    These capture the dynamic implementer agents (developer / ai-engineer)
    that are assigned via a runtime ternary and therefore don't appear as
    literal ``agentType`` strings.
    """
    # Pattern: args?.track === '<val>' ? '<true_val>' : '<false_val>'
    _q = r"""['"]([^'"]+)['"]"""
    _p = r"args\?\.track\s*===\s*" + _q + r"\s*\?\s*" + _q + r"\s*:\s*" + _q
    return re.compile(_p)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def build_skills(existing_versions: dict[str, str]) -> list[dict]:
    skills_dir = ASSETS_DIR / "skills"
    entries: list[dict] = []
    for skill_path in sorted(skills_dir.iterdir()):
        if not skill_path.is_dir():
            continue
        name = skill_path.name
        files: list[dict] = []
        for f in sorted(skill_path.rglob("*")):
            if f.is_file():
                rel = f.relative_to(skill_path)
                files.append({"path": str(rel), "sha256": sha256_file(f)})
        entries.append(
            {
                "name": name,
                "version": existing_versions.get(name, "1.0.0"),
                "path": f"assets/skills/{name}",
                "files": files,
            }
        )
    return entries


def build_agents(existing_versions: dict[str, str]) -> list[dict]:
    agents_dir = ASSETS_DIR / "agents"
    entries: list[dict] = []
    for agent_file in sorted(agents_dir.glob("*.md")):
        name = agent_file.stem
        sha = sha256_file(agent_file)
        # Parse frontmatter to extract skill dependencies
        try:
            post = frontmatter.load(str(agent_file))
            skills: list[str] = list(post.metadata.get("skills", []))
        except Exception as exc:
            print(
                f"WARNING: could not parse frontmatter in {agent_file}: {exc}",
                file=sys.stderr,
            )
            skills = []
        entry: dict = {
            "name": name,
            "version": existing_versions.get(name, "1.0.0"),
            "path": f"assets/agents/{agent_file.name}",
            "sha256": sha,
        }
        if skills:
            entry["dependencies"] = {"skills": sorted(set(skills))}
        entries.append(entry)
    return entries


def build_workflows(existing_versions: dict[str, str]) -> list[dict]:
    workflows_dir = ASSETS_DIR / "workflows"
    agent_type_pat = _agent_type_regex()
    track_pat = _track_ternary_regex()
    entries: list[dict] = []
    for wf_file in sorted(workflows_dir.glob("*.ts")):
        name = wf_file.stem
        sha = sha256_file(wf_file)
        source = wf_file.read_text(encoding="utf-8")
        # Primary: literal agentType: 'name' strings
        agent_names: set[str] = set(agent_type_pat.findall(source))
        # Secondary: ternary track selection pattern (dynamic implementer agents)
        for match in track_pat.finditer(source):
            # Groups: (condition_value, true_value, false_value)
            agent_names.add(match.group(2))
            agent_names.add(match.group(3))
        entry: dict = {
            "name": name,
            "version": existing_versions.get(name, "1.0.0"),
            "path": f"assets/workflows/{wf_file.name}",
            "sha256": sha,
        }
        if agent_names:
            entry["dependencies"] = {"agents": sorted(agent_names)}
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate(
    skills: list[dict],
    agents: list[dict],
    workflows: list[dict],
) -> None:
    skill_names = {e["name"] for e in skills}
    agent_names = {e["name"] for e in agents}

    errors: list[str] = []

    for agent in agents:
        for skill in agent.get("dependencies", {}).get("skills", []):
            if skill not in skill_names:
                errors.append(
                    f"agent '{agent['name']}' depends on unknown skill '{skill}'"
                )

    for wf in workflows:
        for agent in wf.get("dependencies", {}).get("agents", []):
            if agent not in agent_names:
                errors.append(
                    f"workflow '{wf['name']}' depends on unknown agent '{agent}'"
                )

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # Load existing manifest to preserve version strings
    existing_skills: dict[str, str] = {}
    existing_agents: dict[str, str] = {}
    existing_workflows: dict[str, str] = {}

    if MANIFEST_PATH.exists():
        try:
            old = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            for e in old.get("skills", []):
                existing_skills[e["name"]] = e["version"]
            for e in old.get("agents", []):
                existing_agents[e["name"]] = e["version"]
            for e in old.get("workflows", []):
                existing_workflows[e["name"]] = e["version"]
        except Exception as exc:
            print(f"WARNING: could not parse existing manifest: {exc}", file=sys.stderr)

    skills = build_skills(existing_skills)
    agents = build_agents(existing_agents)
    workflows = build_workflows(existing_workflows)

    validate(skills, agents, workflows)

    manifest = {
        "schema_version": 1,
        "skills": skills,
        "agents": agents,
        "workflows": workflows,
    }

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"manifest rebuilt: {len(skills)} skills, {len(agents)} agents, {len(workflows)} workflows"
    )


if __name__ == "__main__":
    main()
