#!/usr/bin/env python3
"""
kirei gate-command discovery.
Lists a repo's gate battery by role, from files only: it never runs make, cmake or a package
script. Execute agents and /kirei-wave builders run what it prints.

Usage:
  python "${CLAUDE_PLUGIN_ROOT}/scripts/gate-commands.py" [repo] [--json]

Sources, highest priority first:
  1. A `gate-commands` section in AGENTS.md (then CLAUDE.md). A role listed there replaces
     every discovered command for that role. Format, one role per line:
       - test: `make test`
       - smoke: `make smoke` (slow)
  2. Makefile targets (rules and .PHONY). A Make role shadows the same CMake role, because a
     Makefile in a CMake repo usually wraps cmake.
  3. CMakePresets.json (configure, build and test presets), or enable_testing/add_test in
     CMakeLists.txt with ctest per build preset.
  4. package.json scripts (run with the package manager the lockfile names) and Cargo.toml.
  5. Python helpers in tools/ or scripts/ whose names say capture, golden or smoke (marked
     "guessed": read their usage before running them).

Roles: typecheck, lint, build, test, check, smoke, capture, goldens, feel, perf, assets.
fast roles run on every fix cycle; slow roles run once per slice before the PR. A goldens
target whose recipe accepts new images is listed as goldens-accept (manual) and never run.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROLES = ["typecheck", "lint", "build", "test", "check", "smoke", "capture", "goldens", "feel",
         "perf", "assets", "goldens-accept"]
FAST = {"typecheck", "lint", "build", "test"}
# A goldens target whose recipe rewrites the goldens is not a check. It is listed as
# goldens-accept with speed "manual": a gate never runs it, and a diff that ran it is a
# gate relaxation unless the intent names it.
ACCEPT = re.compile(r"accept|bless|--update|update-goldens|overwrite", re.I)

# Target or script name -> role. First match wins; names that match nothing are not gates.
NAME_ROLES = [
    (r"^(typecheck|type-check|types|tsc)$", "typecheck"),
    (r"^(lint|format-check|fmt-check|tidy|clippy|lint:.*)$", "lint"),
    (r"^(build|all|debug|release)$", "build"),
    (r"^(test|tests|unit|test-.*|test:.*)$", "test"),
    (r"^(check|verify|ci)$", "check"),
    (r"^smoke.*$", "smoke"),
    (r"^(shots|.*-shots|capture.*|screenshots?|showcase)$", "capture"),
    (r"^(goldens?|golden-.*)$", "goldens"),
    (r"^feel.*$", "feel"),
    (r"^(perf|bench.*|benchmark.*|profile)$", "perf"),
    (r"^(assets|asset-check|assets-check)$", "assets"),
]


def role_of(name):
    for pattern, role in NAME_ROLES:
        if re.match(pattern, name):
            return role
    return None


def read(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def from_agents_md(repo):
    """Return ({role: [(cmd, speed)]}, source) from the first gate-commands section found."""
    for name in ("AGENTS.md", "CLAUDE.md"):
        text = read(repo / name)
        if not text:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            head = re.match(r"^(#+)\s+.*gate-commands", line, re.I)
            if not head:
                continue
            level = len(head.group(1))
            found = {}
            for body in lines[i + 1:]:
                h = re.match(r"^(#+)\s", body)
                if h and len(h.group(1)) <= level:
                    break
                m = re.match(r"^\s*[-*]\s*`?([A-Za-z][\w-]*)`?\s*:\s*(.+)$", body)
                if not m:
                    continue
                cmds = re.findall(r"`([^`]+)`", m.group(2))
                speed = "slow" if re.search(r"\(slow\)", m.group(2), re.I) else (
                    "fast" if re.search(r"\(fast\)", m.group(2), re.I) else None)
                role = m.group(1).lower()
                speed = speed or ("fast" if role in FAST else "slow")
                found.setdefault(role, []).extend((c, speed) for c in cmds)
            if found:
                return found, f"{name} gate-commands"
    return {}, None


def make_targets(repo):
    """Return [(target, recipe text)] from the first Makefile found."""
    text = None
    for name in ("Makefile", "makefile", "GNUmakefile"):
        text = read(repo / name)
        if text:
            break
    if not text:
        return []
    text = re.sub(r"\\\r?\n", " ", text)
    names, recipes, current = [], {}, []
    for line in text.splitlines():
        if line.startswith("\t"):
            for target in current:
                recipes[target] = recipes.get(target, "") + line + "\n"
            continue
        if line.startswith("#") or not line.strip() or re.match(
                r"^\s*(ifeq|ifneq|ifdef|ifndef|else|endif)\b", line):
            continue
        current = []
        m = re.match(r"^\.PHONY\s*:(.*)$", line)
        if m:
            names += m.group(1).split()
            continue
        m = re.match(r"^([A-Za-z0-9][\w.-]*(?:\s+[A-Za-z0-9][\w.-]*)*)\s*:(?![=:])", line)
        if m:
            current = m.group(1).split()
            names += current
    seen = []
    for n in names:
        if n not in seen and not n.startswith("."):
            seen.append(n)
    return [(n, recipes.get(n, "")) for n in seen]


def from_make(repo):
    found = {}
    for target, recipe in make_targets(repo):
        role = role_of(target)
        if role == "goldens" and ACCEPT.search(recipe):
            role = "goldens-accept"
        if role:
            found.setdefault(role, []).append(f"make {target}")
    # Several build-flavour targets: keep the explicit build/all one if there is one.
    builds = found.get("build", [])
    explicit = [c for c in builds if c in ("make build", "make all")]
    if explicit:
        found["build"] = explicit
    return found


def preset_value(presets, name, key, seen=None):
    """Follow `inherits` to find a configure preset's key."""
    seen = seen or set()
    preset = presets.get(name)
    if not preset or name in seen:
        return None
    seen.add(name)
    if key in preset:
        return preset[key]
    parents = preset.get("inherits", [])
    for parent in [parents] if isinstance(parents, str) else parents:
        value = preset_value(presets, parent, key, seen)
        if value is not None:
            return value
    return None


def from_cmake(repo):
    lists = read(repo / "CMakeLists.txt")
    if lists is None:
        return {}
    has_tests = bool(re.search(r"\b(enable_testing|add_test|catch_discover_tests|"
                               r"gtest_discover_tests)\s*\(", lists, re.I))
    found = {}
    data = None
    raw = read(repo / "CMakePresets.json")
    if raw:
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
    if not data:
        found["build"] = ["cmake -S . -B build && cmake --build build"]
        if has_tests:
            found["test"] = ["ctest --test-dir build --output-on-failure"]
        return found
    configure = {p["name"]: p for p in data.get("configurePresets", []) if "name" in p}
    for b in data.get("buildPresets", []):
        if b.get("hidden"):
            continue
        cfg = b.get("configurePreset", b["name"])
        found.setdefault("build", []).append(
            f"cmake --preset {cfg} && cmake --build --preset {b['name']}")
    tests = [t for t in data.get("testPresets", []) if not t.get("hidden")]
    if tests:
        found["test"] = [f"ctest --preset {t['name']}" for t in tests]
    elif has_tests:
        for b in data.get("buildPresets", []):
            if b.get("hidden"):
                continue
            cfg = b.get("configurePreset", b["name"])
            binary = preset_value(configure, cfg, "binaryDir") or "build"
            binary = (binary.replace("${sourceDir}/", "").replace("${sourceDir}", ".")
                      .replace("${presetName}", cfg))
            config = b.get("configuration") or (
                (preset_value(configure, cfg, "cacheVariables") or {}).get("CMAKE_BUILD_TYPE"))
            flag = f" -C {config}" if config else ""
            found.setdefault("test", []).append(
                f"ctest --test-dir {binary}{flag} --output-on-failure")
    return found


def from_package_json(repo):
    raw = read(repo / "package.json")
    if not raw:
        return {}
    try:
        scripts = json.loads(raw).get("scripts") or {}
    except ValueError:
        return {}
    if (repo / "pnpm-lock.yaml").exists():
        run = "pnpm run"
    elif (repo / "bun.lock").exists() or (repo / "bun.lockb").exists():
        run = "bun run"
    elif (repo / "yarn.lock").exists():
        run = "yarn run"
    else:
        run = "npm run"
    found = {}
    for name in scripts:
        role = role_of(name)
        if role:
            found.setdefault(role, []).append(f"{run} {name}")
    return found


def from_cargo(repo):
    if not (repo / "Cargo.toml").exists():
        return {}
    return {"build": ["cargo build"], "test": ["cargo test"], "lint": ["cargo clippy"]}


def from_helpers(repo):
    found = {}
    for folder in ("tools", "scripts"):
        for path in sorted((repo / folder).glob("*.py")):
            stem = path.stem.lower()
            role = ("capture" if "capture" in stem else "goldens" if "golden" in stem
                    else "smoke" if "smoke" in stem else None)
            if role:
                found.setdefault(role, []).append(f"python {folder}/{path.name}")
    return found


def discover(repo):
    entries = {}  # role -> list of (cmd, speed, source)

    def add(found, source, speed=None):
        for role, cmds in found.items():
            for cmd in cmds:
                if isinstance(cmd, tuple):
                    cmd, sp = cmd
                else:
                    sp = speed or ("fast" if role in FAST else
                                   "manual" if role == "goldens-accept" else "slow")
                if all(cmd != c for c, _, _ in entries.get(role, [])):
                    entries.setdefault(role, []).append((cmd, sp, source))

    declared, declared_source = from_agents_md(repo)
    make = from_make(repo)
    cmake = {r: c for r, c in from_cmake(repo).items() if r not in make}
    add(make, "Makefile")
    add(cmake, "CMakePresets.json" if (repo / "CMakePresets.json").exists() else "CMakeLists.txt")
    add(from_package_json(repo), "package.json")
    add(from_cargo(repo), "Cargo.toml")
    helpers = {r: c for r, c in from_helpers(repo).items() if r not in entries}
    add(helpers, "guessed from file name")
    for role, cmds in declared.items():
        entries[role] = [(c, sp, declared_source) for c, sp in cmds]
    order = {r: i for i, r in enumerate(ROLES)}
    return sorted(((r, c, sp, s) for r, items in entries.items() for c, sp, s in items),
                  key=lambda e: order.get(e[0], len(ROLES)))


def main():
    parser = argparse.ArgumentParser(description="List a repo's gate commands by role.")
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args()
    repo = Path(args.repo)
    if not repo.is_dir():
        print(f"not a directory: {repo}", file=sys.stderr)
        return 2
    rows = discover(repo)
    if args.json:
        print(json.dumps([{"role": r, "command": c, "speed": sp, "source": s}
                          for r, c, sp, s in rows], indent=2))
        return 0
    if not rows:
        print("no gate commands found: read the README and CONTRIBUTING for the real checks")
        return 0
    width = max(len(r) for r, _, _, _ in rows)
    for role, cmd, speed, source in rows:
        print(f"{role.ljust(width)}  {speed.ljust(6)}  {cmd}  ({source})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
