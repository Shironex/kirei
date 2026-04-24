---
name: kirei
description: Orchestrate research + execution for any engineering task. Auto-detects task type (security/ui/refactor/perf/arch/general) and complexity (build vs forge). Spawns the right kirei specialist research agent, then the right execute agent with findings. Invoke with /kirei followed by a task description.
---

You have been invoked via `/kirei`. Follow this workflow precisely.

---

## 1. DETECT TASK TYPE

Read the user's task description and pick the **most specific** match:

| Type | Trigger keywords |
|------|-----------------|
| `security` | auth, vulnerability, injection, XSS, CSRF, secret, permission, CVE, exploit, token, session, audit |
| `ui` | component, layout, design, styling, UX, accessibility, visual, responsive, a11y, animation, UI |
| `refactor` | cleanup, refactor, technical debt, extract, abstract, dead code, duplication, smell, restructure |
| `perf` | slow, performance, bundle, optimize, memory, N+1, latency, cache, speed, render |
| `arch` | architecture, structure, dependencies, coupling, module, system design, boundaries |
| `general` | anything else |

## 2. DETECT EXECUTE COMPLEXITY

Pick one — this determines which execute agent runs after research:

- **`build`** (sonnet) — single or few files, clear bug fix, small feature, obvious scope, straightforward implementation
- **`forge`** (opus) — multi-file changes, architectural decision, new feature, unclear scope, ordering matters

When in doubt between build and forge, pick forge.

## 3. ANNOUNCE PLAN

Tell the user in one line what you're spawning:

> "Running **kirei-{type}** to investigate → **kirei-{build|forge}** to implement."

If this is an architecture task (advisory only), note: "kirei-arch produces a report and diagram — no code changes."

## 4. SPAWN THE RESEARCH AGENT

Spawn the appropriate research agent using the Agent tool. The agent has **no session context** — include everything it needs in the prompt.

| Task type | Agent to spawn |
|-----------|---------------|
| `general` | `kirei` |
| `security` | `kirei-security` |
| `ui` | `kirei-ui` |
| `refactor` | `kirei-refactor` |
| `perf` | `kirei-perf` |
| `arch` | `kirei-arch` |

**Prompt structure for the research agent:**
```
Task: [exact task description from the user]

Working directory: [current working directory]

Context:
[Any relevant context from the conversation — file paths mentioned, symptoms observed, recent changes, constraints]

Deliver: structured KIREI HANDOFF block + write findings to docs/research/ in this repo.
```

Run the research agent in the **foreground** (not background) — you need its findings before spawning the execute agent.

## 5. REVIEW FINDINGS

When the research agent completes, read its KIREI HANDOFF block. Before proceeding:

- Verify the files it mentions actually exist (spot-check 1-2 paths)
- **Check that a findings file was written to `docs/research/`** — use Glob: `docs/research/*.md` to verify. If the agent failed to write it (look for `FINDINGS FILE NOT WRITTEN` in its summary, or if Glob returns nothing recent), write the file yourself from the agent's handoff content using the Write tool: `docs/research/YYYY-MM-DD-{topic}.md`
- Confirm the complexity assessment (SIMPLE vs COMPLEX) matches your read of the task
- Upgrade `build` → `forge` if the findings reveal more scope than expected

## 6. SPAWN THE EXECUTE AGENT

Skip this step if the task type is `arch` (advisory only — no implementation).

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

Findings doc is at: docs/research/[filename]

Implement the recommended fix. Follow the verification steps in the handoff.
```

## 7. REPORT TO USER

Once the execute agent completes, summarize for the user:

- What was investigated and what was found (1-2 sentences)
- What was changed (files modified)
- How to verify it works
- Point to `docs/research/[filename]` for the full findings

---

## PARALLELIZING MULTIPLE ANGLES

If the task naturally splits into independent investigations (e.g., "audit security AND check performance"), spawn multiple research agents in parallel in a single message, then spawn execute agents once both complete.

## RESEARCH-ONLY MODE

If the user asks to investigate without implementing ("just audit", "give me a report", "analyze but don't change anything"), skip Step 6. Deliver the research findings and findings doc only.
