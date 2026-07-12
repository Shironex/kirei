---
name: kirei-prism
description: Run multiple kirei research agents in parallel against the same target and merge their findings into one combined report. Use when a question needs more than one lens (e.g., "audit this module for security AND performance AND architecture", or "audit observability AND error handling together"). Invoke with /kirei-prism followed by a task description; optionally pass --types security,perf,arch to pin the lens set. Valid lenses: security, ui, refactor, perf, arch, test, data, observability, bundle, error, general.
---

You have been invoked via `/kirei-prism`. Follow this workflow precisely.

You orchestrate **multiple research agents in parallel** on the same target, then merge their findings into one combined doc and one combined handoff.

You do **not** spawn execute agents. The user (or a follow-up `/kirei`) decides how to act on the merged findings.

---

## 1. PARSE THE INVOCATION

Extract from the user's prompt:

- **Task description** — the actual thing to investigate (everything that isn't a flag).
- **`--types <comma-list>`** — optional explicit lens set. Valid values: `security`, `ui`, `refactor`, `perf`, `arch`, `test`, `data`, `observability`, `bundle`, `error`, `general`.
- **`--research-only`** — accepted and implied (this skill is research-only by definition).

If `--types` is **not** provided, **auto-detect** by scanning the task for trigger keywords from the table below. Pick **all** that match (this skill is for multi-lens questions). If only one lens matches, tell the user that `/kirei` is the better tool and ask whether to continue anyway.

| Lens | Trigger keywords |
|---|---|
| `security` | auth, vulnerability, injection, XSS, CSRF, secret, permission, CVE, exploit, token, session |
| `ui` | component, layout, design, styling, UX, accessibility, visual, responsive, a11y, animation |
| `refactor` | cleanup, refactor, technical debt, extract, dead code, duplication, smell, restructure |
| `perf` | slow, performance, bundle, optimize, memory, N+1, latency, cache, render speed |
| `arch` | architecture, structure, dependencies, coupling, module boundaries, system design |
| `test` | tests, coverage, untested, flaky, edge cases, regression |
| `data` | schema, migration, query, index, ORM, FK, table, integrity |
| `observability` | logging, metrics, tracing, telemetry, PII in logs, log levels, correlation id |
| `bundle` | bundle size, code splitting, lazy load, tree-shake, vendor chunk, gzipped size |
| `error` | error handling, swallowed catch, generic Error, error contract, no timeouts, unhandled rejection |
| `general` | (fallback for one of the slots if the question is broad) |

**Not lenses** — `migrate`, `debug`, `review`, `deps`, `license`, and `eval` are single-purpose research flows, not multi-angle audits. If the user's prompt is really about "upgrade pkg X" or "find why test Y fails" or "review PR #123" or "audit our dependencies" or "license compatibility" or "audit our eval suite", recommend `/kirei` (or `/kirei-deps`) instead — chain mode adds noise without adding insight.

Cap at **4 lenses** maximum. When more than 4 match, drop in this priority order (drop earliest first):

1. `general` — almost always redundant when 2+ specific lenses match
2. `ui` — usually orthogonal to security/perf/data; survives only if explicitly raised
3. `refactor` — overlaps with `arch` for structural concerns
4. `test` — coverage is rarely the most urgent angle in a multi-lens audit

`security`, `data`, `perf`, and `arch` survive ties by default. Tell the user which 4 you picked and why; offer to swap.

---

## 2. ANNOUNCE PLAN

One line:

> "Running **kirei-{a}** + **kirei-{b}** + **kirei-{c}** in parallel against [target]. Will merge into a single combined findings doc."

---

## 3. SPAWN THE RESEARCH AGENTS — IN PARALLEL

This is the whole point of the skill. Send **all** Agent calls in a **single message** so they execute concurrently. Do not spawn them sequentially.

For each lens, pick the agent:

| Lens | Agent |
|---|---|
| `security` | `kirei-security` |
| `ui` | `kirei-ui` |
| `refactor` | `kirei-refactor` |
| `perf` | `kirei-perf` |
| `arch` | `kirei-arch` |
| `test` | `kirei-test` |
| `data` | `kirei-data` |
| `observability` | `kirei-observability` |
| `bundle` | `kirei-bundle` |
| `error` | `kirei-resilience` |
| `general` | `kirei-research` |

Each agent writes its findings to its own category folder (e.g. `docs/security/`, `docs/perf/`, `docs/arch/` — see the per-agent prompts).

**Prompt structure for each spawned agent** (each agent has no shared context — include everything):

```
Task: [exact task description from the user]

Working directory: [current working directory]

Context:
[Any relevant context from the conversation — file paths, symptoms, recent changes, constraints]

You are part of a parallel kirei-prism investigation alongside: [other agents in this run].
Stay in YOUR lens — do not duplicate the others' work. Note in your handoff if you see something obviously in another lens.

SKIP the user-validation step (your "validate findings with user" AskUserQuestion step). You are a non-interactive parallel sub-agent — the orchestrator validates once after the merge. Do NOT call AskUserQuestion; go straight from analysis to writing findings. (Several lenses running at once would otherwise each block on their own user prompt and deadlock the run.)

Deliver: structured KIREI HANDOFF block + write findings to your category folder
(e.g. docs/security/ for kirei-security, docs/perf/ for kirei-perf — see your agent prompt for the exact path).
```

Run them in the **foreground**. You need every result before the merge step.

If `kirei-arch` is one of the lenses, note that it's advisory only — that's fine for chain mode (we're not auto-executing anyway).

---

## 4. WAIT FOR ALL → REVIEW EACH HANDOFF

When all parallel agents complete:

- For each one, read its KIREI HANDOFF block.
- Verify each agent wrote a findings file. Glob the lens-specific folder filtered by today's date (e.g. `docs/security/YYYY-*.md` where YYYY is the current year). If any agent printed `FINDINGS FILE NOT WRITTEN`, write that one yourself from its handoff content using the Write tool to the correct category folder.
- Spot-check 1-2 file paths each agent referenced — make sure they exist.

If any agent failed entirely (errored out, no handoff), report that to the user before merging. Do not silently drop a lens.

---

## 5. WRITE COMBINED FINDINGS DOC

Write a **new** combined doc that links to and synthesizes the per-lens docs. Don't duplicate the entire per-lens content — link to the originals and pull out the cross-cutting takeaways.

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/write-findings.py" "<short-topic-slug>" --category chain << 'FINDINGS'
# Combined Findings: <Topic>

**Date:** YYYY-MM-DD
**Skill:** /kirei-prism
**Lenses:** [list — e.g., security, perf, arch]
**Scope:** [what was investigated]

## Per-Lens Reports
- **Security:** docs/security/YYYY-MM-DD-<slug>.md
- **Performance:** docs/perf/YYYY-MM-DD-<slug>.md
- **Architecture:** docs/arch/YYYY-MM-DD-<slug>.md

## Cross-Cutting Themes
[Patterns that appeared in 2+ lenses — these are the highest-leverage findings.
Example: "Both security and perf flag the unbounded admin query at orders.ts:54 —
security as data-exposure risk, perf as DoS risk. Single fix addresses both."]

## Conflicts Between Lenses
[Where lens recommendations disagree.
Example: "kirei-refactor wants to inline the cache wrapper for clarity;
kirei-perf wants to keep the wrapper for memoization. Recommend keeping the wrapper."]

## Unified Priority Order
Rank fixes considering ALL lenses, not just severity within one lens:
1. [Cross-cutting blocker — addresses multiple lens findings] — owner lens(es)
2. [Critical security finding] — security
3. [Critical perf finding] — perf
4. ...

## Recommended Execution Strategy
[One PR per lens? Single bundled PR? Stagger over a sprint?
Justify based on the conflicts and cross-cuts above.]

## Out of Scope (Surfaced but Not Investigated)
[Anything the agents flagged outside their own lens that wasn't picked up by another lens —
recommend a follow-up /kirei or /kirei-prism run.]
FINDINGS
```

If `CLAUDE_PLUGIN_ROOT` is not set: `mkdir -p docs/chain` via Bash, then use Write to write `docs/chain/YYYY-MM-DD-<slug>.md`.

---

## 6. OUTPUT COMBINED HANDOFF

```
---
## KIREI-PRISM HANDOFF

**Combined report:** docs/chain/YYYY-MM-DD-<slug>.md
**Lenses:** [list]
**Per-lens reports:** linked in the combined doc (one file per lens, in its own category folder)

**Cross-cutting blockers:**
- [Item that appeared in 2+ lenses] — `file:line`

**Unified priority order (top 5):**
1. ...
2. ...

**Suggested next step:**
- Single broad implementation: `/kirei [task] --findings docs/chain/YYYY-MM-DD-<slug>.md`
- Per-lens implementation: spawn `/kirei` separately for each lens's top item

**This skill does NOT auto-execute — user decides how to act on the merged findings.**
---
```

---

## 7. REPORT TO USER

One short paragraph:
- Lenses run, in parallel
- Top 1-2 cross-cutting findings (one sentence each)
- Where the combined report lives
- Suggested next move (single `/kirei` follow-up vs. multiple)

---

## RULES

1. **Always parallel.** All Agent calls go in a single message. Sequential defeats the point.
2. **Cap at 4 lenses.** More agents in parallel → noisier merge, longer wait, higher cost.
3. **Never auto-execute.** This is a research-only skill. The merged findings hand off to a user-invoked `/kirei` or `/kirei [type]`.
4. **Surface conflicts, don't silence them.** If two lenses disagree, that's a real signal — name it in the merged doc.
5. **One lens = wrong tool.** If only one lens matches, recommend the user use `/kirei` instead.
6. **Workers run non-interactively.** Every worker prompt must tell the lens agent to SKIP its AskUserQuestion validate step — parallel workers each blocking on their own user prompt would deadlock the run. The orchestrator validates once, after the merge.
