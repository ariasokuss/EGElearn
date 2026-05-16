#!/usr/bin/env python3
"""Insert S3 placeholder image links after every [DIAGRAM: ...] block in lesson files."""

import re
from pathlib import Path

S3_URL = "https://nls3-570515227065-eu-north-1-an.s3.eu-north-1.amazonaws.com/diagrams/placeholder.jpg"
IMAGE_LINE = f"![Diagram]({S3_URL})"

LESSONS_DIR = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "A-Level"
    / "Edexcel A-Level Economics"
    / "lessons"
)

# Match [DIAGRAM: ...] followed by newline, but NOT already followed by ![Diagram]
PATTERN = re.compile(r"(\[DIAGRAM:[^\]]+\])\n(?!\!\[Diagram\])")

total_insertions = 0
files_modified = 0

for md_file in sorted(LESSONS_DIR.glob("*.md")):
    content = md_file.read_text(encoding="utf-8")
    new_content, count = PATTERN.subn(rf"\1\n{IMAGE_LINE}\n", content)
    if count > 0:
        md_file.write_text(new_content, encoding="utf-8")
        print(f"  {md_file.name}: {count} insertion(s)")
        total_insertions += count
        files_modified += 1

print(f"\nDone: {total_insertions} insertions across {files_modified} files.")
