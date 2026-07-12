# kirei

A specialized agent team for Claude Code. Automated research → execute workflow with domain-specific specialists.

## Agents

### Research agents (analyse, prescribe, hand off)

Each research agent writes its findings to its own folder under `docs/`, so reports stay organised by domain instead of piling up in one place.

| Agent | Model | Findings folder | Purpose |
|-------|-------|----------------|---------|
| `kirei-research` | sonnet | `docs/research/` | General research & investigation |
| `kirei-security` | opus | `docs/security/` | Security audit (OWASP, auth, injection) |
| `kirei-ui` | sonnet | `docs/ui/` | UI/UX audit (impeccable skills integration) |
| `kirei-refactor` | sonnet | `docs/refactor/` | Code quality & refactoring plan |
| `kirei-perf` | sonnet | `docs/perf/` | Performance bottleneck analysis |
| `kirei-arch` | sonnet | `docs/arch/` | Architecture mapping + Mermaid diagram |
| `kirei-test` | sonnet | `docs/test/` | Test coverage gaps, missing edge cases, flake hunt |
| `kirei-migrate` | sonnet | `docs/migrate/` | Dependency / framework upgrade plan with breaking-change map |
| `kirei-review` | sonnet | `docs/review/` | Code review of pending changes or a GitHub PR; can also classify reviewer comments (`--address-pr-comments`) |
| `kirei-debug` | opus | `docs/debug/` | Reproduce + root-cause a specific bug; may add tracked temp instrumentation |
| `kirei-data` | sonnet | `docs/data/` | Schema / migration safety / query / index audit |
| `kirei-deps` | sonnet | `docs/deps/` | Dependency safety: package-manager audit + Dependabot alerts + safe-bump list + ordered upgrade plan (depth-tunable) |
| `kirei-observability` | sonnet | `docs/observability/` | Logs, metrics, traces audit — coverage gaps, structure, PII safety, correlation, mis-leveled logs |
| `kirei-bundle` | sonnet | `docs/bundle/` | Shipped-bytes deep dive — composition, duplicates, missing splits, asset weight, with KB savings |
| `kirei-license` | sonnet | `docs/license/` | Dependency license compatibility, copyleft contagion, NOTICE/attribution gaps |
| `kirei-resilience` | sonnet | `docs/error/` | Error handling audit — swallowed catches, error taxonomy, boundary leaks, missing timeouts/retries, async hazards |
| `kirei-eval` | sonnet | `docs/eval/` | Evaluation infrastructure audit — eval suites, baselines, golden datasets, regression detection, CI integration |
| `kirei-sentry` | sonnet | `docs/sentry/` | Production-ready Sentry setup — framework-aware (Electron/Next/Vite/Node/RN), consent gating, recursive PII scrubbing, CI-only source maps, region handling, secret wiring |
| `/kirei-prism` (skill) | — | `docs/chain/` | Combined report from a multi-lens parallel run |
| `/kirei-audit` (skill) | — | `docs/audit/` | Code-quality audit — scales parallel `kirei-refactor` agents to repo size, merges into one dependency-ordered cleanup plan, offers ordered fixes |
| `/kirei-discuss` (skill) | — | `docs/discuss/` | Conversational pros/cons audit of an idea/feature/project before any code is written |

### Execute & review agents

| Agent | Model | Purpose |
|-------|-------|---------|
| `kirei-stitch` | sonnet | Execute findings — normal/focused tasks |
| `kirei-loom` | opus | Execute findings — complex/multi-file tasks |
| `kirei-gate` | opus | Adversarial, read-only merge-gate reviewer — reviews a PR/diff and returns exactly `VERDICT: MERGE` or `VERDICT: HOLD`. No Edit/Write, no AskUserQuestion, so it is background-safe. Used by `/kirei-wave`. |

## Skills

| Skill | Purpose |
|---|---|
| `/kirei [task]` | Single-lens orchestrator — auto-detects type and complexity, spawns the right research agent, then the right execute agent. |
| `/kirei-prism [task]` | Multi-lens orchestrator — runs up to 4 research agents in parallel against the same target and merges their findings into one report. Research-only by design. |
| `/kirei-deps` | Dependency-safety orchestrator — asks for depth (quick / standard / deep) at invoke time, runs `kirei-deps`, optionally hands safe bumps to `kirei-stitch` and recommends `/kirei migrate` for risky majors. |
| `/kirei-audit` | Code-quality orchestrator — asks for depth (quick / standard / deep), scout-sizes parallel `kirei-refactor` agents to the repo (1 → 6), merges findings into one dependency-ordered cleanup plan, then offers to fix the phases in order via `kirei-stitch` / `kirei-loom`. Audits code smells, DRY violations, god files, dead code, inconsistent conventions, and best-practice gaps. |
| `/kirei-discuss [idea]` | Conversational pros/cons audit before any code — walks problem framing, value, cost, risks, alternatives, reversibility, and a clear next-step recommendation (build / spike / wait / don't-build). Writes a decision doc to `docs/discuss/`. |
| `/kirei-sentry` | Sentry setup orchestrator — asks the consent model + scope + region, runs `kirei-sentry` to design a framework-specific integration (consent-gated, PII-scrubbed, CI source maps), then `kirei-loom` to implement it. Verifies the current SDK API via Ref first. |
| `/kirei-templatize` | Strips an existing JS/TS repo into a reusable starter template via parallel disjoint-file phase agents. Asks target/detection/execution/commit/attribution preferences up front. |
| `/kirei-wave` | Worktree-parallel multi-slice execute orchestrator — takes slices (from `--findings`, `--audit`, a wayfinder `--map`, or an inline list), fans out one worktree-isolated builder (`kirei-stitch`/`kirei-loom`) per PR that bootstraps → implements → runs the gate battery → opens a PR (`Closes #N`, labels, no AI attribution), then gates each PR (CI + attribution grep + `kirei-gate`) and merges in dependency order. Keeps a `.kirei/wave-*.md` ledger; never runs parallel worktrees on shared files. |

### `/kirei` flags

| Flag | Effect |
|---|---|
| `--research-only` | Skip the execute step. Deliver findings + handoff only. |
| `--findings <path>` | Skip research. Use an existing findings doc and go straight to execute. |
| `--pr <N>` | Force `kirei-review` mode against GitHub PR #N. |
| `--address-pr-comments <N>` | `kirei-review` fetches PR comments, classifies each (valid / out-of-scope / invalid / nit / resolved), and only valid ones are handed to `kirei-stitch`/`kirei-loom`. Invalid ones come back with suggested replies the user can post. |

### `/kirei-prism` flags

| Flag | Effect |
|---|---|
| `--types <a,b,c>` | Pin the lens set explicitly (otherwise auto-detected). Valid: `security, ui, refactor, perf, arch, test, data, observability, bundle, error, general`. Capped at 4. |

### `/kirei-deps` flags

| Flag | Effect |
|---|---|
| `--quick` / `--standard` / `--deep` | Skip the depth question. `quick` = audit only. `standard` = + Dependabot + safe-bumps. `deep` = + outdated map + ordered upgrade plan. |
| `--research-only` | Skip the kirei-stitch hand-off for safe bumps. Report only. |
| `--no-dependabot` | Skip Dependabot fetching even at standard/deep (e.g., private repo, no alert access). |
| `--manager <pm>` | Override package-manager detection. Valid: `pnpm, npm, yarn, bun, poetry, uv, pip, cargo, go, bundler`. |
| `--scope <path>` | Run audit only in a sub-directory (useful in monorepos). |

### `/kirei-audit` flags

| Flag | Effect |
|---|---|
| `--quick` / `--standard` / `--deep` | Skip the depth question. Depth caps the parallel agent budget (1 / 3 / 6); a scout pass sizes the real count to the repo. |
| `--research-only` | Produce the merged cleanup plan only — skip the ordered fix step. |
| `--scope <path>` | Audit only a sub-directory / module (useful in monorepos). |
| `--categories <list>` | Pin taxonomy categories: `dead-code, dup, god-files, abstractions, consistency, best-practices`. Default: all six. |
| `--max-agents <n>` | Hard cap on parallel workers (never raises above the depth cap). |
| `--no-scout` | Skip scout sizing; use the depth's full agent budget directly. |

## How it works

```mermaid
flowchart TD
    skill(["/kirei:kirei task"])

    skill --> detect{auto-detect\ntype}

    detect -->|general| kirei[kirei-research\nsonnet · cyan]
    detect -->|security| sec[kirei-security\nopus · red]
    detect -->|ui| ui[kirei-ui\nsonnet · magenta]
    detect -->|refactor| ref[kirei-refactor\nsonnet · yellow]
    detect -->|perf| perf[kirei-perf\nsonnet · cyan]
    detect -->|arch| arch[kirei-arch\nsonnet · blue]
    detect -->|test| test[kirei-test\nsonnet · green]
    detect -->|migrate| mig[kirei-migrate\nsonnet · yellow]
    detect -->|review| rev[kirei-review\nsonnet · cyan]
    detect -->|debug| dbg[kirei-debug\nopus · red]
    detect -->|data| data[kirei-data\nsonnet · blue]
    detect -->|observability| obs[kirei-observability\nsonnet · cyan]
    detect -->|bundle| bun[kirei-bundle\nsonnet · yellow]
    detect -->|license| lic[kirei-license\nsonnet · yellow]
    detect -->|error| err[kirei-resilience\nsonnet · red]
    detect -->|eval| ev[kirei-eval\nsonnet · green]

    kirei-research --> findings
    sec --> findings
    ui --> findings
    ref --> findings
    perf --> findings
    arch -->|advisory only| findings
    test --> findings
    mig --> findings
    rev --> findings
    dbg --> findings
    data --> findings
    obs --> findings
    bun --> findings
    lic --> findings
    err --> findings
    ev --> findings

    findings([docs/&lt;category&gt;/\nYYYY-MM-DD-slug.md])

    findings -->|simple scope| stitch[kirei-stitch\nsonnet · green]
    findings -->|complex scope| loom[kirei-loom\nopus · yellow]
    arch -->|no code changes| done
    findings -->|--research-only| done

    stitch --> done([changes implemented\n+ verified])
    loom --> done
```

1. `/kirei` auto-detects task type and complexity (stitch/loom)
2. Spawns the appropriate `kirei-*` research agent
3. Research agent investigates, validates findings with the user via AskUserQuestion, writes `docs/<category>/YYYY-MM-DD-<slug>.md` in the target repo (one folder per agent — see table above), and produces a structured handoff
4. Spawns `kirei-stitch` (sonnet) or `kirei-loom` (opus) with the handoff (skipped if `--research-only`)
5. Execute agent implements and verifies

### Multi-lens (`/kirei-prism`)

```mermaid
flowchart TD
    chain(["/kirei-prism task"])
    chain --> lenses{detect\nlenses}
    lenses -->|in parallel| a[kirei-security]
    lenses -->|in parallel| b[kirei-perf]
    lenses -->|in parallel| c[kirei-arch]
    a --> merge[merge findings]
    b --> merge
    c --> merge
    merge --> combined([docs/chain/\nYYYY-MM-DD-slug.md])
    combined -->|user decides next move| user([user runs /kirei or /kirei type])
```

Use when one question needs more than one perspective. Capped at 4 parallel agents. Research-only by design — the merged report points the user (or a follow-up `/kirei`) to the highest-leverage fixes.

### Code-quality audit (`/kirei-audit`)

```mermaid
flowchart TD
    audit(["/kirei-audit"])
    audit --> depth{ask depth\nquick/standard/deep}
    depth --> scout[scout pass\nsize repo → agent count]
    scout -->|1 agent| q[full-spectrum pass]
    scout -->|≤3 by category| s[dead-code+dup · god-files · consistency]
    scout -->|≤6 by region| d[one agent per module]
    q --> merge[merge → ordered plan]
    s --> merge
    d --> merge
    merge --> plan([docs/audit/\nYYYY-MM-DD-slug.md])
    plan --> fix{fix in order?}
    fix -->|yes, sequential| exec[kirei-stitch / kirei-loom\nphase by phase, verify between]
    fix -->|--research-only| done([plan only])
    exec --> done2([cleanup applied\n+ verified])
```

Depth **caps** the parallel agent budget (1 / 3 / 6); a scout pass **sizes** the real count to the repo. Audit runs in parallel; fixing runs **sequentially**, phase by phase in dependency order (dead code → extractions → consolidations → conventions → god-file splits → best-practice fixes), verifying typecheck/tests between each.

### PR comment workflow (`kirei-review --address-pr-comments`)

```mermaid
flowchart LR
    invoke(["/kirei review --address-pr-comments 123"])
    invoke --> fetch[fetch PR comments\nvia gh]
    fetch --> classify{classify each\ncomment}
    classify -->|valid| toFix[hand to kirei-stitch/loom\nto address]
    classify -->|invalid / misread| reply[suggest reply text\nuser posts manually]
    classify -->|out of scope| follow[recommend follow-up issue]
    classify -->|nit| optional[optional, only if user asks]
```

The agent never pushes commits or posts comments — it produces a triage report; you decide what lands.

### Parallel execution (`/kirei-wave`)

```mermaid
flowchart TD
    wave(["/kirei-wave --findings|--audit|--map|--slices"])
    wave --> slice[normalize slices\nscope · issue · complexity · files]
    slice --> plan[plan waves\ndisjoint files per wave]
    plan --> spawn[spawn 1 worktree builder / slice\nkirei-stitch / kirei-loom]
    spawn --> pr[bootstrap → implement → gate battery\n→ commit no-attribution → open PR Closes #N]
    pr --> gate{CI green?\nattribution clean?\nkirei-gate: MERGE?}
    gate -->|all yes| merge[merge in dependency order]
    gate -->|any no| hold[HOLD → back to builder or user]
    merge --> ledger([.kirei/wave-YYYY-MM-DD.md])
```

Turns a set of PR-sized slices into worktree-isolated builders, one per PR, then gates each PR (CI + attribution grep + an adversarial `kirei-gate` review) and merges in dependency order. Never runs parallel worktrees on files that overlap; keeps a ledger so the plan survives context compaction. Feeds naturally from `/kirei` findings, `/kirei-audit` phases, or a wayfinder map.

## Install

### As a Claude Code plugin (recommended)

Add the kirei marketplace, then install the plugin:

```
/plugin marketplace add Shironex/kirei
/plugin install kirei@kirei
/reload-plugins
```

Once installed, the skill is invoked as:
```
/kirei:kirei [task description]
```

### Manual install (global, standalone)

Agents and skills go directly into your global `~/.claude/` directories — no marketplace needed. Skills are **directories** (`~/.claude/skills/<name>/SKILL.md`), so copy the whole `skills/` tree, not a single file. Skills then invoke as `/kirei`, `/kirei-prism`, `/kirei-wave`, etc.

```bash
git clone https://github.com/Shironex/kirei.git
cp kirei/agents/*.md ~/.claude/agents/
cp -R kirei/skills/* ~/.claude/skills/
cp -R kirei/scripts ~/.claude/skills/kirei/scripts   # optional: the write-findings helper (set CLAUDE_PLUGIN_ROOT or rely on the per-agent fallback)
```

> Standalone installs have no `CLAUDE_PLUGIN_ROOT`, so agents fall back to `mkdir -p docs/<category>` + the Write tool for findings — the plugin install is the smoother path.

### Local development / testing

```bash
claude --plugin-dir ./kirei
```

### Updating

Plugin install:
```
/plugin marketplace update kirei
/reload-plugins
```

Manual install: pull latest and re-run the copy commands.

## Design decisions

- **Ref MCP for docs** — agents use `mcp__Ref__ref_*` for library documentation; falls back to WebSearch if unavailable. context7 is not used.
- **AskUserQuestion after investigation** — findings are validated with the user once analysis is complete, not before. Prevents scope conversations from slowing down clear tasks.
- **Findings persistence, organised by domain** — every investigation writes to `docs/<category>/YYYY-MM-DD-<slug>.md` in the target repo (one folder per agent: `docs/security/`, `docs/perf/`, `docs/refactor/`, `docs/test/`, `docs/migrate/`, `docs/review/`, `docs/debug/`, `docs/data/`, `docs/arch/`, `docs/ui/`, `docs/observability/`, `docs/bundle/`, `docs/license/`, `docs/error/`, `docs/eval/`, `docs/chain/`, `docs/audit/`, `docs/discuss/`, plus `docs/research/` for the general agent). Findings survive across sessions and stay sorted instead of piling up in one folder.
- **Two execute tiers** — kirei-stitch (sonnet) for focused changes, kirei-loom (opus) for complex multi-file work. Research agent recommends which; orchestrator skill decides.
- **Skill = front door, agent = engine** — `/kirei-deps` and `/kirei-sentry` are skills that gather decisions and orchestrate; the same-named `kirei-deps` / `kirei-sentry` agents are the research engines they spawn. New additions should follow this split deliberately.
- **Findings folders are stable labels** — a couple of agents keep their original findings-folder name after a rename so historical reports stay put: `kirei-resilience` writes to `docs/error/`, and the `/kirei-prism` skill merges into `docs/chain/`.
