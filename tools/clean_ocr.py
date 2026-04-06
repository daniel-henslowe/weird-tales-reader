#!/usr/bin/env python3
"""
Clean OCR artifacts from wt_*.txt story files.

Handles:
  1. Soft-hyphen line rejoins  (word¬ rest → wordrest)
  2. Drop-cap OCR split         (T HE → THE at paragraph start)
  3. Inline page-break junk     (mid-story author credits, running headers)
  4. Stray noise characters     (¬ alone, • used as apostrophe, etc.)
  5. Common high-confidence OCR substitutions inside story bodies

Usage:
  python3 tools/clean_ocr.py [--dry-run] [--file wt_1923_03.txt]
"""

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ISSUES_DIR = REPO_ROOT / "issues"

DIVIDER_RE = re.compile(r"^={10,}\s*$")


# ---------------------------------------------------------------------------
# Section-level cleaning (applied to story content only, not header/TOC)
# ---------------------------------------------------------------------------

# Common OCR substitutions that are safe to apply globally.
# Format: (pattern, replacement, flags)
SUBSTITUTIONS = [
    # --- Soft hyphen: rejoin split words ---
    # "re¬\n treat" or "re¬ treat" → "retreat"
    (r'(\w)¬[ \t]*\n[ \t]*(\w)', r'\1\2', re.MULTILINE),
    (r'(\w)¬ (\w)',               r'\1\2', 0),
    # Any remaining stray ¬ → hyphen
    (r'¬',                        r'-',    0),

    # --- Apostrophe / quote substitutions ---
    # • used as apostrophe:  "don•t" → "don't",  "it•s" → "it's"
    (r'(\w)•(\w)',  r"\1'\2", 0),
    # * used as apostrophe in obvious contractions
    (r"(\w)\*s\b",  r"\1's",  0),
    (r"(\w)\*t\b",  r"\1't",  0),
    (r"(\w)\*ll\b", r"\1'll", 0),
    (r"(\w)\*ve\b", r"\1've", 0),
    (r"(\w)\*d\b",  r"\1'd",  0),
    (r"(\w)\*re\b", r"\1're", 0),

    # --- High-confidence whole-word OCR substitutions only ---
    # Only include words with no legitimate alternate meaning.
    (r'\bnnd\b',  'and', 0),   # very common OCR for "and"
    (r'\btlie\b', 'the', 0),   # "tlie" → "the"
    (r'\bthc\b',  'the', 0),   # "thc" → "the"

    # --- Spacing / punctuation ---
    # Multiple spaces → single space
    (r'  +', ' ', 0),
    # Trailing space before punctuation
    (r' ([,\.;:!?])', r'\1', 0),
]

# Lines that look like mid-story running headers / page numbers / bylines
# and should be removed entirely.
JUNK_LINE_RE = re.compile(
    r'^('
    r'\d+\s*$'                         # bare page numbers
    r'|[A-Z][A-Z\s\.\-]{8,}$'         # ALL-CAPS lines (running titles)
    r'|By [A-Z][a-z]+ [A-Z][\.\s][A-Z][a-z]+'  # "By Author Name" mid-story
    r')\s*$'
)

# Drop-cap artifact: a lone uppercase letter followed by space + uppercase word
# at the start of a paragraph.  "T HE CASTLE" → "THE CASTLE"
DROP_CAP_RE = re.compile(r'^([A-Z]) ([A-Z]{2,})', re.MULTILINE)


def clean_section_text(text: str) -> str:
    """Apply OCR fixes to the body text of a single section."""

    # 1. Soft-hyphen & high-confidence substitutions
    for pattern, repl, flags in SUBSTITUTIONS:
        text = re.sub(pattern, repl, text, flags=flags)

    # 2. Drop-cap fix: "T HE" → "THE" (only at start of line)
    text = DROP_CAP_RE.sub(lambda m: m.group(1) + m.group(2), text)

    # 3. Remove obvious mid-story junk lines (running headers, lone page nums)
    cleaned_lines = []
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped and JUNK_LINE_RE.match(stripped):
            continue  # drop the line
        cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)

    return text


# ---------------------------------------------------------------------------
# File-level processing: preserve structure, only clean story bodies
# ---------------------------------------------------------------------------

def process_file(path: Path, dry_run: bool = False) -> tuple[int, int]:
    """
    Clean one issue file.  Returns (original_len, new_len).
    """
    content = path.read_text(encoding='utf-8')
    lines = content.split('\n')

    dividers = [i for i, l in enumerate(lines) if DIVIDER_RE.match(l.strip())]

    if len(dividers) < 4:
        return len(content), len(content)

    # Identify the start of story content (after the 4 leading dividers)
    story_start_line = dividers[3] + 1

    # Join the header+TOC portion unchanged
    header_part = '\n'.join(lines[:story_start_line])
    story_part  = '\n'.join(lines[story_start_line:])

    cleaned_story = clean_section_text(story_part)
    new_content = header_part + '\n' + cleaned_story

    if not dry_run and new_content != content:
        path.write_text(new_content, encoding='utf-8')

    return len(content), len(new_content)


def main():
    parser = argparse.ArgumentParser(description="Clean OCR artifacts in Weird Tales issue files")
    parser.add_argument('--dry-run', action='store_true', help="Don't write changes")
    parser.add_argument('--file', help="Process a single file by name (e.g. wt_1923_03.txt)")
    args = parser.parse_args()

    if args.file:
        files = [ISSUES_DIR / args.file]
    else:
        files = sorted(ISSUES_DIR.glob("wt_*.txt"))

    total_orig = total_new = changed = 0
    for f in files:
        orig, new = process_file(f, dry_run=args.dry_run)
        total_orig += orig
        total_new  += new
        if orig != new:
            changed += 1
            if args.file:
                print(f"  {f.name}: {orig} → {new} chars ({orig - new:+d})")

    action = "Would change" if args.dry_run else "Changed"
    print(f"{action} {changed}/{len(files)} files  "
          f"({total_orig:,} → {total_new:,} chars, -{total_orig - total_new:,} removed)")


if __name__ == "__main__":
    main()
