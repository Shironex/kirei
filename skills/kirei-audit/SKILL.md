---
name: kirei-audit
description: Audit a codebase for quality and maintainability — code smells, DRY violations, god files, dead code, inconsistent conventions, and unfollowed best practices. Depth-tunable like /kirei-deps; a scout pass sizes how many kirei-refactor agents run in parallel (1 → up to 6) to match the repo. Produces one merged, dependency-ordered cleanup plan, then offers to fix the issues in order via kirei-stitch / kirei-loom. Use whenever a user asks to audit the codebase, find code smells, hunt technical debt, check for DRY violations, find god files or dead code, surface inconsistencies, run a code-quality / health pass, or plan a refactor — even if they don't say "kirei". Invoke with /kirei-audit; the skill asks which depth before working.
---

You have been invoked via `/kirei-audit`. Follow this workflow precisely.

You orchestrate a **code-quality audit**. Depth picks an agent budget; a cheap **scout pass** partitions the in-scope code and spawns only as many `kirei-refactor` agents as the repo actually warrants (1 → up to 6, in parallel). You then **merge** their findings into one dependency-ordered cleanup plan and, unless told otherwise, offer to apply the fixes **in order** via `kirei-stitch` / `kirei-loom`.

You do **not** write code yourself, and you do **not** run the workers sequentially during research — the audit is parallel; only the *fixing* is sequential. The agents report; the user decides what runs next.

This skill reuses the existing **`kirei-refactor`** research agent as its parallel worker. There is no separate audit agent — the worker prompt below carries the full audit taxonomy.

---

## THE AUDIT TAXONOMY

Every worker audits against this taxonomy. Which categories a given worker covers depends on the partition mode (see Step 3).

| # | Category | What to flag |
|---|----------|--------------|
| 1 | **Dead code** | Unused exports, never-imported symbols, commented-out blocks, unreachable branches (`if (false)`), permanently-on/off feature flags, unused imports/vars (trust IDE diagnostics). |
| 2 | **Duplication / DRY** | Copy-paste blocks, logic repeated 3+ times, duplicated type/validation/error-handling/API-call patterns. (3 occurrences = a pattern; 2 may be coincidence.) |
| 3 | **God files & complexity** | Files doing too much (size relative to repo norms), functions >50 lines, nesting 3+ deep, >4–5 params, mixed concerns (fetch + transform + render in one place), circular deps. |
| 4 | **Abstraction quality** | Under-abstraction (logic that should be a shared util) and over-abstraction (single-impl interfaces, factories where a function would do, premature generics). |
| 5 | **Consistency / conventions** | Same job done differently across files (multiple fetch wrappers, mixed error styles), inconsistent naming, mixed import/module styles, inconsistent file/folder structure. |
| 6 | **Best-practice gaps** | Magic numbers/strings, leftover `console.log`/debug prints, `any`/untyped boundaries, swallowed errors, sync work in async paths, missing input validation — relative to the repo's stack. |

---

## 0. PARSE FLAGS

Strip these flags from the task description before proceeding:

| Flag | Meaning |
|---|---|
| `--quick` / `--standard` / `--deep` | Skip the depth question — use this depth directly. |
| `--research-only` | Skip Step 7 (the fix step). Deliver the merged plan only. |
| `--scope <path>` | Audit only this sub-directory / module (e.g. `--scope packages/api`). Defaults to the current directory. |
| `--categories <list>` | Pin the taxonomy categories to audit. Comma list of: `dead-code`, `dup`, `god-files`, `abstractions`, `consistency`, `best-practices`. Default: all six. |
| `--max-agents <n>` | Hard cap on parallel workers (overrides the scout's count, never raises it above the depth cap). |
| `--no-scout` | Skip the scout pass; use the depth's max agent count directly (degrades hybrid → fixed tiers). |

Any flag the user passes must reach the spawned agents' prompts in effect (scope, categories) so the workers act on it.

---

## 1. ASK FOR DEPTH

If the user already passed `--quick`, `--standard`, or `--deep`, skip this step and use that depth.

Otherwise, use AskUserQuestion. Depth sets the **agent budget cap** — the scout then sizes the real count to the repo. Explain the tradeoff:

```
Question: "How deep should the code-quality audit go? Depth caps how many kirei-refactor agents run in parallel; a scout pass then sizes the real count to your repo."
Header: "Depth"
multiSelect: false

Options:
- "Quick — 1 agent, top smells (~2 min)"
  description: "One full-spectrum pass over the scope. Reports the ~10 highest-leverage issues across all categories. Use for a fast read or a small module."

- "Standard — up to 3 agents, by category (Recommended, ~5 min)"
  description: "Splits the taxonomy into category lanes (dead-code+dup / god-files+complexity+abstractions / consistency+best-practices). Scout collapses lanes for small repos. Use for a thorough audit of a normal-sized project."

- "Deep — up to 6 agents, by codebase region (~12 min)"
  description: "Scout partitions the code into modules/regions; each agent runs the FULL taxonomy on its slice. Best parallelism + cross-region duplication detection. Use for a real cleanup sprint on a large repo."
```

Map: "Quick" → `quick` (cap 1), "Standard" → `standard` (cap 3), "Deep" → `deep` (cap 6).

---

## 2. SCOUT PASS *(skip if `--no-scout`)*

Cheaply size the in-scope code **yourself** (the orchestrator) — no agent needed. Use Glob/Grep, not raw shell, so it works cross-platform.

1. Resolve the scope root (`--scope` path or cwd).
2. Glob source files by stack extension (`**/*.{ts,tsx,js,jsx,mjs,cjs,py,go,rs,java,kt,rb,php,cs,vue,svelte}` — adapt to what the repo actually uses).
3. Build a **region map**: group files by their top-level directory under the scope root (in a monorepo, group by package). Record file count per region.
4. Note the total source-file count and the largest regions.

Then compute the **actual agent count**, never above the depth cap and never above `--max-agents`:

**Quick** → always **1** agent. No partition. (Scout still useful to brief the agent on structure.)

**Standard** (cap 3, **partition by category**):
- total source files **< ~15** → **1** agent, all categories.
- **~15–40** → **2** agents: lane A = dead-code + dup + best-practices; lane B = god-files + complexity + abstractions + consistency.
- **> ~40** → **3** agents: lane 1 = dead-code + dup; lane 2 = god-files + complexity + abstractions; lane 3 = consistency + best-practices.
- If `--categories` pins fewer categories, distribute only those across as many lanes as make sense (≤ cap).

**Deep** (cap 6, **partition by region**):
- Merge any region with **< ~5 files** into its nearest sibling so no agent gets a trivial slice.
- agent count = number of regions after merging, capped at **6** (and `--max-agents`).
- **> 6 regions** → bucket the smallest regions together until 6 buckets remain; one agent owns a bucket of dirs.
- **Only 1 meaningful region**, or total **< ~25 files** → fall back to the **Standard** category split (it parallelizes better than one-region-one-agent on a small repo).

Treat the thresholds as guidance — round to the repo's real shape. If the scout result surprises you (e.g. Deep on a tiny repo collapses to 1 agent), say so in the announcement.

---

## 3. ANNOUNCE PLAN

One line stating depth, partition basis, and worker count:

> "Running **kirei-audit** at **<depth>** → scout sized this to **<N>** `kirei-refactor` agent(s) in parallel, split by **<category|region>**. Findings → `docs/audit/`."

Variants:
- `--research-only`: append " (research only — no fixes applied)."
- `--scope <path>`: append " — scoped to `<path>`."
- `--no-scout`: append " (scout skipped — using full depth budget of <cap>)."
- Scout collapsed below the cap: append " (repo small enough that <cap-N> fewer agents are needed)."

---

## 4. SPAWN THE WORKERS — IN PARALLEL

Send **all** Agent calls in a **single message** so they run concurrently. Never spawn them sequentially — parallel is the whole point.

Each worker is the **`kirei-refactor`** agent. It has no shared context — put everything in the prompt. Give each worker a **disjoint slice** (region agents own non-overlapping dirs; category agents own non-overlapping categories) so their findings don't collide.

**Prompt structure for each worker:**

```
Task: Code-quality audit (one slice of a parallel /kirei-audit run).

Working directory: [cwd]
Scope root: [--scope path or cwd]

YOUR SLICE:
[Region mode] Audit ONLY these directories/files: [exact list]. Run the FULL taxonomy on them.
[Category mode] Audit the WHOLE scope, but ONLY these categories: [assigned category names].

AUDIT TAXONOMY — flag issues in your assigned categories:
1. Dead code — unused exports, commented blocks, unreachable branches, dead flags, unused imports (trust IDE diagnostics).
2. Duplication/DRY — copy-paste, logic repeated 3+ times, duplicated type/validation/error/API patterns.
3. God files & complexity — oversized files, functions >50 lines, nesting 3+ deep, >4-5 params, mixed concerns, circular deps.
4. Abstraction quality — under-abstraction (should be shared util) and over-abstraction (single-impl interface, needless factory/generic).
5. Consistency/conventions — same job done differently across files, inconsistent naming, mixed import/module styles, inconsistent structure.
6. Best-practice gaps — magic numbers, leftover console.log/debug, any/untyped boundaries, swallowed errors, sync-in-async, missing validation (stack-relative).

You are part of a parallel kirei-audit run alongside: [other slices].
- Stay strictly in YOUR slice. If you spot something obviously in another slice's territory, NOTE it in your handoff — do NOT fix or deep-dive it.
- SKIP the user-validation step (your STEP 6 "validate scope with user"). You are a non-interactive parallel sub-agent — the orchestrator validates once after merge. Go straight from analysis to writing findings.

For every finding give: file:line, which category, severity (high/med/low), effort (XS/S/M/L), risk, and a one-line fix.

Deliver:
- Write findings to docs/audit/ — use: python "${CLAUDE_PLUGIN_ROOT}/scripts/write-findings.py" "<scope>-<your-slice-id>" --category audit  (fallback: mkdir -p docs/audit and Write docs/audit/YYYY-MM-DD-<scope>-<your-slice-id>.md).
- Then output your KIREI-REFACTOR HANDOFF block.
```

Run them in the **foreground** — you need every result before merging.

---

## 5. WAIT FOR ALL → REVIEW EACH HANDOFF

When all workers complete:

- Read each KIREI-REFACTOR HANDOFF.
- Verify each wrote its file: Glob `docs/audit/*.md` filtered by today's date. If any worker printed `FINDINGS FILE NOT WRITTEN` (or its file is missing), write it yourself from that worker's handoff content using Write at `docs/audit/YYYY-MM-DD-<scope>-<slice-id>.md`.
- Spot-check 1–2 `file:line` references per worker — confirm they exist and say what the worker claims.

If any worker errored out entirely, report that to the user before merging — do **not** silently drop a slice.

---

## 6. MERGE → ONE ORDERED CLEANUP PLAN

Write a **combined** doc that synthesizes the per-slice reports (link them; don't re-paste them wholesale).

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/write-findings.py" "<scope>-audit" --category audit << 'FINDINGS'
# Code-Quality Audit: <scope>

**Date:** YYYY-MM-DD
**Skill:** /kirei-audit
**Depth:** <quick|standard|deep>  ·  **Workers:** <N> (<category|region> split)
**Scope:** <what was audited>

## Health Snapshot
| Category | High | Med | Low |
|----------|------|-----|-----|
| Dead code | . | . | . |
| Duplication/DRY | . | . | . |
| God files & complexity | . | . | . |
| Abstraction quality | . | . | . |
| Consistency/conventions | . | . | . |
| Best-practice gaps | . | . | . |

One-paragraph overall read: what's healthy, what's the worst debt, where to start.

## Per-Slice Reports
- [slice id] — docs/audit/YYYY-MM-DD-<scope>-<slice-id>.md
- ...

## Cross-Cutting Findings (highest leverage)
[Issues the SAME across multiple slices/regions — e.g. the same util duplicated in 4 modules.
Dedupe here: if region agents each flagged the same shared duplication, collapse to one entry. These rank first.]

## Ordered Cleanup Plan
Refactors have dependencies and touch overlapping files — this order avoids breaking things mid-way and is the order the fix step runs in:

### Phase 1 — Remove dead code  [safe, no deps]
| Item | file:line | Effort | Risk |
|------|-----------|--------|------|

### Phase 2 — Extract shared utilities/abstractions  [creates targets later phases need]
| Item | extract to | from | Effort | Risk |
|------|-----------|------|--------|------|

### Phase 3 — Consolidate duplicates  [depends on Phase 2]
| Pattern | occurrences (file:line) | replace with | Effort | Risk |
|---------|------------------------|--------------|--------|------|

### Phase 4 — Normalize consistency/conventions
| Item | files | target convention | Effort | Risk |
|------|-------|-------------------|--------|------|

### Phase 5 — Split god files  [depends on Phase 2 extractions]
| File | lines | split into | Effort | Risk |
|------|-------|-----------|--------|------|

### Phase 6 — Best-practice fixes
| Item | file:line | fix | Effort | Risk |
|------|-----------|-----|--------|------|

## Execute Complexity Per Phase
- Phase 1, 6 → kirei-stitch (focused, low-risk)
- Phase 2, 4 → kirei-stitch unless wide → kirei-loom
- Phase 3, 5 → kirei-loom (multi-file, ordering matters)

## What NOT to Touch
[Things that look messy but are intentional, generated, vendored, or too risky to refactor now.]
FINDINGS
```

If `CLAUDE_PLUGIN_ROOT` is not set: `mkdir -p docs/audit` via Bash, then Write `docs/audit/YYYY-MM-DD-<scope>-audit.md`.

Then output the handoff block:

```
---
## KIREI-AUDIT HANDOFF

**Combined plan:** docs/audit/YYYY-MM-DD-<scope>-audit.md
**Depth / workers:** <depth> · <N> agents (<split>)
**Per-slice reports:** linked in the combined doc

**Top cross-cutting issues:**
- [Item appearing across slices] — `file:line`

**Ordered phases (run in this order):**
1. Remove dead code — [count] items — stitch
2. Extract shared utilities — [count] — stitch/loom
3. Consolidate duplicates — [count] — loom
4. Normalize conventions — [count] — stitch/loom
5. Split god files — [count] — loom
6. Best-practice fixes — [count] — stitch

**This skill stops here unless you approve fixes (Step 7). Fixing runs sequentially, phase by phase.**
---
```

---

## 7. OFFER ORDERED EXECUTION — *the "fix in order" step*

Skip entirely if `--research-only` was passed (just point the user at the doc).

Otherwise use AskUserQuestion:

```
Question: "Audit done — <X> issues across <Y> categories. Want me to fix them in order now? Fixing runs SEQUENTIALLY (refactors share files; parallel would collide), verifying typecheck/tests between phases."
Header: "Fix?"
multiSelect: false

Options:
- "Fix all phases in order"
  description: "Run Phases 1→6 sequentially via kirei-stitch/kirei-loom. Stop and report if any phase breaks typecheck/tests."

- "Fix only safe phases (1–2)"
  description: "Dead-code removal + utility extraction only — lowest risk. Leave consolidation / god-file splits for a later, deliberate pass."

- "Let me pick phases"
  description: "Tell me which phases to run; I'll run those in dependency order."

- "Research only — stop here"
  description: "Keep the plan; apply nothing. You can run fixes later via /kirei or by re-invoking with the doc."
```

If the user opts to fix, run the chosen phases **sequentially** — one phase per agent, never in parallel:

For each phase in order:
1. Spawn `kirei-stitch` (focused/low-risk phases) or `kirei-loom` (multi-file phases per the complexity map) in the **foreground**, with:
   - the combined plan path,
   - the exact phase's items pasted in,
   - a hard rule: implement ONLY this phase's items; do not start a later phase.
2. When it returns, the agent must have run typecheck + relevant tests and left them **green**. If a phase leaves them red, **stop** — do not start the next phase. Report which phase broke and the failure output.
3. Then proceed to the next chosen phase.

Never push commits or open a PR from this skill (agents may commit locally if the project's convention is to commit; you do not push). Never run a dev server.

---

## 8. REPORT TO USER

One short paragraph:
- Depth + how many agents the scout sized, on what split.
- One-sentence health read (e.g. "Standard audit, 3 agents by category: 4 god files, 6 DRY clusters, 11 dead exports").
- What was fixed, if anything (phases run + verification result) — or "research only, no changes."
- Pointer to `docs/audit/<file>.md` for the full plan.
- Recommended next move (e.g. run remaining phases later, or `/kirei-deps` / `/kirei-prism` for an adjacent angle).

---

## RULES

1. **Always ask depth unless flagged.** Quick / Standard / Deep produce very different work; running Deep on a tiny repo wastes minutes, running Quick on a large one produces a shallow snapshot.
2. **Scout sizes; depth caps.** Never spawn more workers than the depth cap (1/3/6) or `--max-agents`. Collapse to fewer when the repo is small — don't spin up agents with trivial slices.
3. **Audit in parallel, fix sequentially.** All workers go in one message. Fixes run one phase at a time because refactors share files and have ordering dependencies.
4. **Disjoint slices.** Region agents own non-overlapping dirs; category agents own non-overlapping categories. Overlap produces duplicate findings and merge conflicts.
5. **Workers skip user-validation.** They are non-interactive sub-agents; the orchestrator validates once at merge. Make this explicit in every worker prompt.
6. **Order is dependency order, not severity order.** Dead code first, extractions before consolidations, splits after extractions. Don't reorder phases by severity — you'll break things mid-refactor.
7. **Never push or open PRs from this skill; never run a dev server.** Fixes are local; the user pushes.
8. **Stop on red.** If a fix phase breaks typecheck/tests, halt the sequence and report — do not plow into the next phase on top of a broken build.
