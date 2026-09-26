---
name: kirei-showcase
description: Give any project a showcase-grade README with a hero banner and real, reproducible screenshots, built on @noctcore/showcase-kit. Detects how the app can be captured (web app, live site, Electron over CDP, Tauri or backend-heavy UIs through a dev-only fixture mode, terminal apps in a pseudo terminal), asks the capture target, demo data, README scope and look, runs the kirei-showcase agent to plan the capture and verify every README claim, then kirei-loom to install the kit, write the config (and fixture mode if needed), capture, check the images and rewrite the README. Use whenever a user wants a better README, screenshots or a hero image for a repo, a README "like Shiranami's" or "like the portfolio's", README images regenerated, or showcase-kit adopted in a project, even if they don't say "kirei". Invoke with /kirei-showcase; the skill asks the key decisions before working.
---

You have been invoked via `/kirei-showcase`. Follow this workflow precisely.

You orchestrate the `kirei-showcase` research agent (which triages the project and plans a deterministic capture plus
a verified README) and then `kirei-loom` (which builds it). The capture know-how lives in the agent; this skill
gathers the decisions only the user can make, drives the flow, and reviews the result with its own eyes before
reporting.

You do **not** write the config, fixtures or README yourself, and you never push or open a PR.

---

## 0. PARSE FLAGS

Strip these before proceeding:

| Flag | Meaning |
|---|---|
| `--research-only` | Skip Step 6. Deliver the plan in `docs/showcase/` only. |
| `--mode <m>` | Skip the target question. Valid: `url`, `live`, `cdp`, `tty`. |
| `--readme-only` | Keep the existing config and images; rewrite the README around them. |
| `--images-only` | Set up the kit and regenerate images; leave the README text alone (only the image table is updated). |
| `--langs <codes>` | Languages to capture, comma separated. |
| `--portfolio <dir>` | Also export portfolio images (`outputs.portfolio.dir`). |
| `--no-hero` | Skip the hero banner. |

Any flag the user passes must reach the spawned agents' prompts **verbatim**.

---

## 1. QUICK DETECT (cheap, before asking)

Enough to tailor the questions, not a triage (the agent does that):

```bash
ls; cat package.json 2>/dev/null | head -60; ls showcase* assets/showcase 2>/dev/null
```

Note: project kind (web app / static site / Electron / Tauri / CLI or TUI / library), package manager, whether the
kit is already installed (which version), whether a mock or fixture mode exists (grep `mock`, `fixture`,
`showcase=`, `MockStore`, `msw`), i18n locales, and whether the UI shows personal data.

---

## 2. ASK THE DECISIONS

Skip any question a flag answers. Use **AskUserQuestion** in one call (up to four questions), putting the option the
detection supports first with "(Recommended)":

- **Capture target**: "How should the kit reach the app?"
  - *Local build started by the kit*: deterministic and matches the branch; needs the app to build without real
    secrets (mock env is fine).
  - *Local dev server*: fastest to set up; HMR overlays may need hiding.
  - *Live URL*: for deployed sites and docs; images follow what is deployed.
  - *Terminal (tty)*: CLI/TUI apps in a pseudo terminal; can also record clips. (Or *Electron over CDP* when the
    renderer cannot run alone.)
- **Demo data**: "What data should the screenshots show?"
  - *Existing mock/fixture mode*: when detection found one.
  - *Build a showcase fixture mode*: a dev-only flag (`?showcase=1`) serving invented, license-safe data at the
    transport seam. Recommend it for desktop apps, backend-heavy UIs and anything showing personal data.
  - *Real app as-is*: only when everything on screen is public and stable.
- **README scope**: "How much of the README should change?"
  - *Full rewrite in the showcase layout (Recommended for stale READMEs)*: hero, tagline, screenshots, verified
    feature table, current stack, getting started.
  - *Keep the text, add hero and screenshots*: for READMEs with valuable reference content.
  - *Images only*: regenerate images, touch nothing else.
- **Look**: "Which look for the frames and hero?"
  - *Dark, accent gradient (Recommended)*: background from the app's accent color.
  - *Light, accent gradient*
  - *Match the app's default theme*

Ask a second round only when it matters: languages (i18n found), portfolio export (the user keeps a portfolio
repo), terminal clips (tty). If the user says "sensible defaults": local build (else dev server) · existing mock
mode (else fixture mode for personal-data apps, else as-is) · full rewrite · dark accent gradient · first language
only · no portfolio export. Say so.

---

## 3. ANNOUNCE PLAN

One line:

> "Running **kirei-showcase** to plan a [mode] capture ([demo data] · README [scope] · [look]) → **kirei-loom** to build it. Plan to `docs/showcase/`."

Variants: `--research-only` → "… (plan only, no changes)."

---

## 4. SPAWN THE RESEARCH AGENT

Spawn `kirei-showcase` with the Agent tool. It has **no session context**, so include everything, and paste the
README layout from `readme-layout.md` in this skill's directory (`${CLAUDE_PLUGIN_ROOT}/skills/kirei-showcase/` for a plugin install, `~/.claude/skills/kirei-showcase/` for a manual one).

```
Task: Plan a showcase README and screenshot set for this project with @noctcore/showcase-kit. [Extra detail the user gave.]

Working directory: [cwd]

Decisions:
- Capture target: [...]
- Demo data: [...]
- README scope: [...]
- Look: [...]
- Languages: [...] · Portfolio export: [dir | none] · Hero: [yes | no] · Clips: [yes | no]

Flags: [verbatim]

Context:
[Quick-detect notes, the user's writing rules if known (voice, banned punctuation, claims to avoid), a reference README
the user wants matched, anything personal that must never appear on screen.]

README layout to follow:
[paste readme-layout.md]

Read the kit README for the version in use before writing the config: unknown keys fail validation.

Deliver: KIREI-SHOWCASE HANDOFF block + findings in docs/showcase/.
```

Run in the **foreground**.

---

## 5. REVIEW THE PLAN

- Confirm `docs/showcase/*.md` exists for today; if the handoff says `FINDINGS FILE NOT WRITTEN`, write it from the
  handoff with the Write tool.
- Spot-check 2 selectors or nav targets from the shot list against the code.
- Check the decisions were honored (fixture mode when chosen, no live data where it was frozen, README scope).
- Surface anything under **Needs the user** now (license copyright leftovers, personal data risks) with
  AskUserQuestion if it changes what gets built; otherwise carry it to the report.
- Complexity: fixture mode, several languages or tty ⇒ **kirei-loom**; config + README only ⇒ kirei-stitch.

If the agent returned no handoff, say so in one sentence, point at anything partial, offer a narrower retry. Never
fabricate a plan.

---

## 6. SPAWN THE EXECUTE AGENT

Skip if `--research-only`.

```
Working directory: [cwd]

Here is the KIREI-SHOWCASE HANDOFF:
[paste it]

Plan: docs/showcase/[file]

Build it in the plan's order. Rules:
- Branch first (never the default branch). Small scoped conventional commits. No AI attribution lines anywhere.
- Install with the project's package manager, exact version. Respect release-age gates (first-party scope exclusion only).
- Fixture mode (if any) is dev-only, explicitly enabled, invented and license-safe, frozen, swapped at the transport seam.
- Never put real secrets in the config, target.env or a committed file; use CI's mock values.
- Run the capture. Look at EVERY generated image with the Read tool: no secrets, no personal data, no half-loaded
  views, no hover highlights, nothing cropped. Rerun once and compare hashes; fix what differs.
- Add showcase-out/ to .gitignore; commit the framed images, hero and config.
- README: follow the outline; every feature row must be true in the code. Commands must work on Windows and macOS.
- Fixes found on the way (a broken .env.example, a stale CLAUDE.md fact) go in their own commits; legal text
  (license copyright) only if the user approved it.
- Gate: lint, typecheck, format check, build. Paste real output. Do NOT push or open a PR.
```

Run in the foreground.

---

## 7. CHECK THE RESULT YOURSELF

Before reporting:

- Read the new README top to bottom. Check it against the user's writing rules and that every image path resolves.
- Look at the hero and at least two screenshots with the Read tool.
- `git log <default>..HEAD --format=%B | grep -icE "co-authored|generated with"` → 0.
- The regenerate command is in the README and in `package.json`.

Fix small misses by sending kirei-loom back with the list; do not paper over them in the report.

---

## 8. REPORT TO USER

- Decisions and what was built (1-2 sentences): mode, shots, fixture mode yes/no, README scope.
- Branch and commits; gate results.
- The one command that regenerates everything.
- **Needs you**: legal lines, claims the agent could not verify, wording the agent chose (tagline), anything to push
  or merge.
- Pointer to `docs/showcase/[file]`.

---

## RULES

1. **Ask the decisions unless flagged.** Demo data especially: what appears on screen is the user's call.
2. **Nothing private on screen.** Secrets, personal data, other people's content: fixture them or drop the view.
3. **Verified claims only.** A README that says what the code does not do is worse than the old one.
4. **Deterministic or not done.** Same OS, same command, same bytes.
5. **Look at the images.** A passing run with a spinner in every shot is a failure.
6. **Never push or open PRs.** kirei-loom commits on a branch; the user merges and pushes.
