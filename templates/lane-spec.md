# Lane spec blocks: stop rules, failure classes, gate surfaces, gate commands

Drop-in blocks for a coordinator's lane brief (an Orca `GOAL / DO THIS / VERIFY / REPORT` spec, a
`/kirei-wave` builder brief, or any hand-written worker prompt). `kirei-stitch`, `kirei-loom` and
`/kirei-wave` builders already carry the same rules; paste these into briefs for workers that do
not run a kirei agent. For visible changes, add the OBSERVE block from
`templates/run-and-observe.md`.

---

## VERIFY block

```text
VERIFY
Run the lane's full battery and paste REAL output, not a summary line. Find the battery with
python "${CLAUDE_PLUGIN_ROOT}/scripts/gate-commands.py" (AGENTS.md gate-commands, Make, CMake,
package.json, Cargo): fast roles on every fix cycle, slow roles once before the PR, and never a
goldens-accept command unless the brief names the re-accept.

Stop rules. A fix cycle is one edit plus one rerun of the failing check. Track each failure by
its signature: file + rule for type and lint errors, the test name for a test, the step name for
a build or bootstrap failure.
- If the same signature still fails after 5 consecutive fix cycles, STOP and report it as the
  named blocker ("stuck on <rule> in <file> after 5 cycles").
- If the whole failing set is unchanged for 6 consecutive gate runs, STOP with
  failure_class no-progress.
- After 2 failed cycles on one unit, rewrite the unit from its contract; do not micro-patch.
- Never pass a check by weakening it: no lowered threshold, demoted or disabled rule, new
  ignore/skip/retry/inline disable, or strict flag turned off.
- Before calling a failure pre-existing, rerun the same check on the base commit in a throwaway
  worktree and paste that output. Without it, the failure is yours.
- A turn or time cap is a crash guard, not a stop rule. Stopping early with a named blocker is a
  successful report.
```

## REPORT block

```text
REPORT
Every report carries these three lines, even on success:

failure_class: none | <one or more from the fixed list>
blocker: none | <signature + cycles, e.g. "stuck on no-explicit-any in src/views/Foo/index.tsx after 5 cycles">
gate_surfaces: none | <path: before -> after, why>   (one per touched gate-surface file)
Run result: OBSERVED <what was seen> (<paths>) | NOT VERIFIED <reason> | N/A <reason>

A bootstrap failure also names the AGENTS.md / CLAUDE.md entry that should have covered it, or
says none exists. A red-on-base claim pastes the base rerun output.
```

## failure_class vocabulary

A fixed list, so a wave summary can tally failures and each class points at an intervention.
Use `none` when every gate is green. Do not invent new classes in a report; propose them to the
coordinator instead.

| failure_class | Means | Intervention |
|---|---|---|
| `type-error` | typecheck red | the change, or a wrong type assumption in the brief |
| `lint-rule` | an ESLint (or equivalent) rule red | the change, or a rule the brief did not mention |
| `lint-meta` | a repo meta-check red (config, docs or structure checks) | the invariant the change crossed |
| `test-failure` | a test red | the change, or a stale test |
| `build-fail` | build or bundle step red | build config, a missing export |
| `hallucinated-import` | an import of a module, export or package that does not exist | give the worker the real module map; grep before importing |
| `bootstrap` | the worktree could not run the gate: missing `.env`, missing generated client, stale workspace build, a bare `--filter` run | an `AGENTS.md` setup entry; two of these on the same step means the entry is missing |
| `infra` | DB or port collision, Docker, model overload (529), machine sleep, network | the environment; retry after it clears, do not blame the lane |
| `timeout` | a check or the run hit a time cap | the slow or hung step, named |
| `red-on-base` | the same check fails on the base commit | the base; only valid with the base rerun output |
| `no-progress` | the failing set was unchanged for 6 gate runs | the task framing; needs a human or a different approach |
| `scope` | finishing needs files or decisions outside the brief | the brief |

## Wave summary tally

The coordinator's wave summary counts `failure_class` across every lane report:

```text
failure_class tally: none 5 · bootstrap 2 (missing Prisma client x2) · red-on-base 1 · no-progress 0
```

## gate-surfaces list (for the target repo's AGENTS.md)

`kirei-gate`, `kirei-review` and `/kirei-wave` read a `gate-surfaces` section from the target
repo's `AGENTS.md` (or `CLAUDE.md`) on top of their built-in defaults. A repo publishes its list
once, as paths or globs:

```markdown
## gate-surfaces

- `eslint.config.mjs`, `apps/*/eslint.config.*`, `packages/eslint-config/**`
- `tools/lint-meta/**` (including the required-rules list)
- `apps/api/package.json` (coverage floor), `apps/web/package.json` (coverage floor, bundle limit)
- `packages/tsconfig/**`, `**/tsconfig*.json`
- `apps/web/playwright.config.ts` (retries), jest and vitest configs
- `scripts/ci/**`, `.husky/**`, `.github/workflows/**`
- `**/knip.json`, `.gitleaks.toml`, `commitlint.config.cjs`
```

## gate-commands list (for the target repo's AGENTS.md)

`scripts/gate-commands.py` finds most gates on its own (Make targets, CMake presets and CTest,
package.json scripts, Cargo). A repo whose real gate is not obvious from those files publishes
it once in `AGENTS.md`, next to `gate-surfaces`. A role listed here replaces everything
discovered for that role. Roles: `typecheck`, `lint`, `build`, `test`, `check`, `smoke`,
`capture`, `goldens`, `feel`, `perf`, `assets`. Mark each `(fast)` (every fix cycle) or
`(slow)` (once per slice before the PR); without a mark, `typecheck`, `lint`, `build` and
`test` are fast and the rest slow.

```markdown
## gate-commands

- build: `make debug` (fast)
- test: `make test` (fast), `make test-release` (fast)
- lint: `make format-check` (fast)
- smoke: `make smoke` (slow)
- capture: `make shots` (slow)
- feel: `make feel` (slow)
- assets: `python -I <kirei>/scripts/asset-check.py assets/models --scan-code src` (slow)
```

`<kirei>` is wherever kirei's `scripts/` folder lives; agents running as the plugin use
`${CLAUDE_PLUGIN_ROOT}`. A goldens target that accepts new images (a `make
goldens` that rewrites `tests/data/goldens/`) does not belong under `goldens`: the comparison
runs inside `smoke` or a test, and the accept command is never a gate.

The `assets` role is the asset contract check: `scripts/asset-check.py` reads every glTF/GLB
model given and fails when a node name the code looks up (string literals and UPPER_CASE
constants passed to `findNode`, `getObjectByName` or a `--lookup` of your own), a `--expect`
list or a `--manifest` JSON asks for is missing from the models. Call sites it cannot resolve
(a parameter, a name built at runtime) are listed for a human look and do not fail the run.
