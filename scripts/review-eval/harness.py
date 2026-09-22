#!/usr/bin/env python3
"""
kirei review-recall harness.

Measures how often a reviewer (kirei-gate by default) catches a real, known bug, by replaying
the diff that introduced it (or a revert of its fix) and scoring the reviewer's grounded findings
against the lines the real fix changed.

Subcommands:
  analyze  <fix-sha>                 blame the fix's non-test hunks at <fix>^ and rank the commits
                                     that wrote those lines (picks the introducing commit)
  prepare  --corpus C --out DIR      build one isolated repo per case under DIR/cases/<id>/
  run      --out DIR --variant V     run reviewer variant V on every prepared case
  score    --out DIR [--variant V]   score every variant (or one) and print recall + intervals
  compare  --out DIR A B             two-proportion z-test (and exact McNemar) between variants

Case repos are `git init` + an alternates file pointing at the source repo's object store, with a
single `review` branch. No ref points at any commit after the diff under review, so a reviewer
running `git log --all` cannot find the fix. Nothing is written to the source repo.

Hit rule (NEAR = 3): a finding is a hit when its path matches a ground-truth file and its line
(or line range) lies within 3 lines of a ground-truth line. A case is caught when at least one
finding hits. Findings that hit nothing are counted as off-target (not all are false: a reviewer
can find a different real bug, so read them before calling them noise).

Python 3.9 compatible; standard library only.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from collections import Counter

NEAR = 3
HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(os.path.dirname(HERE))

TEST_PATH = re.compile(
    r"(\.(spec|test|e2e-spec)\.[cm]?[jt]sx?$)|(/__tests__/)|(/__fixtures__/)|(^|/)(test|tests|e2e)/"
)

VARIANTS = {
    # name: (agent prompt file relative to plugin root, model alias)
    "gate-opus": ("agents/kirei-gate.md", "opus"),
    "gate-sonnet": ("agents/kirei-gate.md", "sonnet"),
    # The same prompt file under a new name, so a prompt change can be measured against a run
    # snapshotted before it (each run keeps its own .system-prompt.md).
    "gate-opus-v2": ("agents/kirei-gate.md", "opus"),
}

FINDING = re.compile(
    r"^\s*(?:\d+\.|[-*])\s*(?:\*\*)?\[?(CRITICAL|HIGH|MEDIUM|LOW)\]?(?:\*\*)?\s*`([^`\s]+?):(\d+)(?:\s*[-–]\s*(\d+))?[^`]*`"
)
UNCERTAIN = re.compile(r"^\s*[-*]\s*`([^`\s]+?):(\d+)(?:\s*[-–]\s*(\d+))?[^`]*`")
VERDICT = re.compile(r"^VERDICT: (MERGE|HOLD)\s*$", re.M)
LOC = re.compile(r"`([^`\s:]*?):(\d+)(?:\s*[-\u2013]\s*(\d+))?[^`]*`")


def locations(line, first_path):
    """Every `path:line` / `:line` ref on a finding line; a bare `:line` reuses the last path."""
    locs = []
    path = first_path
    for m in LOC.finditer(line):
        p, a, b = m.groups()
        if p:
            path = p
        locs.append((path, int(a), int(b or a)))
    return locs


def git(repo, *args, check=True, env=None):
    out = subprocess.run(
        ["git", "-C", repo] + list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if check and out.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), out.stderr.decode(errors="replace")))
    return out.stdout.decode(errors="replace")


def is_test(path):
    return bool(TEST_PATH.search(path))


def changed_files(repo, a, b):
    rows = []
    for line in git(repo, "diff", "--name-status", "--no-renames", a, b).splitlines():
        status, path = line.split("\t", 1)
        rows.append((status, path))
    return rows


HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def hunks(repo, a, b, path):
    """Yield (old_start, old_len, new_start, new_len) for a -U0 diff of one file."""
    for line in git(repo, "diff", "-U0", "--no-renames", a, b, "--", path).splitlines():
        m = HUNK.match(line)
        if m:
            os_, ol, ns, nl = m.groups()
            yield int(os_), int(ol if ol is not None else 1), int(ns), int(nl if nl is not None else 1)


def touched_old_lines(repo, a, b, path):
    """Lines of `a`'s version of path that the a->b diff removes or inserts next to."""
    lines = set()
    for os_, ol, _ns, _nl in hunks(repo, a, b, path):
        if ol == 0:
            lines.update({max(1, os_), os_ + 1})
        else:
            lines.update(range(os_, os_ + ol))
    return lines


def touched_new_lines(repo, a, b, path):
    lines = set()
    for _os, _ol, ns, nl in hunks(repo, a, b, path):
        if nl == 0:
            lines.update({max(1, ns), ns + 1})
        else:
            lines.update(range(ns, ns + nl))
    return lines


def map_new_to_old(repo, old, new, path, new_lines):
    """Map line numbers in `new`'s version of path back to `old`'s version, through the diff.
    A line inside a changed hunk maps to that hunk's old span."""
    hs = list(hunks(repo, old, new, path))
    out = set()
    for ln in new_lines:
        shift = 0
        mapped = None
        for os_, ol, ns, nl in hs:
            if nl and ns <= ln < ns + nl:
                mapped = set(range(os_, os_ + max(ol, 1)))
                break
            before = (ns + nl <= ln) if nl else (ns < ln)
            if before:
                shift += ol - nl
        if mapped is None:
            mapped = {ln + shift}
        out.update(mapped)
    return out


def file_exists(repo, rev, path):
    return subprocess.run(
        ["git", "-C", repo, "cat-file", "-e", "%s:%s" % (rev, path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


# ---------------------------------------------------------------- analyze


def blame_counts(repo, fix):
    counts = Counter()
    per_file = {}
    for status, path in changed_files(repo, fix + "^", fix):
        if is_test(path) or status == "A":
            continue
        lines = touched_old_lines(repo, fix + "^", fix, path)
        fc = Counter()
        for ln in sorted(lines):
            out = git(repo, "blame", "-w", "--porcelain", "-L", "%d,%d" % (ln, ln), fix + "^", "--", path, check=False)
            if out:
                fc[out.split()[0]] += 1
        per_file[path] = fc
        counts.update(fc)
    return counts, per_file


def cmd_analyze(args):
    counts, per_file = blame_counts(args.repo, args.fix)
    print("fix %s: %s" % (args.fix, git(args.repo, "log", "-1", "--format=%s", args.fix).strip()))
    for path, fc in per_file.items():
        print("  %s" % path)
        for sha, n in fc.most_common(4):
            print("    %3d  %s" % (n, git(args.repo, "log", "-1", "--format=%h %ad %s", "--date=short", sha).strip()))
    total = sum(counts.values())
    if total:
        sha, n = counts.most_common(1)[0]
        stat = git(args.repo, "show", "--shortstat", "--format=", sha).strip()
        print("dominant: %s  %d/%d touched lines  (%s)" % (sha[:10], n, total, stat))


# ---------------------------------------------------------------- prepare


def init_case_repo(src, path):
    os.makedirs(path, exist_ok=True)
    if not os.path.isdir(os.path.join(path, ".git")):
        subprocess.run(["git", "init", "-q", path], check=True)
    src_objects = os.path.join(git(src, "rev-parse", "--path-format=absolute", "--git-common-dir").strip(), "objects")
    with open(os.path.join(path, ".git", "objects", "info", "alternates"), "w") as fh:
        fh.write(src_objects + "\n")
    git(path, "config", "user.name", "review-eval")
    git(path, "config", "user.email", "review-eval@localhost")


def commit_tree(repo, tree, parent, message, date):
    env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    out = subprocess.run(
        ["git", "-C", repo, "commit-tree", tree, "-p", parent, "-m", message],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=True,
    )
    return out.stdout.decode().strip()


def prepare_case(src, case, out_dir):
    cid = case["id"]
    repo = os.path.join(out_dir, "cases", cid, "repo")
    init_case_repo(src, repo)
    gt_files = case.get("files")
    fix = None
    if case["mode"] != "patch":
        fix = git(src, "rev-parse", case["fix"]).strip()
        fix_parent = fix + "^"
        fix_parent_sha = git(src, "rev-parse", fix_parent).strip()
        fix_src_files = [p for s, p in changed_files(src, fix_parent, fix) if not is_test(p)]
        if gt_files:
            fix_src_files = [p for p in fix_src_files if p in gt_files]

    if case["mode"] == "introducing":
        head = git(src, "rev-parse", case["introducing"]).strip()
        base = git(src, "rev-parse", head + "^").strip()
        intent = git(src, "log", "-1", "--format=%B", head).strip()
        ground = {}
        for path in fix_src_files:
            lines_at_parent = touched_old_lines(src, fix_parent, fix, path)
            if not file_exists(src, head, path):
                continue
            mapped = map_new_to_old(src, head, fix_parent_sha, path, lines_at_parent)
            ground[path] = sorted(mapped)
    elif case["mode"] == "revert":
        # base = the fix with its test changes undone; head = the fix's parent. So the diff under
        # review is the reverse of the fix's non-test hunks and the tree contains no regression test.
        # Files outside the case's `files` list (a guard the fix also added, say) are held at the
        # fix's parent like tests, so the revert does not advertise the guard it deletes.
        git(repo, "read-tree", fix)
        for status, path in changed_files(src, fix_parent, fix):
            if not is_test(path) and (not gt_files or path in gt_files):
                continue
            if file_exists(src, fix_parent, path):
                blob = git(src, "rev-parse", "%s:%s" % (fix_parent, path)).strip()
                mode = git(src, "ls-tree", fix_parent, "--", path).split()[0]
                git(repo, "update-index", "--add", "--cacheinfo", "%s,%s,%s" % (mode, blob, path))
            else:
                git(repo, "update-index", "--force-remove", "--", path)
        base_tree = git(repo, "write-tree").strip()
        date = git(src, "log", "-1", "--format=%aI", fix).strip()
        base = commit_tree(repo, base_tree, fix_parent_sha, "baseline", date)
        head_tree = git(src, "rev-parse", fix_parent + "^{tree}").strip()
        intent = case["intent"]
        head = commit_tree(repo, head_tree, base, intent, date)
        ground = {}
        for path in fix_src_files:
            ground[path] = sorted(touched_new_lines(repo, base, head, path))
    elif case["mode"] == "patch":
        # A planted defect: `patch` (relative to the corpus file) applied on top of `base`.
        base = git(src, "rev-parse", case["base"]).strip()
        git(repo, "read-tree", base)
        subprocess.run(["git", "-C", repo, "apply", "--cached", case["patch_path"]], check=True)
        tree = git(repo, "write-tree").strip()
        date = git(src, "log", "-1", "--format=%aI", base).strip()
        intent = case["intent"]
        head = commit_tree(repo, tree, base, intent, date)
        ground = {}
        for path in case["files"]:
            ground[path] = sorted(touched_new_lines(repo, base, head, path))
    else:
        raise ValueError("unknown mode %r" % case["mode"])

    git(repo, "update-ref", "refs/heads/review", head)
    git(repo, "symbolic-ref", "HEAD", "refs/heads/review")
    git(repo, "reset", "-q", "--hard", head)
    stat = git(repo, "diff", "--shortstat", base, head).strip()
    meta = {
        "id": cid,
        "mode": case["mode"],
        "fix": fix,
        "base": base,
        "head": head,
        "intent": intent,
        "ground_truth": ground,
        "diffstat": stat,
        "invariant": case.get("invariant", ""),
        "tags": case.get("tags", []),
    }
    with open(os.path.join(out_dir, "cases", cid, "case.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    return meta


def cmd_prepare(args):
    with open(args.corpus) as fh:
        corpus = json.load(fh)
    only = set(args.only.split(",")) if args.only else None
    for case in corpus["cases"]:
        if only and case["id"] not in only:
            continue
        if "patch" in case:
            case["patch_path"] = os.path.join(os.path.dirname(os.path.abspath(args.corpus)), case["patch"])
        meta = prepare_case(args.repo, case, args.out)
        gt = ", ".join("%s:%s" % (p, _ranges(ls)) for p, ls in meta["ground_truth"].items())
        print("%-28s %-11s %s | GT %s" % (meta["id"], meta["mode"], meta["diffstat"], gt or "NONE"))
        if not meta["ground_truth"]:
            print("  WARNING: no ground-truth lines; this case cannot be scored", file=sys.stderr)


def _ranges(lines):
    lines = sorted(lines)
    out = []
    for ln in lines:
        if out and ln == out[-1][1] + 1:
            out[-1][1] = ln
        else:
            out.append([ln, ln])
    return ",".join(str(a) if a == b else "%d-%d" % (a, b) for a, b in out)


# ---------------------------------------------------------------- run


def agent_body(rel):
    with open(os.path.join(PLUGIN_ROOT, rel)) as fh:
        text = fh.read()
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.strip()


def run_one(out_dir, cid, variant, timeout, sys_prompt):
    case_dir = os.path.join(out_dir, "cases", cid)
    with open(os.path.join(case_dir, "case.json")) as fh:
        meta = json.load(fh)
    _prompt_rel, model = VARIANTS[variant]
    res_dir = os.path.join(out_dir, "results", variant)
    dest = os.path.join(res_dir, cid + ".md")
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return "cached"
    task = (
        "Diff range: %s..%s (in the git repository at the current working directory).\n"
        "Stated intent (the commit message the author wrote):\n\n%s\n\n"
        "Stress security, tenancy and data-integrity claims. Follow your output contract exactly."
        % (meta["base"], meta["head"], meta["intent"])
    )
    started = time.time()
    try:
        proc = subprocess.run(
            [
                "claude", "-p", "--safe-mode",
                "--model", model,
                "--tools", "Bash,Read,Glob,Grep",
                "--allowedTools", "Bash,Read,Glob,Grep",
                "--append-system-prompt-file", sys_prompt,
                task,
            ],
            cwd=os.path.join(case_dir, "repo"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        body = proc.stdout.decode(errors="replace")
        status = "ok" if proc.returncode == 0 else "exit-%d" % proc.returncode
        if proc.returncode != 0:
            body += "\n\n<!-- stderr -->\n" + proc.stderr.decode(errors="replace")[-4000:]
    except subprocess.TimeoutExpired:
        body, status = "", "timeout"
    elapsed = int(time.time() - started)
    with open(dest if status == "ok" else dest + "." + status, "w") as fh:
        fh.write(body)
    return "%s in %ds" % (status, elapsed)


def cmd_run(args):
    from concurrent.futures import ThreadPoolExecutor

    ids = sorted(os.listdir(os.path.join(args.out, "cases")))
    # Snapshot the reviewer prompt once, so editing the agent mid-run cannot mix two prompts.
    res_dir = os.path.join(args.out, "results", args.variant)
    os.makedirs(res_dir, exist_ok=True)
    prompt_rel = VARIANTS[args.variant][0]
    sys_prompt = os.path.join(res_dir, ".system-prompt.md")
    if not os.path.exists(sys_prompt):
        with open(sys_prompt, "w") as fh:
            fh.write(agent_body(prompt_rel))
    if args.only:
        ids = [i for i in ids if i in set(args.only.split(","))]
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        futs = {i: pool.submit(run_one, args.out, i, args.variant, args.timeout, sys_prompt) for i in ids}
        for i, f in futs.items():
            try:
                print("%-28s %s" % (i, f.result()), flush=True)
            except Exception as exc:  # report and continue with the other cases
                print("%-28s error: %s" % (i, exc), flush=True)


# ---------------------------------------------------------------- score


def parse_review(text):
    findings = []
    in_uncertain = False
    for line in text.splitlines():
        if re.match(r"^\s*\*\*Uncertainties", line):
            in_uncertain = True
            continue
        m = FINDING.match(line)
        if m:
            sev, path, a, b = m.groups()
            findings.append({"severity": sev, "path": path, "start": int(a), "end": int(b or a), "uncertain": False,
                             "locs": locations(line, path)})
            continue
        if in_uncertain:
            m = UNCERTAIN.match(line)
            if m:
                path, a, b = m.groups()
                findings.append({"severity": "UNCERTAIN", "path": path, "start": int(a), "end": int(b or a), "uncertain": True,
                                 "locs": locations(line, path)})
    verdicts = VERDICT.findall(text)
    return findings, (verdicts[-1] if verdicts else None)


def path_match(finding_path, gt_path):
    fp = finding_path.lstrip("./")
    return fp == gt_path or gt_path.endswith("/" + fp) or fp.endswith("/" + gt_path)


def hits(finding, ground):
    locs = finding.get("locs") or [(finding["path"], finding["start"], finding["end"])]
    for fpath, start, end in locs:
        for path, lines in ground.items():
            if not path_match(fpath, path):
                continue
            for ln in lines:
                if start - NEAR <= ln <= end + NEAR:
                    return True
    return False


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def load_audit(out_dir, variant):
    """Optional human audit: results/<variant>/audit.json maps a case id to
    {"any": bool, "blocking": bool, "note": str}. The line rule can credit a finding that sits
    near the fixed lines but describes something else, or miss one that names the bug from a
    different line; the audit records what the finding actually says."""
    path = os.path.join(out_dir, "results", variant, "audit.json")
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return json.load(fh)


def score_variant(out_dir, variant):
    rows = []
    audit = load_audit(out_dir, variant)
    cases_dir = os.path.join(out_dir, "cases")
    for cid in sorted(os.listdir(cases_dir)):
        with open(os.path.join(cases_dir, cid, "case.json")) as fh:
            meta = json.load(fh)
        path = os.path.join(out_dir, "results", variant, cid + ".md")
        if not os.path.exists(path):
            rows.append({"id": cid, "mode": meta["mode"], "status": "missing"})
            continue
        with open(path) as fh:
            text = fh.read()
        findings, verdict = parse_review(text)
        ground = meta["ground_truth"]
        hit_any = [f for f in findings if hits(f, ground)]
        hit_block = [f for f in hit_any if f["severity"] in ("CRITICAL", "HIGH")]
        rows.append({
            "id": cid,
            "mode": meta["mode"],
            "status": "ok",
            "verdict": verdict,
            "findings": len([f for f in findings if not f["uncertain"]]),
            "uncertain": len([f for f in findings if f["uncertain"]]),
            "caught_any": bool(hit_any),
            "caught_blocking": bool(hit_block) and verdict == "HOLD",
            "off_target": len([f for f in findings if not f["uncertain"] and not hits(f, ground)]),
            "hit_lines": ["%s %s:%d" % (f["severity"], f["path"], f["start"]) for f in hit_any],
        })
        if cid in audit:
            rows[-1]["audited_any"] = bool(audit[cid]["any"])
            rows[-1]["audited_blocking"] = bool(audit[cid]["blocking"]) and verdict == "HOLD"
            rows[-1]["audit_note"] = audit[cid].get("note", "")
    return rows


def summarize(variant, rows):
    ok = [r for r in rows if r["status"] == "ok"]
    n = len(ok)
    lines = ["## %s  (%d scored, %d missing)" % (variant, n, len(rows) - n), ""]
    lines.append("| case | mode | verdict | findings | off-target | caught (any) | caught (HIGH+ & HOLD) | hit |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        if r["status"] != "ok":
            lines.append("| %s | %s | %s | | | | | |" % (r["id"], r["mode"], r["status"]))
            continue
        lines.append("| %s | %s | %s | %d | %d | %s | %s | %s |" % (
            r["id"], r["mode"], r["verdict"] or "none", r["findings"], r["off_target"],
            "yes" if r["caught_any"] else "no", "yes" if r["caught_blocking"] else "no",
            "; ".join(r["hit_lines"]) or "",
        ))
    lines.append("")
    for label, key in (("recall (any grounded finding)", "caught_any"), ("recall (blocking: HIGH+ hit and HOLD)", "caught_blocking")):
        k = sum(1 for r in ok if r[key])
        lo, hi = wilson(k, n)
        lines.append("- %s: %d/%d = %.0f%%  (Wilson 95%% CI %.0f%%-%.0f%%)" % (label, k, n, 100.0 * k / n if n else 0, 100 * lo, 100 * hi))
        for mode in ("introducing", "revert"):
            sub = [r for r in ok if r["mode"] == mode]
            if sub:
                ks = sum(1 for r in sub if r[key])
                lines.append("  - %s cases: %d/%d" % (mode, ks, len(sub)))
    audited = [r for r in ok if "audited_any" in r]
    if audited:
        lines.append("- hand-audited (%d/%d cases audited; the finding must describe the real defect):" % (len(audited), n))
        for label, key in (("any", "audited_any"), ("blocking", "audited_blocking")):
            k = sum(1 for r in audited if r[key])
            lo, hi = wilson(k, len(audited))
            lines.append("  - %s: %d/%d = %.0f%%  (Wilson 95%% CI %.0f%%-%.0f%%)" % (label, k, len(audited), 100.0 * k / len(audited), 100 * lo, 100 * hi))
        for r in audited:
            if r["audited_any"] != r["caught_any"] or r["audited_blocking"] != r["caught_blocking"]:
                lines.append("  - override %s: %s" % (r["id"], r["audit_note"]))
    holds = sum(1 for r in ok if r["verdict"] == "HOLD")
    lines.append("- HOLD verdicts: %d/%d" % (holds, n))
    if n:
        lines.append("- off-target findings per case: mean %.1f (total %d)" % (sum(r["off_target"] for r in ok) / n, sum(r["off_target"] for r in ok)))
    return "\n".join(lines)


def cmd_score(args):
    variants = [args.variant] if args.variant else sorted(
        v for v in os.listdir(os.path.join(args.out, "results")) if not v.startswith(".")
    )
    report = []
    for v in variants:
        rows = score_variant(args.out, v)
        with open(os.path.join(args.out, "results", v, "score.json"), "w") as fh:
            json.dump(rows, fh, indent=2)
        report.append(summarize(v, rows))
    print("\n\n".join(report))


def two_proportion_z(k1, n1, k2, n2):
    p1, p2 = k1 / n1, k2 / n2
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 1.0
    z = (p1 - p2) / se
    pval = math.erfc(abs(z) / math.sqrt(2))
    return z, pval


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def cmd_compare(args):
    for key in ("caught_any", "caught_blocking", "audited_any", "audited_blocking"):
        a = {r["id"]: r for r in score_variant(args.out, args.a) if r["status"] == "ok" and key in r}
        b = {r["id"]: r for r in score_variant(args.out, args.b) if r["status"] == "ok" and key in r}
        common = sorted(set(a) & set(b))
        if not common:
            continue
        n = len(common)
        ka = sum(1 for i in common if a[i][key])
        kb = sum(1 for i in common if b[i][key])
        z, p = two_proportion_z(ka, n, kb, n) if n else (0.0, 1.0)
        only_a = sum(1 for i in common if a[i][key] and not b[i][key])
        only_b = sum(1 for i in common if b[i][key] and not a[i][key])
        print("%s: %s %d/%d vs %s %d/%d  z=%.2f p=%.3f  | paired: only-%s=%d only-%s=%d exact McNemar p=%.3f"
              % (key, args.a, ka, n, args.b, kb, n, z, p, args.a, only_a, args.b, only_b, mcnemar_exact(only_a, only_b)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=os.environ.get("REVIEW_EVAL_REPO", "."), help="source repo with the corpus history")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("analyze")
    p.add_argument("fix")
    p = sub.add_parser("prepare")
    p.add_argument("--corpus", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--only")
    p = sub.add_parser("run")
    p.add_argument("--out", required=True)
    p.add_argument("--variant", required=True, choices=sorted(VARIANTS))
    p.add_argument("--parallel", type=int, default=3)
    p.add_argument("--timeout", type=int, default=1500)
    p.add_argument("--only")
    p = sub.add_parser("score")
    p.add_argument("--out", required=True)
    p.add_argument("--variant")
    p = sub.add_parser("compare")
    p.add_argument("--out", required=True)
    p.add_argument("a")
    p.add_argument("b")
    args = ap.parse_args()
    {"analyze": cmd_analyze, "prepare": cmd_prepare, "run": cmd_run, "score": cmd_score, "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    main()
