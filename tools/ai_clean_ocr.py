#!/usr/bin/env python3
"""
AI-powered OCR cleanup for Weird Tales story text.
Uses Claude API to fix character-level OCR errors in story bodies.

Usage:
  python3 tools/ai_clean_ocr.py                     # all issues
  python3 tools/ai_clean_ocr.py --file wt_1923_03.txt
  python3 tools/ai_clean_ocr.py --year 1923
  python3 tools/ai_clean_ocr.py --dry-run --file wt_1923_03.txt

Requires: pip install anthropic
API key:  export ANTHROPIC_API_KEY=...
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
ISSUES_DIR = REPO_ROOT / "issues"
DIVIDER_RE = re.compile(r"^={10,}\s*$")

# Maximum chars per API call (~4000 tokens ≈ 16000 chars)
CHUNK_SIZE = 12000

SYSTEM_PROMPT = """You are a proofreader correcting OCR errors in scanned pulp magazine stories from the 1920s–1950s.

Rules:
- Fix OCR errors: misread characters, garbled words, broken ligatures, split words
- Preserve the original prose style, vocabulary, and period-appropriate phrasing
- Keep all proper nouns exactly as they appear unless clearly wrong
- Do NOT rewrite, summarize, or change the meaning
- Do NOT add or remove sentences
- Return ONLY the corrected text — no commentary, no markdown, no explanation
- If a word is unrecognizable and you cannot determine the original, leave it as-is"""

def clean_chunk(client: anthropic.Anthropic, chunk: str) -> str:
    """Send one chunk of story text to Claude for OCR cleanup."""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": chunk}]
    )
    return msg.content[0].text


def split_into_chunks(text: str, max_size: int = CHUNK_SIZE) -> list[str]:
    """Split text into chunks at paragraph boundaries."""
    paragraphs = text.split('\n\n')
    chunks = []
    current = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > max_size and current:
            chunks.append('\n\n'.join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para)

    if current:
        chunks.append('\n\n'.join(current))

    return chunks


def process_file(path: Path, client: anthropic.Anthropic, dry_run: bool = False) -> bool:
    """Clean one issue file. Returns True if changed."""
    content = path.read_text(encoding='utf-8')
    lines = content.split('\n')

    dividers = [i for i, l in enumerate(lines) if DIVIDER_RE.match(l.strip())]
    if len(dividers) < 4:
        print(f"  {path.name}: skipped (not enough dividers)")
        return False

    # Split header+TOC (preserve) from story body (clean)
    story_start = dividers[3] + 1
    header_part = '\n'.join(lines[:story_start])
    story_part  = '\n'.join(lines[story_start:])

    # Process in chunks to stay within API limits
    chunks = split_into_chunks(story_part)
    cleaned_chunks = []

    for i, chunk in enumerate(chunks):
        sys.stdout.write(f"\r  {path.name}: chunk {i+1}/{len(chunks)} ...    ")
        sys.stdout.flush()

        if dry_run:
            cleaned_chunks.append(chunk)
        else:
            try:
                cleaned = clean_chunk(client, chunk)
                cleaned_chunks.append(cleaned)
                time.sleep(0.3)  # rate limit buffer
            except anthropic.RateLimitError:
                print(f"\n  Rate limited — waiting 60s...")
                time.sleep(60)
                cleaned = clean_chunk(client, chunk)
                cleaned_chunks.append(cleaned)

    cleaned_story = '\n\n'.join(cleaned_chunks)
    new_content = header_part + '\n' + cleaned_story

    if not dry_run and new_content != content:
        path.write_text(new_content, encoding='utf-8')
        print(f"\r  {path.name}: done ({len(content):,} → {len(new_content):,} chars)")
        return True

    print(f"\r  {path.name}: {'dry-run OK' if dry_run else 'unchanged'}")
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file',    help='Single file to process (e.g. wt_1923_03.txt)')
    parser.add_argument('--year',    type=int, help='Only process issues from this year')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    if args.file:
        files = [ISSUES_DIR / args.file]
    elif args.year:
        files = sorted(ISSUES_DIR.glob(f"wt_{args.year}_*.txt"))
    else:
        files = sorted(ISSUES_DIR.glob("wt_*.txt"))

    print(f"Processing {len(files)} files {'(dry-run)' if args.dry_run else ''}...")
    changed = 0
    for f in files:
        if process_file(f, client, dry_run=args.dry_run):
            changed += 1

    print(f"\nDone: {changed}/{len(files)} files updated")


if __name__ == "__main__":
    main()
