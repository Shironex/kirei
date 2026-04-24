#!/usr/bin/env python3
"""
kirei write-findings helper.
Creates docs/research/ if needed, names the file with today's date, writes content from stdin.

Usage (from agent via Bash):
  python "${CLAUDE_PLUGIN_ROOT}/scripts/write-findings.py" "topic-slug" << 'FINDINGS'
  # Research: Topic
  ...full markdown content...
  FINDINGS

Standalone (no plugin root):
  python /path/to/write-findings.py "topic-slug" << 'FINDINGS'
  ...
  FINDINGS

Arguments:
  topic       Short kebab-case slug for the filename  e.g. "auth-token-refresh"

Options:
  --date      Override date (YYYY-MM-DD). Defaults to today.
  --dir       Output directory. Defaults to docs/research relative to cwd.
"""
import sys
import argparse
from datetime import date
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a kirei research findings document.")
    parser.add_argument("topic", help="Short kebab-case topic slug")
    parser.add_argument("--date", default=date.today().isoformat(), help="Date override (YYYY-MM-DD)")
    parser.add_argument("--dir", default="docs/research", help="Output directory (relative to cwd)")
    args = parser.parse_args()

    content = sys.stdin.read()
    if not content.strip():
        print("error: no content on stdin — pipe your findings markdown into this script", file=sys.stderr)
        return 1

    topic = args.topic.lower().replace(" ", "-").replace("_", "-")
    output_dir = Path(args.dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{args.date}-{topic}.md"
    filepath = output_dir / filename
    filepath.write_text(content, encoding="utf-8")

    print(f"ok: {filepath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
