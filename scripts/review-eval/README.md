# Reviewer recall harness

How often does `kirei-gate` catch a real bug? This harness answers that with a number, from real
fixes in a project's history, so a clean `VERDICT: MERGE` carries a known amount of confidence and
a reviewer change (a new prompt, a second reviewer, a model swap) can be shown to help or not.

Run it on demand. It spends one full reviewer session per case per variant, so it is not a CI job.

## How it works

1. **Corpus.** A JSON file of known-real fixes, each with a regression test
   (`corpus.example.json` shows the shape). Keep the real corpus in the repo whose history it
   replays: a private project's bug history stays in that project. Every case picks how the
   reviewer sees the bug:
   - `introducing`: the commit that wrote the defective lines, found by `harness.py analyze
     <fix>` (blame of the fix's non-test hunks at `<fix>^`). The intent is that commit's original
     message, so the reviewer sees exactly what a reviewer saw at the time.
   - `revert`: the reverse of the fix's non-test hunks, with a plausible builder intent. A pure
     revert is easier to review (it deletes the fix's own explanatory comments, and the synthetic
     base commit is visible in the log), so these cases **over-estimate** recall. Scores are reported per mode.
   - `patch`: a planted defect, a patch file applied on top of `base`. Keep plants in their own
     corpus file so they never enter the real-fix recall number.
2. **Isolation.** `prepare` builds one repo per case: `git init`, an alternates file pointing at
   the source repo's objects, and a single `review` branch at the diff's head. No ref points at the
   fix, so `git log --all` cannot reveal it, and the fix's regression test is never in the tree.
   Nothing is written to the source repo.
3. **Run.** `run` starts `claude -p --safe-mode` in each case repo with the agent's prompt as an
   appended system prompt, only `Bash,Read,Glob,Grep` available, the diff range and the intent.
   The prompt is snapshotted once per run into `results/<variant>/.system-prompt.md`.
4. **Score.** A finding is a hit when its path matches a ground-truth file and its line or range
   lies within `NEAR = 3` lines of a line the real fix changed (mapped back to the reviewed
   version). Two recall numbers are reported:
   - **any**: some grounded finding (any severity, or an uncertainty) hits.
   - **blocking**: a CRITICAL or HIGH finding hits **and** the verdict is HOLD. This is the
     number that matters for a merge gate.

   Off-target findings are counted per case. They are not all false positives, since a reviewer
   can find a different real bug, so read them before calling them noise.
5. **Audit.** The line rule is a proxy. A finding can sit near the fixed lines and describe
   something else, or name the bug while citing another line. Read each hit and each miss and
   record the verdict in `results/<variant>/audit.json` (`{"<case>": {"any": bool, "blocking":
   bool, "note": "..."}}`); `score` then prints the hand-audited recall next to the line-rule
   recall and lists every override.
6. **Compare.** `compare` runs a two-proportion z-test and, because both variants see the same
   cases, an exact McNemar test on the discordant pairs. On a small corpus only a large
   difference will be significant: with 4 discordant pairs all one way, exact McNemar p is 0.125.
   Say so rather than over-reading a small one.

## Usage

```bash
H="python3 scripts/review-eval/harness.py --repo /path/to/source-repo"
OUT=/tmp/review-eval

$H analyze <fix-sha>                                  # choose an introducing commit
$H prepare --corpus /path/to/source-repo/docs/review-eval/corpus.json --out $OUT
$H run --out $OUT --variant gate-opus --parallel 4
$H run --out $OUT --variant gate-sonnet --parallel 4
$H score --out $OUT
$H compare --out $OUT gate-opus gate-sonnet
python3 scripts/review-eval/test_harness.py           # scorer unit tests
```

To measure a prompt change, run the old prompt first, edit the agent, then run the same model
under the `gate-opus-v2` variant name. Each run snapshots the prompt it used into
`results/<variant>/.system-prompt.md`, so the two runs cannot mix prompts.

A run is resumable: a case with a non-empty result is skipped. A failed or timed-out case is
written as `<id>.md.<status>` and retried on the next run.

## Adding a case

Pick a fix with a clear root cause and a regression test. Run `analyze`. If one commit wrote most
of the touched lines and its diff is under about 120k characters, use `introducing` with that
commit. For an omission (the bug is a missing check, so blame names an older author of the
surrounding lines), name the commit that should have added the check and record why in `blame`.
Otherwise use `revert` and write an intent a builder would plausibly have written. Use `files` to
keep a guard the fix also added (a lint rule, a meta-check) out of the ground truth and out of the
revert.

## First measurement (2026-09-22)

Private corpus of 14 real fixes from one production monorepo (7 introducing-commit, 7 revert),
all hand-audited. Blocking means the real defect was named at HIGH or above and the verdict was
HOLD.

| variant | blocking, all | blocking, introducing-commit | any finding, all | HOLD | off-target per case |
|---|---|---|---|---|---|
| `kirei-gate` 2.0.0 prompt, Opus | 10/14 (71%, CI 45%-88%) | 3/7 | 11/14 | 11/14 | 2.7 |
| `kirei-gate` 2.0.0 prompt, Sonnet | 6/14 (43%, CI 21%-67%) | 0/7 | 7/14 | 8/14 | 0.9 |
| `kirei-gate` current prompt, Opus | 11/14 (79%, CI 52%-92%) | 4/7 | 12/14 | 14/14 | 3.4 |

- Revert cases sit at the ceiling for Opus (7/7 on both prompts), so the introducing-commit
  column is the one that tells reviewers apart.
- **Opus vs Sonnet:** Opus caught 4 defects Sonnet missed and Sonnet caught none Opus missed
  (exact McNemar p = 0.125, z-test p = 0.127). The direction is consistent but not significant
  at n = 14. On introducing-commit diffs Sonnet caught nothing at blocking level. Keep the gate
  on Opus, and do not treat a Sonnet review (such as `kirei-review`) as a merge gate.
- **2.0.0 prompt vs current prompt:** one discordant pair, in favour of the current prompt: the
  "broken safety claim is HIGH" rule turned a defect the old prompt had rated LOW into a HOLD
  (exact McNemar p = 1.0). The added gate-surface scan cost no recall.
- The four 2.0.0 misses were two omissions (a missing entry in a redaction list, a missing
  handshake guard the reviewer believed the framework already enforced), one race in a
  102k-character diff, and one defect named correctly but rated LOW.
- **No clean controls yet.** Every case contains a real defect, so HOLD is the right verdict for
  all 14 and the corpus cannot measure false HOLDs. Add known-clean merged diffs before reading
  the HOLD column as precision.

See `PANEL-DESIGN.md` for what this implies for a second reviewer.
