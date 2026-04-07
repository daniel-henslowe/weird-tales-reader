#!/usr/bin/env python3
"""
AI-powered OCR cleanup for Weird Tales story text.
Uses 'claude --print' CLI — no separate API key needed.

Usage:
  python3 tools/ai_clean_ocr.py --file wt_1923_03.txt
  python3 tools/ai_clean_ocr.py --year 1923
  python3 tools/ai_clean_ocr.py --start-from wt_1930_01.txt   # resume
  python3 tools/ai_clean_ocr.py                               # all files
"""

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ISSUES_DIR = REPO_ROOT / "issues"
DIVIDER_RE = re.compile(r"^={10,}\s*$")

MAX_CHUNK_CHARS = 4000  # ~800 words — fewer round-trips, still reliable

SYSTEM_INSTRUCTION = (
    "Fix ONLY the OCR scan errors in this 1920s-1950s pulp horror magazine text. "
    "Rules: fix misread characters and garbled words; preserve original prose style "
    "and period vocabulary; keep all proper nouns unless clearly wrong; do NOT "
    "rewrite or change meaning; return ONLY the corrected text with no commentary."
)


def claude_fix(text: str, retries: int = 2) -> str:
    prompt = SYSTEM_INSTRUCTION + "\n\n" + text
    last_err = None
    for attempt in range(retries + 1):
        try:
            result = subprocess.run(
                ["claude", "--print", "--model", "haiku", prompt],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr[:300])
            out = result.stdout.strip()
            if len(out) < len(text) * 0.4:
                raise RuntimeError(f"Output suspiciously short ({len(out)} vs {len(text)} chars)")
            return out
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(3)
    raise last_err


def split_at_paragraphs(text: str) -> list[str]:
    paragraphs = re.split(r'\n\n+', text)
    chunks, current, current_len = [], [], 0
    for para in paragraphs:
        if current_len + len(para) > MAX_CHUNK_CHARS and current:
            chunks.append('\n\n'.join(current))
            current, current_len = [para], len(para)
        else:
            current.append(para)
            current_len += len(para)
    if current:
        chunks.append('\n\n'.join(current))
    return chunks


def find_sections(lines: list[str]) -> list[tuple[int, int]]:
    """Return (start_line, end_line) for each story body section."""
    dividers = [i for i, l in enumerate(lines) if DIVIDER_RE.match(l.strip())]
    if len(dividers) < 5:
        return []
    sections = []
    i = 4  # skip 4 leading dividers (header-start/end, toc-start/end)
    while i < len(dividers):
        start = dividers[i]
        if i + 1 < len(dividers) and dividers[i + 1] - start < 15:
            # title-block pair → content is after second divider
            content_start = dividers[i + 1] + 1
            content_end = dividers[i + 2] if i + 2 < len(dividers) else len(lines)
            sections.append((content_start, content_end))
            i += 2
        else:
            content_start = start + 1
            content_end = dividers[i + 1] if i + 1 < len(dividers) else len(lines)
            sections.append((content_start, content_end))
            i += 1
    return sections


def process_file(path: Path, dry_run: bool = False) -> bool:
    lines = path.read_text(encoding='utf-8').split('\n')
    sections = find_sections(lines)
    if not sections:
        print(f"  {path.name}: no sections, skipped")
        return False

    changed = False
    for idx, (start, end) in enumerate(sections):
        raw = '\n'.join(lines[start:end])
        words = len(raw.split())
        # Skip ads/very short sections and absurdly long ones
        if words < 80 or words > 8000:
            continue

        label = f"  {path.name} §{idx+1}/{len(sections)} ({words}w)"
        sys.stdout.write(label)
        sys.stdout.flush()

        if dry_run:
            print(" [dry-run]")
            continue

        chunks = split_at_paragraphs(raw)
        fixed_chunks = []
        ok = True
        for ci, chunk in enumerate(chunks):
            if len(chunks) > 1:
                sys.stdout.write(f" [{ci+1}/{len(chunks)}]")
                sys.stdout.flush()
            try:
                fixed_chunks.append(claude_fix(chunk))
                if ci < len(chunks) - 1:
                    time.sleep(1)
            except Exception as e:
                print(f" ERROR: {e}")
                ok = False
                break

        if not ok:
            continue

        fixed = '\n\n'.join(fixed_chunks)
        if fixed != raw:
            lines[start:end] = fixed.split('\n')
            changed = True
        print(" ✓")

    if changed and not dry_run:
        path.write_text('\n'.join(lines), encoding='utf-8')

    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file',       help='Single file (e.g. wt_1923_03.txt)')
    parser.add_argument('--year',       type=int)
    parser.add_argument('--start-from', help='Resume from this filename')
    parser.add_argument('--dry-run',    action='store_true')
    args = parser.parse_args()

    if args.file:
        files = [ISSUES_DIR / args.file]
    elif args.year:
        files = sorted(ISSUES_DIR.glob(f"wt_{args.year}_*.txt"))
    else:
        files = sorted(ISSUES_DIR.glob("wt_*.txt"))

    if args.start_from:
        files = [f for f in files if f.name >= args.start_from]
        print(f"Resuming from {args.start_from} ({len(files)} files remaining)")

    print(f"AI-cleaning {len(files)} file(s){'  [dry-run]' if args.dry_run else ''}...")
    changed = 0
    for f in files:
        if process_file(f, dry_run=args.dry_run):
            changed += 1

    print(f"\nDone — {changed}/{len(files)} files updated.")


if __name__ == "__main__":
    main()
