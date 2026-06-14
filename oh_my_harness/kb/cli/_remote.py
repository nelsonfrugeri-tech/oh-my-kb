"""Remote manifest constants and fetcher for ``omh skills`` / ``omh agents`` / ``omh workflows``."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

REPO_URL = "https://github.com/nelsonfrugeri-tech/oh-my-harness"
RAW_BASE_URL = "https://raw.githubusercontent.com/nelsonfrugeri-tech/oh-my-harness/master"
MANIFEST_URL = f"{RAW_BASE_URL}/assets/manifest.json"


# ---------------------------------------------------------------------------
# Manifest model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillFile:
    path: str
    sha256: str


@dataclass(frozen=True)
class SkillEntry:
    name: str
    version: str
    path: str
    files: list[SkillFile] = field(default_factory=list)


@dataclass(frozen=True)
class AgentEntry:
    name: str
    version: str
    path: str
    sha256: str


@dataclass(frozen=True)
class WorkflowEntry:
    name: str
    version: str
    path: str
    sha256: str


@dataclass(frozen=True)
class Manifest:
    schema_version: int
    skills: list[SkillEntry]
    agents: list[AgentEntry]
    workflows: list[WorkflowEntry] = field(default_factory=list)


def _parse_manifest(data: dict[str, Any]) -> Manifest:
    skills = [
        SkillEntry(
            name=s["name"],
            version=s["version"],
            path=s["path"],
            files=[SkillFile(path=f["path"], sha256=f["sha256"]) for f in s.get("files", [])],
        )
        for s in data.get("skills", [])
    ]
    agents = [
        AgentEntry(
            name=a["name"],
            version=a["version"],
            path=a["path"],
            sha256=a["sha256"],
        )
        for a in data.get("agents", [])
    ]
    workflows = [
        WorkflowEntry(
            name=w["name"],
            version=w["version"],
            path=w["path"],
            sha256=w["sha256"],
        )
        for w in data.get("workflows", [])
    ]
    return Manifest(
        schema_version=int(data.get("schema_version", 1)),
        skills=skills,
        agents=agents,
        workflows=workflows,
    )


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def fetch_text(url: str, *, timeout: int = 10) -> str:
    """GET *url* and return the response body as a string.

    Raises :class:`RuntimeError` on timeout, 4xx, or 5xx.
    """
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"request timed out after {timeout}s: {url}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"network error fetching {url}: {exc}") from exc

    if response.status_code >= 400:
        raise RuntimeError(
            f"HTTP {response.status_code} fetching {url}"
        )
    return response.text


def load_remote_manifest() -> Manifest:
    """Fetch and parse the remote manifest.json."""
    text = fetch_text(MANIFEST_URL)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON in remote manifest: {exc}") from exc
    return _parse_manifest(data)
