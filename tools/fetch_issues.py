#!/usr/bin/env python3
"""
Fetch Weird Tales issues from Internet Archive and convert to tales-reader format.

Usage:
  python3 tools/fetch_issues.py [options]

Options:
  --limit N         Stop after downloading N issues (default: all)
  --start-year Y    Only fetch issues from this year onwards (default: 1923)
  --end-year Y      Only fetch issues up to this year (default: 1954)
  --skip-existing   Skip issues already downloaded (default: True)
  --delay S         Seconds between requests (default: 1.5)

Output:
  issues/wt_YYYY_MM_vVVnNN.txt  — one file per issue in tales-reader format

Run build_manifest.py after this script to generate data/manifest.json.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ISSUES_DIR = REPO_ROOT / "issues"

IA_SEARCH_URL = (
    "https://archive.org/advancedsearch.php"
    "?q=collection%3Aweirdtalesmagazine"
    "&output=json"
    "&rows=600"
    "&fl=identifier,title,date,description"
    "&sort=date+asc"
)

IA_METADATA_URL = "https://archive.org/metadata/{identifier}"
IA_DOWNLOAD_URL = "https://archive.org/download/{identifier}/{filename}"

HEADERS = {
    "User-Agent": "weird-tales-reader/1.0 (educational archive project)",
}


# ─── HTTP helpers ────────────────────────────────────────────────────────────

def fetch_url(url, timeout=30):
    """Fetch URL and return bytes, or None on error."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {url}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  Error fetching {url}: {e}", file=sys.stderr)
        return None


def fetch_json(url):
    data = fetch_url(url)
    if data is None:
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


def fetch_text(url):
    data = fetch_url(url)
    if data is None:
        return None
    # Try UTF-8, fall back to latin-1 (OCR text from old scans)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


# ─── IA collection enumeration ───────────────────────────────────────────────

def get_all_identifiers(start_year, end_year):
    """Query IA search API and return list of candidate identifiers."""
    print("Fetching collection index from Internet Archive...")
    result = fetch_json(IA_SEARCH_URL)
    if not result:
        print("ERROR: Could not fetch collection index.", file=sys.stderr)
        return []

    docs = result.get("response", {}).get("docs", [])
    print(f"  Found {len(docs)} items in collection")

    candidates = []
    for doc in docs:
        identifier = doc.get("identifier", "")
        title = doc.get("title", "")
        date_str = doc.get("date", "") or ""
        description = doc.get("description", "") or ""

        # Parse year from date field
        year = None
        m = re.search(r"\b(19[2-5]\d)\b", date_str)
        if m:
            year = int(m.group(1))
        else:
            # Try from title or identifier
            m = re.search(r"\b(19[2-5]\d)\b", title + identifier)
            if m:
                year = int(m.group(1))

        if year is None or year < start_year or year > end_year:
            continue

        # Skip obvious non-issue items (compilations, author collections)
        lower_id = identifier.lower()
        skip_patterns = [
            "complete_archive", "complete-archive",
            "in_weird_tales", "in-weird-tales",
            "bat-men", "wellman", "compilation",
            "canadian", "british",
            "story_reproduction", "story-reproduction",
            "_novella", "_novel", "_selected",
        ]
        if any(p in lower_id for p in skip_patterns):
            continue

        candidates.append({
            "identifier": identifier,
            "title": title,
            "date_str": date_str,
            "year": year,
            "description": description,
        })

    print(f"  {len(candidates)} issues within {start_year}–{end_year}")
    return candidates


# ─── IA metadata & file discovery ────────────────────────────────────────────

def get_djvu_txt_filename(identifier):
    """Return the _djvu.txt filename for an identifier, or None."""
    url = IA_METADATA_URL.format(identifier=identifier)
    meta = fetch_json(url)
    if not meta:
        return None

    files = meta.get("files", [])
    for f in files:
        name = f.get("name", "")
        if name.endswith("_djvu.txt"):
            return name

    # Sometimes the file is named differently — look for any .txt that's not metadata
    for f in files:
        name = f.get("name", "")
        if name.endswith(".txt") and "_meta" not in name and "files.xml" not in name:
            return name

    return None


# ─── OCR text parsing ─────────────────────────────────────────────────────────

def clean_ocr_text(text):
    """Basic OCR cleanup: fix common artifacts, normalize whitespace."""
    # Remove form feed characters (page separators in djvu.txt)
    text = text.replace("\x0c", "\n\n")

    # Fix soft hyphens / line-break hyphens
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)

    # Remove null bytes
    text = text.replace("\x00", "")

    # Normalize Windows line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Collapse 3+ blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def find_contents_section(lines):
    """
    Find the TABLE OF CONTENTS block(s). Returns (start_idx, end_idx) or None.

    Weird Tales uses "Contents for March, 1923" with a "...—Continued" page.
    We capture both pages by returning the full range.
    """
    toc_start = None
    toc_end = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Look for any CONTENTS header
        if re.search(r"Contents\s+for\s+\w|\bCONTENTS\b|TABLE OF CONTENTS", stripped, re.IGNORECASE):
            if toc_start is None:
                toc_start = i
            # Continue past "Contents ... Continued" pages
            toc_end = min(i + 120, len(lines))
            continue

        # After we've started the TOC, look for end markers
        if toc_start is not None and toc_end is not None:
            # THE EYRIE or similar editorial section = end of TOC
            if re.match(r"THE EYRIE", stripped, re.IGNORECASE):
                toc_end = i
                break

    if toc_start is None:
        return None

    # Scan from toc_start to find the actual last TOC entry
    last_entry_line = toc_start
    for j in range(toc_start + 1, min(toc_start + 300, len(lines))):
        stripped = lines[j].strip()
        # Any line that looks like a TOC entry updates our end pointer
        parsed = parse_contents_line(stripped)
        if parsed:
            last_entry_line = j

    return toc_start, last_entry_line + 1


def parse_contents_line(line):
    """
    Parse a TOC line. Weird Tales uses dot-leader format:
      "The Mystery of Black Jean. Julian Roman 41"
      "The Ghoul and the Corpse..G. A. Wells 65"
      "The Dead Man's Tale.. Willard E. Hawkins"     (no page for novelettes)
      "Ooze . Anthony M. Rud"
      "7 · Title · Author · ss"                      (later reprints)
      "The Scar _Carl Rasmus 7"                       (OCR renders leaders as underscores)

    Returns dict with page, title, author, or None.
    """
    line = line.strip()
    if not line or len(line) < 5:
        return None

    # Skip descriptor lines and section headers
    descriptor_starts = (
        "A Thrilling", "A Short", "A Complete", "A Strange", "A Weird",
        "A Gripping", "A Frightful", "A Two-part", "A Grim", "An Odd",
        "An Amazing", "An Unusual", "An Uncommon", "A tale", "A story",
        "A queer", "A fantasy", "THREE", "TWO", "TWENTY", "SIXTEEN",
        "Also", "Edited", "Showing", "Craigie", "Don't",
    )
    if any(line.startswith(d) for d in descriptor_starts):
        return None

    # Skip lines that are just a page number
    if re.match(r"^\d{1,3}\s*$", line):
        return None

    # Format 1: dot-leader "Title[..] Author [page]"
    # e.g. "The Ghoul and the Corpse..G. A. Wells 65"
    # e.g. "Ooze . Anthony M. Rud"
    # Separator: 1-3 periods possibly with spaces, before an uppercase name
    m = re.match(
        r"^(.+?)\s*\.{1,3}\s*([A-Z][a-zA-Z][a-zA-Z\s\.\-\']{2,}?)(?:\s+(\d{1,3}))?\s*$",
        line
    )
    if m:
        title = clean_title(m.group(1))
        author = clean_author(m.group(2))
        page = int(m.group(3)) if m.group(3) else 0
        # Validate: title and author must be at least 3 chars, not all digits
        if len(title) >= 3 and len(author) >= 4 and not title.isdigit():
            return {"page": page, "title": title, "author": author, "type_code": ""}

    # Format 2: underscore-leader "Title _Author page" (OCR artifact)
    m = re.match(
        r"^(.+?)\s*_{2,}\s*([A-Z][a-zA-Z\s\.\-\']+?)(?:\s+(\d{1,3}))?\s*$",
        line
    )
    if m:
        title = clean_title(m.group(1))
        author = clean_author(m.group(2))
        page = int(m.group(3)) if m.group(3) else 0
        if len(title) >= 3 and len(author) >= 4:
            return {"page": page, "title": title, "author": author, "type_code": ""}

    # Format 3: middle-dot "7 · Title · Author [· type]"
    m = re.match(
        r"^(\d+)\s*[·•]\s*(.+?)\s*[·•]\s*(.+?)\s*(?:[·•]\s*\w+)?\s*$",
        line
    )
    if m:
        return {
            "page": int(m.group(1)),
            "title": clean_title(m.group(2)),
            "author": clean_author(m.group(3)),
            "type_code": "",
        }

    return None


def clean_title(s):
    s = s.strip().strip('"').strip("'").strip()
    # Remove trailing type codes like " · ss" or " (ss)"
    s = re.sub(r"\s*[·•]\s*(ss|nv|vi|nt|poem|verse)\s*$", "", s, flags=re.IGNORECASE)
    return s


def clean_author(s):
    s = s.strip()
    # Remove type codes accidentally included
    s = re.sub(r"\s*(ss|nv|vi|nt)\s*$", "", s, flags=re.IGNORECASE)
    return s.strip()


def extract_stories_from_contents(lines, toc_start, toc_end):
    """Parse story list from the TOC region."""
    stories = []
    for line in lines[toc_start:toc_end]:
        parsed = parse_contents_line(line)
        if parsed and len(parsed["title"]) > 2:
            stories.append(parsed)
    return stories


def find_story_boundaries(lines, stories):
    """
    Locate story sections in OCR text using "By [Author]" lines as anchors.

    In Weird Tales (1920s-50s), each story's heading looks like:
        THE DEAD MAN'S TALE          ← display title (all-caps, short line)
        By Willard E. Hawkins        ← author byline

    Strategy:
    1. Find all "By [Author]" bylines in the text.
    2. Match each byline to a known story from the TOC (by author name).
    3. Look backwards up to 8 lines to find the title line(s).
    4. Return (title_start, content_start, story_dict) tuples.

    Returns list of (start_line, end_line, story_dict) tuples.
    """
    if not stories:
        return []

    total_lines = len(lines)

    # Build a lookup of known authors → story
    author_to_story = {}
    for s in stories:
        key = normalize_name(s.get("author", ""))
        if key:
            author_to_story[key] = s

    # Find all "By [Author]" lines
    byline_pattern = re.compile(r"^\s*[Bb]y\s+([A-Z][a-zA-Z][a-zA-Z\s\.\-\']{2,})\s*$")
    found_bylines = []

    for i, line in enumerate(lines):
        m = byline_pattern.match(line)
        if not m:
            continue

        author_raw = m.group(1).strip()
        author_key = normalize_name(author_raw)

        # Match to known story
        story = author_to_story.get(author_key)
        if story is None:
            # Try partial match (last name only)
            last_name = author_key.split()[-1] if author_key.split() else ""
            for key, s in author_to_story.items():
                if last_name and last_name in key:
                    story = s
                    break

        if story:
            # Find title start — look back up to 8 lines for a short non-empty line
            title_start = i
            for back in range(1, 9):
                if i - back < 0:
                    break
                candidate = lines[i - back].strip()
                if candidate and len(candidate) < 80:
                    title_start = i - back
                    # Keep going back to catch multi-line titles
                elif candidate == "":
                    continue
                else:
                    break

            # Content starts after the byline
            content_start = i + 1

            found_bylines.append((title_start, content_start, story))

    if not found_bylines:
        return []

    # Sort by position, deduplicate (same author appearing twice → keep first occurrence
    # that's deep enough in the file, past the TOC)
    # Estimate where TOC ends (first 30% of file)
    toc_cutoff = total_lines // 5
    found_bylines = [(ts, cs, s) for ts, cs, s in found_bylines if ts > toc_cutoff]

    # Deduplicate by story title
    seen_titles = set()
    deduped = []
    for ts, cs, story in sorted(found_bylines, key=lambda x: x[0]):
        t = story["title"]
        if t not in seen_titles:
            seen_titles.add(t)
            deduped.append((ts, cs, story))

    result = []
    for k, (title_start, content_start, story) in enumerate(deduped):
        end = deduped[k + 1][0] if k + 1 < len(deduped) else total_lines
        result.append((title_start, end, story))

    return result


def normalize_name(name):
    """Normalize author name for fuzzy matching."""
    name = name.strip().lower()
    # Remove punctuation except spaces
    name = re.sub(r"[^a-z\s]", " ", name)
    # Collapse spaces
    name = re.sub(r"\s+", " ", name).strip()
    return name


def extract_issue_metadata(lines, identifier, ia_date):
    """Extract volume, issue number, date, editor from header text."""
    meta = {
        "identifier": identifier,
        "volume": "",
        "number": "",
        "date": ia_date or "",
        "editor": "",
        "cover_price": "",
    }

    header_text = "\n".join(lines[:500])

    # Volume/Number: "VOLUME 1 ... NUMBER 2" on the copyright page
    # Also handles "Vol. 1, No. 2" etc.
    m = re.search(r"VOLUME\s+(\d+)\b", header_text)
    n = re.search(r"NUMBER\s+(\d+)\b", header_text)
    if m and n:
        meta["volume"] = m.group(1)
        meta["number"] = n.group(1)
    else:
        m = re.search(r"[Vv]ol(?:ume)?\.?\s*(\d+)\D{1,10}[Nn]o\.?\s*(\d+)\b", header_text)
        if m:
            meta["volume"] = m.group(1)
            meta["number"] = m.group(2)
        else:
            # From identifier like WeirdTalesV01N011923 or Weird_Tales_v01n04_1923
            m = re.search(r"[Vv](\d{1,2})[Nn](\d{1,2})(?!\d)", identifier)
            if m:
                meta["volume"] = m.group(1).lstrip("0") or "1"
                meta["number"] = m.group(2).lstrip("0") or "1"

    # Editor
    m = re.search(r"[Ee]ditor[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)", header_text)
    if m:
        meta["editor"] = m.group(1)

    # Cover price
    m = re.search(r"(\d+[¢c]|\$[\d.]+)\s*(?:per|a)?\s*copy", header_text, re.IGNORECASE)
    if m:
        meta["cover_price"] = m.group(1).replace("c", "¢")

    return meta


# ─── Issue file writing ───────────────────────────────────────────────────────

DIVIDER = "=" * 60

def write_issue_file(filepath, meta, stories_content, full_text_lines):
    """
    Write a tales-reader formatted .txt file.

    Format:
      === (divider)
      Issue header (volume, number, date, editor, price)
      === (divider)
      Cover art (if found)
      === (divider)
      TABLE OF CONTENTS
      === (divider)
      === (story title divider)
      STORY TITLE
      by Author
      === (story title divider)
      story text
      ... repeating per story
    """
    lines_out = []

    # Header block
    lines_out.append(DIVIDER)
    lines_out.append(f"Weird Tales")
    lines_out.append(f"Volume {meta['volume']}, Number {meta['number']}")
    lines_out.append(f"Date: {meta['date']}")
    if meta.get("editor"):
        lines_out.append(f"Editor: {meta['editor']}")
    if meta.get("cover_price"):
        lines_out.append(f"Cover Price: {meta['cover_price']}")
    lines_out.append(DIVIDER)

    # Cover art placeholder (extracted later if possible)
    cover_art = extract_cover_art(full_text_lines)
    if cover_art:
        lines_out.append(f'Cover Art: "{cover_art["title"]}" by {cover_art["artist"]}')
    lines_out.append(DIVIDER)

    # Table of contents
    lines_out.append("TABLE OF CONTENTS")
    lines_out.append("")
    for i, (story, _) in enumerate(stories_content, 1):
        lines_out.append(f'  {i}. "{story["title"]}" by {story["author"]}')
    lines_out.append(DIVIDER)

    # Story sections
    for story, text_lines in stories_content:
        lines_out.append(DIVIDER)
        lines_out.append(story["title"].upper())
        if story.get("author"):
            lines_out.append(f'by {story["author"]}')
        lines_out.append(DIVIDER)
        lines_out.extend(format_story_lines(text_lines))
        lines_out.append("")
        lines_out.append("[THE END]")
        lines_out.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines_out))


def extract_cover_art(lines):
    """Try to find cover illustration credit."""
    for line in lines[:80]:
        # "Cover illustration by Artist Name" or "Cover by..."
        m = re.search(r"[Cc]over\s+(?:illustration|drawing|design|art)?\s*by\s+([A-Z][a-z].+?)[\.\n]", line)
        if m:
            return {"title": "Cover", "artist": m.group(1).strip()}
        # "Illustration from ... by ..."
        m = re.search(r'"(.+?)"\s+(?:by|from)\s+([A-Z][a-z][^\.]+)', line)
        if m:
            return {"title": m.group(1), "artist": m.group(2).strip()}
    return None


def format_story_lines(lines):
    """Clean and reflow story text lines."""
    out = []
    current_para = []

    for line in lines:
        stripped = line.strip()

        # Skip running headers (page numbers, magazine name)
        if re.match(r"^WEIRD TALES\s*$", stripped, re.IGNORECASE):
            continue
        if re.match(r"^\d+\s*$", stripped) and len(stripped) <= 4:
            continue
        if re.match(r"^WEIRD TALES\s+\d+\s*$", stripped, re.IGNORECASE):
            continue

        if stripped == "":
            if current_para:
                out.append(" ".join(current_para))
                current_para = []
            out.append("")
        else:
            current_para.append(stripped)

    if current_para:
        out.append(" ".join(current_para))

    return out


# ─── Parse date from IA metadata ─────────────────────────────────────────────

MONTHS = {
    "01": "January", "02": "February", "03": "March", "04": "April",
    "05": "May", "06": "June", "07": "July", "08": "August",
    "09": "September", "10": "October", "11": "November", "12": "December",
}

def parse_ia_date(date_str):
    """
    Convert IA date string to human-readable date and (year, month).
    Handles: "1923-03", "1923-03-01", "1923"
    """
    if not date_str:
        return "", None, None

    m = re.match(r"(\d{4})-(\d{2})", date_str)
    if m:
        year, month = int(m.group(1)), m.group(2)
        month_name = MONTHS.get(month, month)
        return f"{month_name} {year}", year, int(month)

    m = re.match(r"(\d{4})", date_str)
    if m:
        return m.group(1), int(m.group(1)), None

    return date_str, None, None


def make_slug(identifier, year, month):
    """Create a URL-safe slug for the issue."""
    # Prefer a clean slug based on date
    if year and month:
        return f"wt_{year}_{month:02d}"
    # Fall back to sanitized identifier
    slug = re.sub(r"[^a-z0-9_]", "_", identifier.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:60]


def make_filename(slug):
    return f"{slug}.txt"


# ─── Main fetch logic ─────────────────────────────────────────────────────────

def process_issue(candidate, delay, skip_existing):
    identifier = candidate["identifier"]
    date_str = candidate["date_str"]
    date_human, year, month = parse_ia_date(date_str)

    slug = make_slug(identifier, year, month)
    filename = make_filename(slug)
    filepath = ISSUES_DIR / filename

    if skip_existing and filepath.exists():
        print(f"  SKIP (exists): {filename}")
        return True

    print(f"  Fetching metadata: {identifier}")
    time.sleep(delay)

    djvu_filename = get_djvu_txt_filename(identifier)
    if not djvu_filename:
        print(f"  WARNING: No djvu.txt found for {identifier}")
        return False

    time.sleep(delay)

    txt_url = IA_DOWNLOAD_URL.format(identifier=identifier, filename=urllib.parse.quote(djvu_filename))
    print(f"  Downloading: {djvu_filename}")
    raw_text = fetch_text(txt_url)

    if not raw_text:
        print(f"  ERROR: Could not download full text for {identifier}")
        return False

    # Process
    text = clean_ocr_text(raw_text)
    lines = text.split("\n")

    meta = extract_issue_metadata(lines, identifier, date_human)
    if year:
        meta["year"] = year
    if month:
        meta["month"] = month

    # Find and parse the table of contents
    toc_bounds = find_contents_section(lines)
    stories = []
    if toc_bounds:
        toc_start, toc_end = toc_bounds
        stories = extract_stories_from_contents(lines, toc_start, toc_end)

    if not stories:
        print(f"  WARNING: No stories found in TOC for {identifier}")
        # Treat the whole text as one section
        stories_content = [
            ({"title": "Full Issue Text", "author": "", "page": 1}, lines)
        ]
    else:
        # Find story boundaries in the text
        boundaries = find_story_boundaries(lines, stories)

        if boundaries:
            stories_content = [
                (story, lines[start:end])
                for start, end, story in boundaries
            ]
        else:
            # Couldn't locate stories — use TOC list with full text as one block
            stories_content = [
                ({"title": s["title"], "author": s.get("author", ""), "page": s.get("page", 0)}, [])
                for s in stories
            ]
            # Put all text in first section
            if stories_content:
                stories_content[0] = (stories_content[0][0], lines)

    write_issue_file(filepath, meta, stories_content, lines)
    print(f"  Written: {filename} ({len(stories_content)} sections)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Fetch Weird Tales issues from Internet Archive")
    parser.add_argument("--limit", type=int, default=0, help="Max issues to download (0 = all)")
    parser.add_argument("--start-year", type=int, default=1923)
    parser.add_argument("--end-year", type=int, default=1954)
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument("--no-skip-existing", dest="skip_existing", action="store_false")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between requests")
    args = parser.parse_args()

    ISSUES_DIR.mkdir(parents=True, exist_ok=True)

    candidates = get_all_identifiers(args.start_year, args.end_year)

    if args.limit:
        candidates = candidates[:args.limit]

    print(f"\nProcessing {len(candidates)} issues...")
    success = 0
    failed = 0

    for i, candidate in enumerate(candidates, 1):
        print(f"\n[{i}/{len(candidates)}] {candidate['identifier']} ({candidate['year']})")
        try:
            ok = process_issue(candidate, args.delay, args.skip_existing)
            if ok:
                success += 1
            else:
                failed += 1
        except KeyboardInterrupt:
            print("\nInterrupted.")
            break
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            failed += 1

    print(f"\nDone: {success} succeeded, {failed} failed")
    print(f"Run 'python3 tools/build_manifest.py' to generate data/manifest.json")


# Add urllib.parse import needed for URL encoding
import urllib.parse

if __name__ == "__main__":
    main()
