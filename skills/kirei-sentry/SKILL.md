---
name: kirei-sentry
description: Set up production-ready Sentry error + performance monitoring for a project. Detects the framework (Electron, Next.js, Vite/React SPA, Node/Nest, React Native), asks the consent + scope + region decisions, verifies the current SDK API via Ref, then spawns the kirei-sentry agent to produce a framework-specific plan and kirei-loom to implement it — with consent gating, recursive PII scrubbing, CI-only source-map upload, region handling, and the exact CI secrets. Use whenever a user wants to add Sentry, set up error tracking / crash reporting, wire production monitoring, add performance tracing, or integrate Sentry into a new or existing project — even if they don't say "kirei". Invoke with /kirei-sentry; the skill asks the key decisions before working.
---

You have been invoked via `/kirei-sentry`. Follow this workflow precisely.

You orchestrate the `kirei-sentry` research agent (which designs a **production-ready, privacy-respecting** Sentry integration for the detected framework) and then `kirei-loom` (which implements it). The hard-won lessons — init timing, consent gating, PII scrubbing, source-map region handling, CI secrets — live in the agent; this skill gathers the few decisions only the user can make, then drives the flow.

You do **not** write integration code yourself, and you do **not** touch the user's Sentry dashboard or CI secrets — those are the user's steps. The agent prescribes; kirei-loom implements; the user finishes the SaaS/infra side.

---

## 0. PARSE FLAGS

Strip these before proceeding:

| Flag | Meaning |
|---|---|
| `--research-only` | Skip Step 5 (the execute agent). Deliver the plan only. |
| `--framework <fw>` | Override framework detection. Valid: `electron`, `nextjs`, `vite`, `node`, `nest`, `react-native`. |
| `--self-hosted` | Target a self-hosted Sentry instead of the cloud SaaS. |
| `--default-on` | Skip the consent question — use default-ON-with-disclosure (server/SaaS). Otherwise the default recommendation is opt-in/default-OFF. |
| `--scope <s>` | Skip the scope question. Valid: `errors`, `errors+perf`, `full` (incl. Session Replay). |

Any flag the user passes must reach the spawned agent's prompt **verbatim**.

---

## 1. ASK THE DECISIONS

Skip any question already answered by a flag. Otherwise use **AskUserQuestion** (these change the whole shape of the integration, so ask intentionally):

- **Consent model** — "Should error tracking be **opt-in (default OFF)** or **on by default**?"
  - *Opt-in, default OFF (Recommended for desktop / local-first / privacy-sensitive apps)* — nothing is sent until the user enables it; surfaced via a settings toggle (and onboarding step for apps that have one).
  - *On by default, with disclosure* — defensible for server-side / SaaS where there's no end-user device; ship a clear privacy disclosure + easy opt-out.
- **Scope** — "What should it capture?"
  - *Errors / crashes only* — smallest data + privacy surface.
  - *Errors + performance tracing (Recommended)* — adds transactions for bottleneck-hunting; for opt-in apps make perf a **separate** sub-toggle.
  - *Errors + performance + Session Replay* — maximum visibility, largest privacy + bandwidth footprint.
- **Hosting / region** — "Sentry **cloud** or **self-hosted**, and which region?" (US `sentry.io` / EU `de.sentry.io` / self-hosted URL). The region matters for source-map upload — getting it wrong 404s in CI.

If the user says "just use sensible defaults", proceed with **opt-in/default-OFF · errors+perf (perf as separate opt-in) · cloud, ask region from the DSN later** and say so.

---

## 2. ANNOUNCE PLAN

One line:

> "Running **kirei-sentry** to design a [framework] Sentry setup ([consent] · [scope] · [hosting/region]) → **kirei-loom** to implement. Findings to `docs/sentry/`."

Variants:
- `--research-only`: "… (research only — no implementation)."
- Framework still unknown: "… detecting framework first."

---

## 3. SPAWN THE RESEARCH AGENT

Spawn the `kirei-sentry` agent with the Agent tool. It has **no session context** — include everything.

**Prompt structure:**

```
Task: Set up production-ready Sentry for this project. [Plus any extra detail the user gave beyond /kirei-sentry.]

Working directory: [current working directory]

Decisions:
- Consent model: [opt-in default-off | default-on with disclosure]
- Scope: [errors | errors+perf | full incl. replay]
- Hosting / region: [cloud US | cloud EU | self-hosted <url>]

Flags: [--framework <fw> if set] [--self-hosted if set]

Context:
[Framework if known, build tooling, monorepo layout, existing settings/store mechanism, CI release workflow, any DSN already present (region hint), constraints the user mentioned.]

Verify the current SDK API via Ref MCP before prescribing — the API drifts across versions.

Deliver: structured KIREI-SENTRY HANDOFF block + write findings to docs/sentry/ in this repo.
```

Run in the **foreground** — you need the plan before implementing.

---

## 4. REVIEW FINDINGS

When the agent completes, read its KIREI-SENTRY HANDOFF:

- **Confirm a findings file was written** — Glob `docs/sentry/*.md` for today. If missing (look for `FINDINGS FILE NOT WRITTEN`), write it yourself from the handoff via the Write tool at `docs/sentry/YYYY-MM-DD-sentry-setup.md`.
- Spot-check 1-2 paths the plan references actually exist.
- Confirm complexity. Electron, multi-process, or any plan touching build config + CI + UI is **COMPLEX → kirei-loom**. Only a trivial single-entry SPA/Node init is `build`.

If the agent returned no handoff at all (errored / ran out of budget): tell the user in one sentence, point to anything partial, and offer to retry with a narrower scope. Do **not** fabricate a plan.

---

## 5. SPAWN THE EXECUTE AGENT

Skip if `--research-only` was passed.

Spawn **`kirei-loom`** (or `kirei-stitch` only if the handoff is genuinely SIMPLE):

**Prompt structure:**

```
Working directory: [current working directory]

Here is the KIREI-SENTRY HANDOFF:
[paste full handoff block]

Findings doc: docs/sentry/[filename]

Implement the setup following the fix order. Critical rules:
- Branch first (never the default branch). Small conventional commits.
- Use the project's package manager to add the Sentry packages into the correct workspace(s).
- The PII scrubber is privacy-critical — write a unit test proving it strips the OS username / home paths from event frames, nested breadcrumb data, and extra/contexts.
- The code must work with the DSN/secrets ABSENT (no init, no crash) — verify that gating.
- Do NOT create the Sentry project, set CI secrets, or touch the Sentry dashboard — those are out of scope (list them for the user).
- Run typecheck + lint + the relevant tests and report results. Do NOT push or open a PR.
```

Run in the foreground.

---

## 6. REPORT TO USER

Summarize:

- Framework + decisions, and what the agent designed (1-2 sentences).
- What kirei-loom changed (files / branch / commits) — or "research only, no code changes".
- **The manual checklist the user must still do** (pull this from the handoff's out-of-scope section):
  1. Create the Sentry project → copy the **DSN**.
  2. Create an **org auth token** (`org:ci` scope) and set CI secrets: `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT`, `SENTRY_DSN` (+ `SENTRY_URL` for EU/self-hosted). `SENTRY_DSN` is required for production telemetry to initialize at all.
  3. (Optional) Dashboard + Discord/Slack alert rules in the Sentry UI.
- How to verify (the checklist from the plan).
- Pointer to `docs/sentry/[filename]`.

---

## RULES

1. **Ask the decisions unless flagged.** Consent model especially — opt-in vs default-on is a product/privacy decision, not yours to assume.
2. **Verify the SDK API via Ref.** The agent does this; if it skipped it, send it back. Stale init code is the most common Sentry failure.
3. **`SENTRY_DSN` is the one secret that gates everything.** Make sure the final report flags that production builds ship dead without it.
4. **Region is a real footgun.** EU/self-hosted source-map upload 404s against the US default — the plan must set the `url`/`SENTRY_URL`.
5. **Never push or open PRs from this skill.** kirei-loom commits locally; the user pushes. Never touch the user's Sentry dashboard or secrets — those are the user's hands only.
6. **Privacy is non-negotiable.** `sendDefaultPii: false`, a recursive scrubber with a test, no Session Replay unless explicitly requested. If the plan is missing any of these, fix the plan before implementing.
