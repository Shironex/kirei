# Changelog

All notable changes to kirei are documented in this file. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [2.0.0] - 2026-07-12

A breaking rework of the v1.x line: clearer agent names, the Omniscribe MCP integration removed entirely, a new adversarial merge-gate reviewer, a worktree-parallel execute orchestrator, model tiering, and two silent-failure bug fixes.

### Added
- `kirei-gate` — an adversarial, read-only merge-gate reviewer (opus, no Edit/Write/AskUserQuestion) that ends every review with exactly `VERDICT: MERGE` or `VERDICT: HOLD`, defaulting to HOLD on uncertainty around security/exec/data-loss surfaces.
- `/kirei-wave` — a worktree-parallel, multi-slice execute orchestrator: one worktree-isolated builder per PR (bootstrap → implement → gate battery → commit → open PR), then gates each PR (CI + attribution grep + `kirei-gate`) and merges in dependency order, tracked in a `.kirei/wave-*.md` ledger.

### Changed
- **Breaking renames:** `kirei-build` → `kirei-stitch`, `kirei-forge` → `kirei-loom`, `kirei` (general agent) → `kirei-research`, `kirei-error` → `kirei-resilience`, `/kirei-chain` → `/kirei-prism`. The plugin name and the `/kirei` orchestrator skill are unchanged. Findings folders kept stable across renames (`kirei-resilience` still writes `docs/error/`, `/kirei-prism` still merges into `docs/chain/`).
- Model tiering: opus reserved for `kirei-loom`, `kirei-security`, `kirei-debug`, and `kirei-gate`; every other agent (17 of 21) now runs on sonnet.
- README, `plugin.json`, and `marketplace.json` refreshed throughout for the new names, the model map, and a new "skill = front door, agent = engine" design note; manual-install instructions fixed (skills are directories — copy the whole `skills/` tree).

### Removed
- Omniscribe MCP integration — dropped from every agent's tools frontmatter, along with the STEP 0 announce blocks and task-tracking prose. The personal `.mcp.json` that leaked an absolute local path and a session ID was also deleted.

### Fixed
- `/kirei-prism` fanned out parallel lens workers without telling them to skip the mandatory `AskUserQuestion` validation step, so a multi-lens run could stall on concurrent user prompts; workers now skip validation when spawned non-interactively.
- `kirei-ui` and `kirei-perf` used unsupported ripgrep look-arounds and a literal `\|` alternation that silently errored out and returned an empty "clean" scan; rewritten as positive-grep-then-Read with an `rg -P` fallback.

## [1.0.0] - 2026-04-24

The mature v1.x line — everything kirei grew into across nine incremental releases (v1.1.0 → v1.10.0) after the v0.1.0 genesis.

### Added
- A full specialist research-agent fleet: 18 opus agents covering general research, security, UI/UX, refactoring, performance, architecture, test coverage, migrations, code review, debugging, data/schema safety, dependency safety, observability, bundle size, licensing, error handling, eval infrastructure, and Sentry setup.
- Per-category findings folders (`docs/<category>/YYYY-MM-DD-slug.md`) replacing the original flat `docs/research/` pile.
- `/kirei-chain` — parallel multi-lens research (up to 4 agents at once) merged into one combined report.
- `kirei-deps` agent + `/kirei-deps` skill — package-manager audit, Dependabot cross-reference, depth-tunable safe-bump list and upgrade plan.
- `/kirei-audit` — scout-sized parallel code-quality audit merged into a dependency-ordered cleanup plan, with ordered fixes via `kirei-build`/`kirei-forge`.
- `/kirei-discuss` — conversational pros/cons audit for an idea before any code is written.
- `kirei-sentry` agent + `/kirei-sentry` skill — framework-aware, consent-gated, PII-scrubbing production Sentry setup.
- `/kirei-templatize` — strips an existing repo into a reusable starter template via parallel disjoint-file phase agents.
- Mermaid diagrams in `kirei-arch` findings and the README architecture overview.
- Claude Code plugin packaging (`.claude-plugin/marketplace.json` + `plugin.json`) alongside the original manual global-copy install.

### Changed
- Hardened the write-findings step across every research agent to reduce silent "findings not written" failures.

Two-tier execute agents (`kirei-build` sonnet / `kirei-forge` opus) and the Omniscribe status/task integration carried forward unchanged from v0.1.0.

## [0.1.0] - 2026-04-24

The genesis: the first cut of kirei as a research → execute agent team for Claude Code.

### Added
- Research → execute workflow: a research specialist investigates and validates findings with the user (`AskUserQuestion`) before any code is written, then hands off to an execute agent.
- Six research agents (opus): `kirei` (general), `kirei-security`, `kirei-ui`, `kirei-refactor`, `kirei-perf`, `kirei-arch`.
- Two execute tiers: `kirei-build` (sonnet, focused/single-file) and `kirei-forge` (opus, complex/multi-file).
- `/kirei [task]` — the orchestrator skill: auto-detects task type and complexity, spawns the matching research agent then execute agent.
- Findings persistence to `docs/research/YYYY-MM-DD-topic.md` in the target repo.
- Ref MCP for library documentation, with a WebSearch fallback.
- Omniscribe integration — agents update `omniscribe_status` / `omniscribe_tasks` as they work.
