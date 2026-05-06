---
name: kirei-templatize
description: Strip an existing JS/TS repo (Electron, Next.js, Vite, monorepo, etc.) down to a reusable starter template. Analyzes the codebase, splits the strip work into independent phases, and runs them via parallel sub-agents. Asks the user at invocation time about target directory, detection mode (user-marked paths / heuristic / keep-list), execution mode (parallel vs sequential), commit style (small conventional vs one-per-phase), co-author attribution, and whether to seed CLAUDE.md in the new template. Use whenever a user asks to "turn this repo into a template", "strip this for a starter", "make a boilerplate from this project", "templatize", "scaffold from existing repo", or "extract template". Invoke with /kirei-templatize followed by an optional task description.
---

You have been invoked via `/kirei-templatize`. Follow this workflow precisely.

---

## 0. SCOPE CHECK

This skill operates on **JS/TS repos** (Electron, Next.js, Nuxt, Vite, SvelteKit, Remix, Turborepo/pnpm/Nx monorepos, Node services). If the source repo's primary language is not JS/TS, stop and tell the user the skill is out of scope.

Confirm by reading `package.json` at the source root. If absent, ask the user where the JS/TS root lives before continuing.

---

## 1. GATHER USER PREFERENCES

Before any analysis, call `AskUserQuestion` with these questions in **one tool call** (multi-question form). Do not skip — these decisions shape every later step.

1. **Target location** — where the stripped template is written.
   - `New directory` (copy source repo to a sibling/specified path, strip there)
   - `New git branch` (create `template/<name>` branch in the source repo)
   - `In place` (destructive — only if source is already a disposable copy)

2. **Detection mode** — how to decide what to strip. **multiSelect: true** (combinable).
   - `User-marked paths` — user lists feature paths to strip
   - `Heuristic analysis` — sub-agent proposes a strip list for approval
   - `Keep-list` — user lists what to keep, strip the rest

3. **Execution mode**
   - `Parallel phases` — independent phases run as concurrent sub-agents (faster, more context)
   - `Sequential phase-by-phase` — one phase at a time, user can review between

4. **Commit style**
   - `Small conventional commits` — `feat:`, `chore:`, `refactor:` per logical change inside each phase
   - `One commit per phase` — single squashed commit per phase with phase name as subject
   - `One final commit` — no per-phase commits; squash everything at the end

After the first call, ask a second `AskUserQuestion` batch:

5. **Co-author attribution** — include `Co-Authored-By: Claude …` trailer in commits / PR bodies?
6. **Seed `CLAUDE.md`** — write a starter `CLAUDE.md` to the new template documenting the stack, commands, and conventions detected during analysis?
7. **Final PR** — open a PR for the template branch / new repo at the end (only offered if mode is `New git branch`)?

Save the answers as a `<prefs>` block you reuse verbatim throughout the rest of the workflow.

---

## 2. RESOLVE TARGET

Based on `prefs.target_location`:

| Choice | Action |
|---|---|
| New directory | Ask for the absolute target path. Copy source → target with `git`-aware copy (respect `.gitignore`, exclude `node_modules`, `dist`, `.next`, `out`, `build`, `.turbo`, `.cache`). Re-init git in target with `git init` + initial `chore: import from <source>` commit. |
| New git branch | `git checkout -b template/<slug>` in the source repo. Working tree is the source repo itself. |
| In place | Confirm with the user once more — this rewrites the source. Proceed only on explicit confirmation. |

All subsequent edits target this resolved working directory. Refer to it as `$TARGET`.

---

## 3. DEEP ANALYSIS (single agent, blocking)

Spawn **one** general-purpose research agent in the foreground. Brief it as a fresh colleague — give it `$TARGET`, `prefs.detection_mode`, and ask for a structured map:

- **Stack inventory**: framework(s), bundler, package manager, language version, lint/format/test tooling
- **Entry points**: `main`, `bin`, `electron/main`, `app/`, `pages/`, `src/main.ts`, etc.
- **Scaffolding (KEEP)**: build config, CI, lint config, type config, layout shell, auth scaffolding (if generic), routing primitives, env loading, error boundaries, providers, i18n setup
- **Feature code (STRIP candidates)**: domain pages/routes, business components, DB schemas/migrations, domain services, domain hooks, fixtures, seeds, domain-specific assets
- **Coupled glue**: imports/exports that bridge KEEP ↔ STRIP and need rewiring after strip
- **Dead-after-strip**: deps in `package.json` only used by STRIP candidates
- **Detected commands**: `dev`, `build`, `test`, `lint`, `typecheck` from `package.json` scripts

Output goes to `$TARGET/.kirei/templatize-analysis.md` (create the dir). The agent must produce a markdown table where each row is a path or symbol with one of: `KEEP`, `STRIP`, `STUB` (replace with placeholder), `RENAME`, or `INSPECT` (needs user decision).

After the agent returns, **show the user the table** and apply detection-mode rules:

- If `prefs.detection_mode` includes `User-marked paths`: ask the user to confirm/extend the STRIP list.
- If `prefs.detection_mode` includes `Keep-list`: ask the user to confirm/extend the KEEP list; flip everything else to STRIP unless explicitly INSPECT.
- If `prefs.detection_mode` is *only* `Heuristic analysis`: present the agent's proposal and ask one yes/no via `AskUserQuestion` to approve before proceeding.

Resolve every `INSPECT` row before phase planning. Do not silently default.

---

## 4. PHASE PLANNING

Group the resolved actions into **independent phases**. Phases must be parallelizable — no two phases may touch the same file.

Standard phase template (adapt to repo):

| Phase | Scope |
|---|---|
| `P1 strip-routes` | Remove domain pages/routes; keep one placeholder index/home |
| `P2 strip-components` | Remove domain components; keep design-system primitives |
| `P3 strip-services` | Remove domain services, API clients, hooks; keep generic transport/wrappers |
| `P4 strip-data` | Remove DB schemas, migrations, seeds, fixtures; keep ORM init / migration runner config |
| `P5 strip-assets` | Remove domain images, icons, copy; keep favicon + brand-neutral placeholders |
| `P6 deps-prune` | Remove deps that became unreferenced after P1–P5 |
| `P7 stub-entrypoints` | Insert minimal "Hello, template" entry pages/components so the app still boots |
| `P8 docs-and-config` | Update `README.md`, write `CLAUDE.md` (if `prefs.seed_claude_md`), prune `.env.example`, scrub repo metadata (name, description, author) |

Drop or merge phases that don't apply. Add phases for stack-specific concerns (e.g., Electron `main`/`preload` strip, Tauri commands, Next.js middleware).

For each phase, write a one-paragraph brief naming the **exact files** it owns. File ownership must be disjoint across phases. Save the plan to `$TARGET/.kirei/templatize-plan.md`.

---

## 5. EXECUTION

Branch on `prefs.execution_mode`:

### Parallel
Spawn one sub-agent per phase **in a single tool-call message** (multiple `Agent` blocks). Each agent receives:

- Its phase brief and exact file list
- `$TARGET` path
- `prefs.commit_style` instructions
- `prefs.co_author` flag (forwarded to its commit instructions)
- A hard rule: **touch only files in your file list**; if a referenced file outside the list seems wrong, report it back, do not edit it

### Sequential
Run the same agents one at a time, waiting for each to return before starting the next. Between phases, briefly summarize the diff to the user (do not block on input unless something failed).

### Commit handling per phase
- `Small conventional commits` → agent makes 2–6 conventional commits inside the phase, scoped to its files.
- `One commit per phase` → agent stages all phase changes and commits once with subject `chore(template): <phase-name>`.
- `One final commit` → agents do NOT commit; they only stage. After all phases finish, you (the orchestrator) commit once.

If `prefs.co_author` is true, every commit message ends with the trailer:

```
Co-Authored-By: Claude <noreply@anthropic.com>
```

Otherwise omit it entirely (no `Generated with` line either).

---

## 6. POST-EXECUTION VERIFICATION

After all phases complete, run in `$TARGET` (do **not** run `pnpm dev` / `npm run dev` — see user's global instruction; only run non-server tasks):

1. Package install: `pnpm install` / `npm install` / `yarn install` / `bun install` based on detected lockfile
2. `typecheck` script if present
3. `lint` script if present
4. `build` script if present (most important — proves template still compiles)
5. `test` script if present and fast (skip if it requires services)

Report each result. If anything fails, spawn a focused fix agent (kirei-build) with the failure log; do not paper over with try/catch or skipped checks.

---

## 7. SEED `CLAUDE.md` (if `prefs.seed_claude_md`)

Write `$TARGET/CLAUDE.md` containing **only** information derived from the analysis in Step 3:

- Detected stack and language versions
- Package manager and the install/dev/build/test/lint/typecheck commands
- Entry points and where to add new routes/components
- Conventions actually present in the kept code (not generic best-practices boilerplate)

Keep it under ~80 lines. No fluff.

---

## 8. FINAL DELIVERY

Print a short report to the user:

- Files removed (count + LOC)
- Deps removed (list)
- Phases run, their commit count
- Verification results
- Path to `$TARGET`
- If `prefs.open_pr` and target was a branch: open PR via `gh pr create` with body summarizing the template scope. Otherwise, the next-step hint is `cd $TARGET && <install-command>`.

Stop.

---

## INVARIANTS

- Never run `pnpm dev` / `npm run dev` / any dev server (user's global rule).
- Never delete the source repo's working directory; only operate on `$TARGET`.
- Never skip Step 1 — preferences drive everything downstream.
- Sub-agents must respect file ownership; cross-phase edits cause merge collisions in parallel mode.
- If `prefs.target_location` = `In place`, require an explicit second confirmation before any destructive action.
- Conventional commit prefixes used: `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `build:`, `ci:`, `test:`. Use `chore(template):` scope for strip operations.
