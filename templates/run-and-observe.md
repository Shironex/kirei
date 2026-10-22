# Run and observe: visual evidence for visible changes

A green gate battery says nothing about how a frame, a screen or a model looks. When a diff
changes anything a user can see, the builder runs the repo's own capture, looks at every
picture, and ends its report with one `Run result:` line. `kirei-stitch`, `kirei-loom` and
`/kirei-wave` builders carry the short form of these rules; this file is the full reference
and a drop-in block for hand-written lane briefs.

---

## When it applies

A diff is **visual** when it touches any of:

- rendering: shaders (`*.glsl`, `*.vert`, `*.frag`, `*.hlsl`, `*.wgsl`, `*.metal`, `*.shader`),
  render, renderer, graphics, material, lighting, camera, post or effects code
- UI: components and styles (`*.tsx`, `*.jsx`, `*.vue`, `*.svelte`, `*.css`, `*.scss`), HUD,
  menu, overlay, layout, font or theme code
- input: keyboard, mouse, gamepad or touch handling, cursor and focus code
- assets: models (`*.glb`, `*.gltf`, `*.obj`, `*.fbx`), textures and images, fonts, animation
  clips, scene or level data
- goldens and screenshot baselines (`tests/data/goldens/**`, `**/__screenshots__/**`,
  `**/*-snapshots/**`)

A diff that touches none of these reports `Run result: N/A <reason>`.

## Find the capture command

Do not build capture tooling. Use what the repo already has, in this order:

1. `python "${CLAUDE_PLUGIN_ROOT}/scripts/gate-commands.py"` and its `capture`, `smoke` and
   `goldens` roles (it reads the repo's `gate-commands` section in `AGENTS.md`, Make targets,
   CMake presets and package.json scripts).
2. A screenshot or showcase script named in the README, `AGENTS.md` or `docs/` (a
   `--shot <file>` flag, a showcase-kit config, a Playwright screenshot test).
3. None found: report `Run result: NOT VERIFIED no capture command in this repo`, and say which
   command the repo should add.

Never run a command that rewrites goldens or baselines (`goldens-accept` in the
gate-commands output, `--accept-goldens`, `--update-snapshots`, `-u`) unless the brief names
the re-accept. A re-accept is a gate relaxation: list every rewritten golden, and Read the old
image (`git show <base>:<path> > <temp dir>/<name>`) next to the new one before claiming it.

## Run it under the input lock

Anything that opens a window, moves the cursor or needs the foreground goes through the shared
lock, so parallel builders never fight over the one real cursor and foreground window:

```bash
python -I "${CLAUDE_PLUGIN_ROOT}/scripts/input-lock.py" --role "<lane or slice id>" -- <capture command>
```

- Every gate role that opens the app's window goes through the lock, not only the capture:
  `smoke`, `goldens` and `feel` runs too.
- The command runs without a shell. Wrap a compound command in one, or only its first part runs
  under the lock: `-- sh -c "make debug && make smoke"`.
- The lock is a directory in the system temp folder with `owner.txt` (role, PID, time). The
  wrapper holds it for exactly one command and releases it when the command ends, even on
  failure. A lock is stale after 10 minutes or when its PID is dead.
- Keep each pass short: one scripted run, not an exploration session. The user may be at the
  machine, so say when an on-screen pass is about to run.
- Target your own window by PID. Never kill a process by image name, which kills other lanes'
  windows too.
- A second build for checking committed work gets its own worktree and build folder, so it
  never locks an executable another lane is linking.
- Checks from a run that overlapped another on-screen run (no lock, or a lock taken over as
  stale while it was live) are redone.

Headless captures (a `--shot` flag that renders offscreen, a headless browser) still take the
lock when they create a window at all.

## Look at every picture

`Read` each PNG the run wrote. For each one, say what is in it in one line: what is on screen,
and whether the change is visible and correct. Compare against the brief's expected look, the
golden, or the previous capture (`git show <base>:<path>`). A picture you did not Read is not
evidence. Leave the images where the command wrote them, or copy them into the repo's review
folder if it has one; do not commit them unless the repo commits captures.

## The report line

End the report with exactly one of:

```text
Run result: OBSERVED <what was seen> (<image path>, <image path>)
Run result: NOT VERIFIED <reason>
Run result: N/A <reason>
```

- `OBSERVED` only when every picture was Read and shows the change working.
- `NOT VERIFIED` always carries a reason: no capture command, the build cannot open a window
  here, the capture failed (paste the error), the input lock stayed busy, or the check needs
  the other operating system. A macOS-only or Windows-only check becomes a short checklist for
  the user, never a claim.
- `N/A` only for a diff that is not visual, with the reason.

A builder that opens a PR copies the `Run result:` line into the PR body. `kirei-gate` holds a
visual diff with no `OBSERVED` line, or with a `NOT VERIFIED` that names no reason.

## Drop-in block for a lane brief

```text
OBSERVE (when the diff is visual: rendering, UI, shaders, input, assets, goldens)
- Find the capture: gate-commands.py roles capture/smoke/goldens, else the README's screenshot
  command. Never run a goldens-accept command unless this brief names the re-accept.
- Run it under the input lock:
  python -I "${CLAUDE_PLUGIN_ROOT}/scripts/input-lock.py" --role <lane> -- <capture command>
  One short pass, own window by PID, never kill by image name.
- Read every picture it wrote and say what each one shows.
- Last line of the report, and in the PR body:
  Run result: OBSERVED <what was seen> (<paths>) | NOT VERIFIED <reason> | N/A <reason>
```
