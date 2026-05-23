---
name: kirei
description: Orchestrate research + execution for any engineering task. Auto-detects task type (security, ui, refactor, perf, arch, test, migrate, review, debug, data, observability, bundle, license, error, eval, or general) and execute complexity (build vs forge), then spawns the right specialist research agent followed by the right execute agent. Use whenever the user asks to investigate, audit, fix, refactor, debug, optimize, review, or implement anything that benefits from research before code — even if they don't say "kirei". Pass --research-only to skip the execute step. Invoke with /kirei followed by a task description.
---

You have been invoked via `/kirei`. Follow this workflow precisely.

---

## 0. PARSE FLAGS

Strip these flags from the task description before classifying:

| Flag | Meaning |
|---|---|
| `--research-only` | Skip Step 6 (the execute agent). Deliver findings only. |
| `--pr <N>` | Used by `kirei-review` — review GitHub PR #N. Forces type=`review`. |
| `--address-pr-comments <N>` | Used by `kirei-review` — fetch PR comments and classify them. Forces type=`review`. |
| `--findings <path>` | Skip Step 4-5; an existing findings doc was provided. Go straight to Step 6 with this doc. |

Any flag the user passes must reach the spawned agent's prompt **verbatim** so the agent can act on it.

---

## 1. DETECT TASK TYPE

If `--pr` or `--address-pr-comments` is present, type is **`review`**.
If `--findings` is present, no research agent runs — skip to Step 6.

Otherwise, read the task description and pick the **most specific** match:

| Type | Trigger keywords |
|------|-----------------|
| `security` | auth, vulnerability, injection, XSS, CSRF, secret, permission, CVE, exploit, token, session, audit |
| `ui` | component, layout, design, styling, UX, accessibility, visual, responsive, a11y, animation, UI |
| `refactor` | cleanup, refactor, technical debt, extract, abstract, dead code, duplication, smell, restructure |
| `perf` | slow, performance, bundle, optimize, memory, N+1, latency, cache, speed, render |
| `arch` | architecture, structure, dependencies, coupling, module, system design, boundaries |
| `test` | test, tests, coverage, untested, flaky, edge cases, regression, fixture, mock |
| `migrate` | migrate, upgrade, bump, breaking change, deprecation, version, codemod |
| `review` | review, PR, pull request, code review, address comments, reviewer feedback |
| `debug` | bug, broken, fails, repro, reproduce, intermittent, root cause, stack trace, error message |
| `data` | schema, migration safety, query, index, ORM, foreign key, table design, integrity, N+1 |
| `observability` | logging, log level, structured logs, metrics, tracing, telemetry, OpenTelemetry, Sentry, Datadog, PII in logs, correlation id, log redaction |
| `bundle` | bundle size, ship size, code splitting, tree shake, lazy load, dynamic import, vendor chunk, gzipped, source-map-explorer, bundle analyzer |
| `license` | license, LICENSE file, MIT, Apache, GPL, AGPL, copyleft, license compatibility, NOTICE, attribution, OSS compliance |
| `error` | error handling, swallowed catch, swallowed error, generic Error, error boundary, error type, error taxonomy, unhandled rejection, retry, timeout, error contract |
| `eval` | eval, evals, evaluation harness, benchmark suite, golden dataset, baseline, regression detection, prompt eval, LLM eval, A/B test infra, snapshot regression |
| `general` | anything else |

Tie-breakers:
- A "performance bug" with a clear repro → `debug` (focus on root cause), not `perf` (which is broad bottleneck mapping).
- "Test coverage for X" → `test`, not `general`.
- "Migration is locking the table" → `data` (migration safety), not `migrate` (version upgrade).
- N+1 in DB queries / ORM → `data`. N+1 in API calls, render loops, or non-DB iteration → `perf`.
- "Audit our deps" / "what's safe to bump" / "check Dependabot" / "run npm/pnpm audit" → recommend `/kirei-deps` (purpose-built for dependency hygiene); only fall back to `security` if the user wants the full codebase audit.
- "Review my PR" with no `--pr` flag → ask which PR or assume current branch's PR.
- "Are errors logged?" / "PII in logs" / "missing metrics" → `observability`. "Why is this slow?" → `perf`. The distinction: `observability` is about *whether you can see what's happening*, `perf` is about *what's slow*.
- "Set up Sentry" / "add error tracking" / "wire crash reporting" / "add production monitoring" (greenfield *setup*) → recommend `/kirei-sentry` (purpose-built: framework-aware, consent-gated, CI source maps). `observability` is for *auditing existing* telemetry, not standing up Sentry from scratch.
- "Bundle is too big" / "shipped JS too large" / "code split this" → `bundle`. Use `perf` only if the question is broader than shipped bytes.
- "Audit our licenses" / "is GPL OK here?" / "missing NOTICE" → `license`. CVE-focused dep questions still go to `/kirei-deps`.
- "Errors are swallowed" / "no error types" / "catch blocks everywhere" / "no timeouts on fetch" → `error`. A specific failing flow with a repro → `debug` instead.
- "Are our evals any good?" / "no regression baseline" / "prompt change broke quality" / "we have benchmarks but no baseline" → `eval`. Test coverage of code paths → `test`.
- "Should we build X?" / "is this idea good?" / "talk me through this" → recommend `/kirei-discuss` instead — that skill is purpose-built for pre-commitment idea audit.

## 2. DETECT EXECUTE COMPLEXITY

Pick one — this determines which execute agent runs after research:

- **`build`** (sonnet) — single or few files, clear bug fix, small feature, obvious scope, straightforward implementation
- **`forge`** (opus) — multi-file changes, architectural decision, new feature, unclear scope, ordering matters

When in doubt between build and forge, pick forge.

Skip this step entirely if `--research-only` was passed, or the type is `arch` (advisory only).

## 3. ANNOUNCE PLAN

Tell the user in one line what you're spawning:

> "Running **kirei-{type}** to investigate → **kirei-{build|forge}** to implement."

Variants:
- `--research-only`: "Running **kirei-{type}** to investigate (research only — no implementation)."
- `arch`: "Running **kirei-arch** — produces a report and diagram, no code changes."
- `--findings <path>`: "Skipping research — using provided findings at `<path>` → **kirei-{build|forge}** to implement."

## 4. SPAWN THE RESEARCH AGENT

Skip if `--findings <path>` was passed.

Spawn the appropriate research agent using the Agent tool. The agent has **no session context** — include everything it needs in the prompt.

| Task type | Agent to spawn | Findings folder |
|-----------|---------------|-----------------|
| `general` | `kirei` | `docs/research/` |
| `security` | `kirei-security` | `docs/security/` |
| `ui` | `kirei-ui` | `docs/ui/` |
| `refactor` | `kirei-refactor` | `docs/refactor/` |
| `perf` | `kirei-perf` | `docs/perf/` |
| `arch` | `kirei-arch` | `docs/arch/` |
| `test` | `kirei-test` | `docs/test/` |
| `migrate` | `kirei-migrate` | `docs/migrate/` |
| `review` | `kirei-review` | `docs/review/` |
| `debug` | `kirei-debug` | `docs/debug/` |
| `data` | `kirei-data` | `docs/data/` |
| `observability` | `kirei-observability` | `docs/observability/` |
| `bundle` | `kirei-bundle` | `docs/bundle/` |
| `license` | `kirei-license` | `docs/license/` |
| `error` | `kirei-error` | `docs/error/` |
| `eval` | `kirei-eval` | `docs/eval/` |

**Prompt structure for the research agent:**
```
Task: [exact task description from the user — INCLUDING any --pr, --address-pr-comments, or other agent-relevant flags verbatim]

Working directory: [current working directory]

Context:
[Any relevant context from the conversation — file paths mentioned, symptoms observed, recent changes, constraints]

Deliver: structured KIREI HANDOFF block + write findings to its category folder in this repo
(e.g. docs/security/ for kirei-security, docs/perf/ for kirei-perf — see your agent prompt for the exact path).
```

Run the research agent in the **foreground** (not background) — you need its findings before spawning the execute agent.

## 5. REVIEW FINDINGS

When the research agent completes, read its KIREI HANDOFF block. Before proceeding:

- Verify the files it mentions actually exist (spot-check 1-2 paths).
- **Check that a findings file was written to the agent's category folder** — use Glob (e.g. `docs/security/*.md` for kirei-security, `docs/perf/*.md` for kirei-perf, `docs/observability/*.md` for kirei-observability, `docs/bundle/*.md` for kirei-bundle, `docs/license/*.md` for kirei-license, `docs/error/*.md` for kirei-error, `docs/eval/*.md` for kirei-eval — see the table above). If the agent failed to write it (look for `FINDINGS FILE NOT WRITTEN` in its summary, or if Glob returns nothing recent for today), write the file yourself from the agent's handoff content using the Write tool at `docs/<category>/YYYY-MM-DD-{topic}.md`.
- Confirm the complexity assessment (SIMPLE vs COMPLEX) matches your read of the task.
- Upgrade `build` → `forge` if the findings reveal more scope than expected.

**If the agent returned no handoff at all** (errored out, hit a tool failure, ran out of budget): tell the user what happened in one sentence, point to anything partial the agent did write, and offer to retry with narrower scope or escalate to `/kirei-chain` for a different angle. Do **not** fabricate a handoff or proceed silently to Step 6.

## 6. SPAWN THE EXECUTE AGENT

Skip this step if **any** of the following is true:
- `--research-only` was passed
- Task type is `arch` (advisory only — no implementation)
- The handoff explicitly says no implementation needed (e.g., a `kirei-review` finding that everything ships, or a `kirei-debug` diagnosis that the bug is in a third-party dep)

Spawn the appropriate execute agent:

| Complexity | Agent |
|-----------|-------|
| `build` | `kirei-build` |
| `forge` | `kirei-forge` |

**Prompt structure for the execute agent:**
```
Working directory: [current working directory]

Here is the KIREI HANDOFF from the research agent:
[paste full handoff block]

Findings doc is at: docs/<category>/[filename]
(category matches the research agent — e.g. security, perf, refactor, test, migrate, review, debug, data, arch, ui, or research for general)

Implement the recommended fix. Follow the verification steps in the handoff.
```

**Special-case prompts:**

- **For `kirei-debug` handoffs**, include this line: "The handoff lists instrumentation sites under 'Instrumentation to REMOVE'. Remove every one as part of the fix, then add the regression test from the report."

- **For `kirei-review --address-pr-comments` handoffs**, include this line: "Only address VALID comments listed in the handoff. Do NOT touch out-of-scope or invalid comments — those have suggested replies the user will post manually. Do not push or post to GitHub yourself."

- **For `kirei-migrate` handoffs**, include this line: "Apply the upgrade order strictly. One step per commit — do not bundle the whole migration into a single change."

## 7. REPORT TO USER

Once the execute agent completes (or after Step 5 if `--research-only`), summarize for the user:

- What was investigated and what was found (1-2 sentences)
- What was changed (files modified) — or "research only, no code changes" if applicable
- How to verify it works
- Point to `docs/<category>/[filename]` for the full findings (the path is in the handoff)

For `kirei-review --address-pr-comments`: also list the **suggested replies** for INVALID comments so the user can paste them back on the PR.

For `kirei-debug`: confirm the **regression test** was added and the **instrumentation** was removed.

---

## PARALLELIZING MULTIPLE ANGLES

If the task naturally splits into 2+ independent investigations (e.g., "audit security AND check performance AND map architecture"), recommend **`/kirei-chain`** instead — it's purpose-built for parallel multi-lens research and produces a merged report. Don't shoehorn multi-angle work through `/kirei`; the merge logic and conflict-surfacing live in `/kirei-chain` for a reason.

If the user explicitly insists on doing it from `/kirei`, you may spawn multiple research agents in parallel in a single message, then spawn execute agents once all complete (only if `--research-only` is not set). But surface the recommendation first.

## RESEARCH-ONLY MODE

Triggered by `--research-only`, OR by phrasings like "just audit", "give me a report", "analyze but don't change anything", "no code changes". Skip Step 6 entirely. Deliver the research findings and findings doc only.

## REUSING AN EXISTING FINDINGS DOC

If the user passes `--findings <path>` (or says "use the findings at X"), skip Steps 4-5. Pass the findings doc directly to the execute agent in Step 6:

```
Working directory: [current working directory]

Use the existing findings document at: <path>

Read it fully, then implement the recommended fix. Follow the verification steps.
```
