#!/usr/bin/env python3
"""
Parse all issues/*.txt files and generate data/manifest.json.

Usage:
  python3 tools/build_manifest.py
"""

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ISSUES_DIR = REPO_ROOT / "issues"
OUTPUT = REPO_ROOT / "data" / "manifest.json"

MONTHS_ABBR = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

DIVIDER_RE = re.compile(r"^={10,}\s*$")


def find_dividers(lines):
    return [i for i, l in enumerate(lines) if DIVIDER_RE.match(l.strip())]


def parse_header(lines):
    info = {}
    for line in lines:
        line = line.strip()
        m = re.match(r"Volume\s+(\d+),\s+Number\s+(\d+)", line)
        if m:
            info["volume"] = m.group(1)
            info["issue_number"] = m.group(2)
        m = re.match(r"Date:\s*(.+)", line)
        if m:
            info["date"] = m.group(1).strip()
        m = re.match(r"Editor:\s*(.+)", line)
        if m:
            info["editor"] = m.group(1).strip()
        m = re.match(r"Cover Price:\s*(.+)", line)
        if m:
            info["cover_price"] = m.group(1).strip()
    return info


def parse_cover_art(lines):
    for line in lines:
        line = line.strip()
        m = re.match(r'Cover Art:\s*"(.+?)"\s*by\s*(.+)', line)
        if m:
            return {"title": m.group(1), "artist": m.group(2).strip()}
    return None


def parse_toc(lines):
    stories = []
    for line in lines:
        stripped = line.strip()
        # Match: N. "Title" by Author  (author may be absent)
        m = re.match(r'\d+\.\s+"(.+?)"(?:\s+by\s+(.*))?$', stripped)
        if m:
            title = m.group(1).strip()
            author = (m.group(2) or '').strip()
            # Skip placeholder TOC entries
            if title.lower() in ('full issue text',):
                continue
            stories.append({"title": title, "author": author})
    return stories


def date_sort_key(issue):
    """Return (year, month) tuple for sorting."""
    date = issue.get("date", "")
    year_m = re.search(r"\b(\d{4})\b", date)
    year = int(year_m.group(1)) if year_m else 9999
    month = 0
    for name, num in MONTHS_ABBR.items():
        if name in date:
            month = num
            break
    return (year, month)


def parse_issue(filepath):
    fname = os.path.basename(filepath)

    with open(filepath, "r", encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f.readlines()]

    dividers = find_dividers(lines)
    if len(dividers) < 3:
        print(f"WARNING: not enough dividers in {fname}", file=sys.stderr)
        return None

    header = parse_header(lines[dividers[0] + 1:dividers[1]])
    cover_art = parse_cover_art(lines[dividers[1] + 1:dividers[2]])
    toc_end = dividers[3] if len(dividers) > 3 else len(lines)
    stories = parse_toc(lines[dividers[2] + 1:toc_end])

    date = header.get("date", "")
    year_m = re.search(r"\b(\d{4})\b", date)
    year = int(year_m.group(1)) if year_m else 0

    volume = header.get("volume", "")
    issue_num = header.get("issue_number", "")

    # Derive slug from filename (strip .txt)
    slug = fname.replace(".txt", "")

    issue = {
        "slug": slug,
        "filename": fname,
        "volume": volume,
        "number": issue_num,
        "date": date,
        "year": year,
        "editor": header.get("editor", ""),
        "cover_price": header.get("cover_price", ""),
        "cover_art": cover_art,
        "stories": stories,
        "story_count": len(stories),
    }
    return issue


def main():
    # Only process clean wt_*.txt files; the weird_tales_v_*.txt files are raw
    # OCR dumps (often garbled) and are excluded until manually cleaned up.
    files = sorted(ISSUES_DIR.glob("wt_*.txt"))
    if not files:
        print(f"ERROR: No .txt files found in {ISSUES_DIR}", file=sys.stderr)
        sys.exit(1)

    issues = []
    for f in files:
        issue = parse_issue(f)
        if issue:
            issues.append(issue)

    # Sort by date
    issues.sort(key=date_sort_key)

    years = sorted(set(i["year"] for i in issues if i["year"] > 0))

    manifest = {
        "title": "Weird Tales — The Unique Magazine",
        "total_issues": len(issues),
        "years": years,
        "issues": issues,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"Generated {OUTPUT} with {len(issues)} issues")
    for issue in issues:
        print(f"  Vol.{issue['volume']} No.{issue['number']} — {issue['date']} — {issue['story_count']} stories")


if __name__ == "__main__":
    main()
