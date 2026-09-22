# kirei-gate `--panel`: a second, non-Claude reviewer (designed, not built)

Status: **designed, not built.** It is blocked on three decisions listed at the end. This design
is based on the first recall measurement (see `README.md`), which is what makes the question
decidable.

## What the measurement says

`kirei-gate` on Opus, over 14 real fixes from a private production monorepo (hand-audited, blocking = the defect named at
HIGH or above, with HOLD):

| | caught (any) | caught (blocking) |
|---|---|---|
| introducing-commit cases (what a reviewer really saw) | 4/7 | 3/7 |
| revert cases (easier, over-estimate) | 7/7 | 7/7 |
| all | 11/14 | 10/14 (71%, Wilson 95% CI 45%-88%) |

The same prompt on Sonnet caught 6/14 at blocking level and 0/7 introducing-commit cases, so a
cheaper model is not a substitute reviewer; it is a weaker one.

The four Opus misses:

| miss | what the reviewer did |
|---|---|
| a redaction list missing one credential route | Reviewed the list and found two other real gaps, but never noticed the missing route. MERGE. |
| a websocket handshake with no origin check | Said outright that the origin allowlist was enforced, because the CORS option reaches the socket server. That is the wrong belief the real fix corrects: CORS middleware never rejects a request. MERGE. |
| a read-then-upsert race in a policy toggle | A 102k-character diff. Found ten other issues, one of them a different real race, but not this one. MERGE. |
| a cross-tenant address disclosure in an invite flow | Named the defect (a "never reveals" claim in the code is false) but rated it LOW. |

Two of the four are **omissions** (a missing prefix, a missing handshake guard), and one of those
two rests on a **wrong belief about framework semantics**. One is **size** and one is
**severity calibration**. A second model from a different family is a plausible fix for the
omission and framework-belief misses. It is not an obvious fix for calibration, which a
deterministic rule handles better (see "block rules").

**The historical miss that motivated this is not a miss when replayed.** The corpus includes a
real diff that claimed to enforce a rule "at every door" and skipped the OAuth door; nothing
flagged it when it merged. Replayed, kirei-gate flagged that exact door at HIGH in both cases that
review that diff. So the original miss was a process gap (the gate did not run on that diff, or
not in this form), not a blind spot two Claude models share.

**Can the corpus show a panel helps?** Not yet. At 14 cases with 4 misses, the best possible
panel result (it catches all 4, loses none) gives an exact McNemar p of 0.125. Even that perfect
result is not significant. It takes 6 discordant pairs, all one way, to reach p < 0.05. So the
corpus needs about 30 or more **introducing-commit** cases (revert cases are near ceiling and
cannot tell reviewers apart) before a panel comparison can mean anything.

## Recommendation

1. **Grow the corpus first**, to at least 30 introducing-commit cases. `harness.py analyze` makes
   each case about five minutes of work. A mature repo's `fix:` history with regression tests
   usually has far more candidates than that.
2. **Ship the calibration rule without a panel (done).** A disproved explicit safety claim
   ("never reveals", "every door", "fails closed") is now at least HIGH, and kirei-gate lists
   every entry point that reaches a newly guarded resource. Measured on the same corpus it
   caught the LOW-rated disclosure at HIGH (blocking 10/14 to 11/14, introducing-commit 3/7 to
   4/7) and named the missing handshake origin check, though only at MEDIUM. One discordant
   pair is not significant (McNemar p = 1.0); it is the first data point, not proof.
3. **Then build `--panel` and measure it** as the `gate-panel` variant against `gate-opus`. Keep
   it only if it wins on introducing-commit cases with McNemar p < 0.1 and adds no more than one
   off-target finding per case.

## Design

### Members

- `kirei-gate` (Opus), unchanged.
- One non-Claude reviewer, run headless and read-only. The candidate is `codex exec` with
  `--sandbox read-only` (codex-cli is installed, and the `handoff-codex` skill already drives it).
  The fallback is `grok`. Both get the same diff range, the stated intent, and the kirei-gate
  prompt body minus its Claude-specific tool notes.
- **Independence rule:** refuse a member whose model family matches the builder's, and refuse
  any binary that fronts that family. `minReviewers` is 2 and cannot be lowered.

### Findings format

Each member ends with a fenced JSON block, which the harness parser and the aggregator both read:

```json
{"verdict": "HOLD",
 "findings": [{"code": "tenant-scope", "severity": "HIGH", "file": "apps/api/src/x.ts",
               "line": 120, "end": 124, "claim": "..."}]}
```

`code` comes from a fixed vocabulary: `security`, `supply-chain`, `tenant-scope`,
`session-fence`, `data-loss`, `concurrency`, `gate-relaxed`, `scope-bypass`, `missing-test`,
`correctness`. A finding is **dropped** unless `file:line` exists at the head commit and lies
within 3 lines of a changed hunk, or in a file the finding explains is a missing door
(`claim` must name the changed file that makes it reachable).

### Preconditions (no member runs if any fails)

- the gate battery is green on the head;
- the intent is not generic (`wip`, `fix`, `update`, under 4 words);
- the diff is at most 40 files and 120k characters (the 102k race case is inside the budget,
  and still the hardest case in the corpus).

### Block rules (a script decides the verdict, not a prompt)

HOLD when any of these holds, and the output names which one:

1. fewer than 2 members returned parseable output;
2. any member's verdict is HOLD;
3. any `security`, `supply-chain`, `tenant-scope` or `session-fence` finding at CRITICAL;
4. two members report findings at HIGH or above within 3 lines of each other;
5. a majority report HIGH or above and at least one of those findings is grounded.

Otherwise MERGE. The output still ends with exactly `VERDICT: MERGE` or `VERDICT: HOLD`, so
`/kirei-wave` needs no change.

### Failure handling

- A member timeout, non-zero exit, truncated output or unparseable JSON is a failure with that
  cause recorded. Any member failure means no quorum, which is a HOLD naming the cause. It never
  degrades to a single-reviewer MERGE.
- A no-quorum result is **never cached**, so a later rerun cannot replay an outage as a verdict.

### Scope

Opt in per wave, for auth, tenancy, session and data-migration waves. Everything else
keeps the single kirei-gate.

### Harness integration

Add a `gate-panel` entry to `VARIANTS` whose runner starts both members in the case repo, applies
the block rules, and writes one combined review in the kirei-gate output format. `score` and
`compare` then work unchanged.

## Decisions needed before building

1. **Data egress.** The codex and grok members send the reviewed repo's source diffs to OpenAI
   or xAI. For a private repo, someone with authority over that code has to approve this; no
   builder or reviewer agent can.
2. **Which member.** `codex exec` (read-only sandbox, existing skill) or `grok`. Or both, as a
   three-member panel with a quorum of 2.
3. **What blocks deterministically.** The five rules above follow tsforge's `harness-review`. Rule 4 (two members
   agree) and rule 5 (a majority requests changes) are the ones to confirm. With two members,
   rule 5 means "both".
