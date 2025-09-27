#!/usr/bin/env python3
import argparse
import os
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "data" / "docs"

# Matches Markdown links but not images. Captures display text and URL.
LINK_RE = re.compile(r'''(?<!\!)\[(?P<text>[^\]]+)\]\((?P<url>[^)\s]+)(?:\s+"[^"]*")?\)''')

FENCE_RE = re.compile(r"^```.*$")  # detect fenced code blocks


def transform_line(line: str) -> str:
    """
    Transform a single line by converting external links to "Text — host"
    and removing links pointing to local .md files entirely. Skips image links.
    """
    def _repl(m: re.Match) -> str:
        text = m.group('text').strip()
        url = m.group('url').strip()
        # Decide based on URL
        p = urlparse(url)
        # External http(s)
        if p.scheme in ("http", "https"):
            host = p.netloc
            if host:
                return f"{text} — {host}"
            else:
                # Unlikely, but fallback to text only
                return text
        # Local/relative
        if url.lower().endswith('.md') or (not p.scheme and not p.netloc and url.lower().endswith('.md')):
            return ""  # remove entirely
        # Other relative resources (e.g., anchors, pdf). Keep just text.
        return text

    new_line = LINK_RE.sub(_repl, line)

    # Remove empty list items like "- " or "* " caused by full removal
    if re.match(r"^\s*([*+-])\s*$", new_line):
        return ""  # drop the line entirely

    # Normalize double spaces created by removals
    new_line = re.sub(r"\s{2,}", " ", new_line).rstrip()
    return new_line


def transform_content(md: str) -> str:
    """
    Transform full Markdown content while preserving fenced code blocks.
    We only process non-code sections.
    """
    lines = md.splitlines()
    out_lines = []
    in_fence = False
    for line in lines:
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out_lines.append(line.rstrip())
            continue
        if in_fence:
            out_lines.append(line.rstrip())
        else:
            out_lines.append(transform_line(line))
    # Remove stray empty lines created by deletions (collapse 3+ empties to 1)
    text = "\n".join(out_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def process_file(path: Path, write: bool, backup: bool) -> bool:
    orig = path.read_text(encoding='utf-8')
    new = transform_content(orig)
    if new != orig and write:
        if backup:
            bak = path.with_suffix(path.suffix + ".bak")
            bak.write_text(orig, encoding='utf-8')
        path.write_text(new, encoding='utf-8')
    return new != orig


def main():
    ap = argparse.ArgumentParser(description="Reformat Markdown links: external -> 'Text — host', remove local .md links.")
    ap.add_argument('--write', action='store_true', help='Apply changes to files (otherwise dry-run).')
    ap.add_argument('--no-backup', action='store_true', help='Do not write .bak backup files when writing.')
    ap.add_argument('--limit', type=int, default=None, help='Only process first N files (for testing).')
    args = ap.parse_args()

    if not DOCS_DIR.exists():
        print(f"Docs directory not found: {DOCS_DIR}")
        return 1

    md_files = list(DOCS_DIR.rglob('*.md'))
    if args.limit:
        md_files = md_files[: args.limit]

    changed = 0
    for p in md_files:
        did_change = process_file(p, write=args.write, backup=not args.no_backup)
        status = "CHANGED" if did_change else "ok"
        if did_change or not args.write:
            print(f"[{status}] {p.relative_to(ROOT)}")
        if did_change:
            changed += 1

    print(f"\nSummary: {changed} file(s) would be changed" + (" (applied)." if args.write else "."))
    if not args.write:
        print("Run with --write to apply changes. A .bak will be created by default.")


if __name__ == '__main__':
    raise SystemExit(main())
