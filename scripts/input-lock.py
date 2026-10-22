#!/usr/bin/env python3
"""
kirei input lock: one on-screen pass at a time.
Parallel agents that launch a window, move the cursor or need the foreground share one real
mouse and one foreground window. This wrapper takes a machine-wide lock, runs one command,
and releases the lock when the command ends, even on failure or Ctrl+C.

Usage:
  python -I "${CLAUDE_PLUGIN_ROOT}/scripts/input-lock.py" --role <who> -- <command> [args...]

The lock is a directory (atomic to create on Windows and macOS) in the system temp folder,
kirei-input.lock, holding owner.txt with the role, the PID of this wrapper and the time. The
wrapper stays alive for the whole pass, so its PID is a true liveness signal. A lock is stale
when that PID is dead or the lock is older than --stale minutes (default 10); a stale lock is
taken over. Otherwise the wrapper waits up to --wait seconds (default 900), then exits 75
naming the holder. The exit code is the command's own.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_LOCK = Path(tempfile.gettempdir()) / "kirei-input.lock"


def pid_alive(pid):
    if pid <= 0:
        return False
    if os.name == "nt":
        # Never os.kill(pid, 0) on Windows: it terminates the process.
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return kernel.GetLastError() == 5  # access denied: it exists
        code = ctypes.c_ulong()
        kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def owner(lock):
    try:
        text = (lock / "owner.txt").read_text(encoding="utf-8")
    except OSError:
        return {}
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def stale(lock, minutes):
    info = owner(lock)
    try:
        pid, since = int(info.get("pid", "0")), float(info.get("time", "0"))
    except ValueError:
        return True
    if not info:
        # owner.txt not written yet: give the creator a moment before calling it stale.
        try:
            return time.time() - lock.stat().st_mtime > 30
        except OSError:
            return False
    return not pid_alive(pid) or time.time() - since > minutes * 60


def acquire(lock, role, wait=900.0, minutes=10.0):
    deadline = time.time() + wait
    while True:
        try:
            lock.mkdir()
        except FileExistsError:
            if stale(lock, minutes):
                shutil.rmtree(lock, ignore_errors=True)
                continue
            if time.time() >= deadline:
                return False
            time.sleep(2)
            continue
        (lock / "owner.txt").write_text(
            f"role={role}\npid={os.getpid()}\ntime={time.time():.0f}\n", encoding="utf-8")
        return True


def release(lock):
    if owner(lock).get("pid") == str(os.getpid()):
        shutil.rmtree(lock, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Run one command under the shared input lock.")
    parser.add_argument("--role", default="agent", help="who holds the lock, e.g. wave/menu-ui")
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--wait", type=float, default=900.0, help="seconds to wait for the lock")
    parser.add_argument("--stale", type=float, default=10.0, help="minutes before a lock is stale")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("give the command after --")
    if not acquire(args.lock, args.role, args.wait, args.stale):
        info = owner(args.lock)
        print(f"input lock busy: held by {info.get('role', '?')} (pid {info.get('pid', '?')}) "
              f"at {args.lock}", file=sys.stderr)
        return 75
    try:
        return subprocess.call(command)
    except KeyboardInterrupt:
        return 130
    except OSError as exc:
        print(f"could not start {command[0]}: {exc}", file=sys.stderr)
        return 127
    finally:
        release(args.lock)


if __name__ == "__main__":
    sys.exit(main())
