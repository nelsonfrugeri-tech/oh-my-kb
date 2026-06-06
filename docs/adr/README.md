# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for `oh-my-kb`.

## Format

We use [MADR](https://adr.github.io/madr/) (Markdown Architecture Decision Records).

## Conventions

- **Naming**: `ADR-NNN-kebab-case-title.md` (NNN zero-padded to 3 digits)
- **Numbering**: monotonically increasing, never reused
- **Status**: `Proposed | Accepted | Deprecated | Superseded by ADR-XXX`
- **Immutability**: Accepted ADRs are immutable — changing a decision means a new ADR that supersedes
- **Language**: English (aligned with codebase and PRs)
- **Location**: `docs/adr/` at the repo root, versioned alongside code

## Index

| ADR | Title | Status |
|-----|-------|--------|
| ADR-001 | *(reserved)* | — |
| [ADR-002](ADR-002-server-bound-universe.md) | Server-bound universe in `o-kb-mcp` | Accepted |

## Adding a new ADR

1. Copy `template.md` to `ADR-NNN-short-title.md`
2. Fill in all sections
3. Add a row to the index table above
4. Open a PR — the decision is not Accepted until merged
