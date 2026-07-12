---
name: kirei-deps
description: Audit a project's dependencies for safety. Detects the package manager (pnpm/npm/yarn/bun/poetry/uv/cargo/go/bundler), runs its audit, fetches GitHub Dependabot alerts when available, and produces a depth-tunable report — quick CVE counts, safe-bump list, or full ordered upgrade plan with risky-major handoff to /kirei migrate. Use whenever a user asks to audit deps, check for CVEs, find safe upgrades, review Dependabot alerts, run npm/pnpm/yarn/bun audit, check for outdated packages, or plan a dependency hygiene pass — even if they don't say "kirei". Invoke with /kirei-deps; the skill will ask which depth before working.
---

You have been invoked via `/kirei-deps`. Follow this workflow precisely.

You orchestrate a single research agent (`kirei-deps`) that audits the dependency tree at one of three **depth levels**. The user picks the depth at invocation time via AskUserQuestion. Once findings are in hand, you optionally hand off safe bumps to `kirei-stitch`, and recommend `/kirei migrate` for any risky majors.

You do **not** modify dependencies yourself. The agent reports; the user decides what runs next.

---

## 0. PARSE FLAGS

Strip these flags from the task description before proceeding:

| Flag | Meaning |
|---|---|
| `--quick` / `--standard` / `--deep` | Skip the depth question — use this depth directly. |
| `--research-only` | Skip Step 5 (the execute agent). Deliver findings only. |
| `--no-dependabot` | Force the agent to skip Dependabot fetching even at standard/deep depth (e.g., private repo with no alert access). |
| `--manager <pm>` | Override package manager detection. Useful for monorepos where the lockfile heuristic picks the wrong one. Valid: `pnpm`, `npm`, `yarn`, `bun`, `poetry`, `uv`, `pip`, `cargo`, `go`, `bundler`. |
| `--scope <path>` | Run audit only in a sub-directory (e.g., `--scope packages/web`). Defaults to current directory. |

Any flag the user passes must reach the spawned agent's prompt **verbatim** so the agent can act on it.

---

## 1. ASK FOR DEPTH

If the user already passed `--quick`, `--standard`, or `--deep`, skip this step and use that depth.

Otherwise, use AskUserQuestion to pick the depth. The depth determines work scope and runtime — explain the tradeoff so the user picks intentionally:

```
Question: "How deep should the dependency audit go? Each level adds work; pick the one that matches what you actually want to act on."
Header: "Depth"
multiSelect: false

Options:
- "Quick — audit only (~1 min)"
  description: "Run the package manager's audit. Report CVEs by severity. Stop. Use when you just want a snapshot of current security posture."

- "Standard — audit + Dependabot + safe bumps (Recommended, ~3 min)"
  description: "Quick + GitHub Dependabot alerts (if gh is authed) + a list of patches/minors that are safe to bump now (resolve CVEs or close drift, won't break). Use when you want a CVE report AND a concrete list of fixes to apply."

- "Deep — full upgrade plan (~8 min)"
  description: "Standard + outdated check + transitive dependency map + ordered upgrade plan with phases. Risky majors flagged for /kirei migrate. Use when planning a real dependency hygiene sprint."
```

Map the answer:
- "Quick" → `quick`
- "Standard" → `standard`
- "Deep" → `deep`

---

## 2. ANNOUNCE PLAN

One line:

> "Running **kirei-deps** at **<depth>** depth → will write findings to `docs/deps/`."

Variants:
- `--research-only`: append " (research only — no implementation)."
- `--scope <path>`: append " — scoped to `<path>`."
- Skipping Dependabot: append " (Dependabot disabled by --no-dependabot)."

---

## 3. SPAWN THE RESEARCH AGENT

Spawn the `kirei-deps` agent using the Agent tool. The agent has **no session context** — include everything it needs in the prompt.

**Prompt structure for the research agent:**

```
Task: Audit project dependencies for safety. [Plus any extra task description the user provided beyond /kirei-deps itself.]

Working directory: [current working directory]

Depth: <quick | standard | deep>

Flags: [--no-dependabot if set] [--manager <pm> if set] [--scope <path> if set]

Context:
[Any relevant context from the conversation — recent CVE concerns, specific packages the user mentioned, monorepo structure, etc.]

Deliver: structured KIREI-DEPS HANDOFF block + write findings to docs/deps/ in this repo.
```

Run the agent in the **foreground** — you need its findings before deciding on execute steps.

---

## 4. REVIEW FINDINGS

When the agent completes, read its KIREI-DEPS HANDOFF block. Before proceeding:

- Verify the findings file exists. Use Glob on `docs/deps/*.md` filtered by today's date. If the agent failed to write it (look for `FINDINGS FILE NOT WRITTEN` in its summary, or empty Glob), write the file yourself from the agent's handoff content using the Write tool at `docs/deps/YYYY-MM-DD-<scope>.md`.
- Spot-check 1-2 package names from the handoff against the lockfile to confirm they really exist there.
- Sanity-check the depth — if the user asked for `quick` but the handoff includes a full upgrade plan, something went off the rails; surface that to the user before continuing.

---

## 5. SPAWN THE EXECUTE AGENT *(safe bumps only)*

Skip this step if **any** of the following is true:
- `--research-only` was passed.
- The user asked for `quick` depth (no safe-bump list was produced).
- The handoff says zero safe bumps were found.
- The handoff lists ONLY risky majors (those go to `/kirei migrate`, not `kirei-stitch`).

Otherwise, spawn `kirei-stitch` to apply Phase 1 safe bumps as a single PR:

**Prompt structure:**

```
Working directory: [current working directory]

Here is the KIREI-DEPS HANDOFF:
[paste full handoff block]

Findings doc: docs/deps/[filename]

Apply ONLY the Phase 1 safe bumps listed in the handoff (patches + minors that resolve CVEs or close drift).

Steps:
1. Bump each package in the safe-bump list to its target version using the project's package manager.
2. Update the lockfile.
3. Run typecheck + build + tests — they must stay green.
4. Re-run `<pm> audit` and verify the expected CVEs cleared.
5. Stop. Do NOT touch any package listed under "Risky Bumps" or "Phase 3" — those need a separate /kirei migrate run per package.

If any safe bump breaks the build or tests, revert it, note it in the commit message as "<pkg> demoted from safe-bumps — needs migration", and continue with the rest.
```

Run in the foreground. When it completes, move to Step 6.

---

## 6. RECOMMEND MIGRATIONS *(if risky bumps were found)*

If the handoff lists risky majors under "Phase 3", **do not** auto-spawn anything for them. Instead, in your final report to the user, list the recommended commands one per package, in the order the agent prescribed:

> Risky bumps that need their own migration plan:
> - `/kirei migrate <pkg-a>` — [one-line reason]
> - `/kirei migrate <pkg-b>` — [one-line reason]

Each becomes its own investigation. Bundling them is exactly the kind of silent failure `kirei-migrate` exists to prevent.

---

## 7. REPORT TO USER

One short paragraph:

- What depth ran, what was found in one sentence (e.g., "Standard audit on the pnpm workspace: 3 critical, 7 high CVEs, 12 packages safe to bump").
- What was changed, if anything (Phase 1 results from kirei-stitch) — or "research only, no code changes" if applicable.
- Recommended next moves: any `/kirei migrate <pkg>` runs to queue up.
- Pointer to `docs/deps/[filename]` for the full report.

---

## RULES

1. **Always ask depth unless flagged.** Quick, Standard, Deep are not interchangeable — running Deep when the user wanted Quick wastes minutes; running Quick when they wanted Deep produces a useless snapshot.
2. **Never bundle risky majors into kirei-stitch.** Each major is its own migration with its own handoff. Step 6 enforces this.
3. **Never push commits or open PRs from this skill.** kirei-stitch commits locally; the user pushes.
4. **Tolerate Dependabot unavailability.** If `gh` isn't authed or the repo is private without alert access, the agent reports that gap and continues — it doesn't error out.
5. **Phase 1 is the whole point of standard depth.** If you skip Step 5 because the user said `--research-only`, make sure the recommended next command is clear in your report.
