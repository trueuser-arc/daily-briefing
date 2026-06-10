#!/usr/bin/env python3
"""Drop daily-briefing digests into the Obsidian vault.

For each archive/YYYY-MM-DD*.html newer than CUTOFF_DAYS with no matching
vault note, extracts readable text and writes
~/Vault/03-Resources/AI-News/<stem>.md with frontmatter and a link to the
AI News MOC. Called at the start of auto-push.sh; safe to run any time.

Vault Improvement Plan, Phase 4.1.
"""

import datetime
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ARCHIVE = Path.home() / "daily-briefing" / "archive"
VAULT_FEED = Path.home() / "Vault" / "03-Resources" / "AI-News"
CUTOFF_DAYS = 7  # only convert recent digests; use --all to backfill


class TextExtract(HTMLParser):
    SKIP = {"script", "style"}
    BLOCK = {"h1", "h2", "h3", "h4", "p", "li", "div", "section", "article"}

    def __init__(self):
        super().__init__()
        self.parts, self._skip, self._tag = [], 0, None

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        self._tag = tag

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        text = data.strip()
        if not text:
            return
        if self._tag in {"h1", "h2", "h3", "h4"}:
            self.parts.append(f"\n## {text}\n")
        elif self._tag == "li":
            self.parts.append(f"- {text}\n")
        else:
            self.parts.append(text + " ")


def convert(html_path: Path) -> str:
    p = TextExtract()
    p.feed(html_path.read_text(encoding="utf-8", errors="replace"))
    text = "".join(p.parts)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def main():
    backfill = "--all" in sys.argv
    cutoff = datetime.date.today() - datetime.timedelta(days=CUTOFF_DAYS)
    VAULT_FEED.mkdir(parents=True, exist_ok=True)
    created = 0
    for html in sorted(ARCHIVE.glob("*.html")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", html.stem)
        date = datetime.date.fromisoformat(m.group(1)) if m else None
        if not backfill and (date is None or date < cutoff):
            continue
        note = VAULT_FEED / f"{html.stem}.md"
        if note.exists():
            continue
        body = convert(html)
        note.write_text(
            "---\n"
            f"type: digest\n"
            f"date: {date or ''}\n"
            f"source: daily-briefing/archive/{html.name}\n"
            "---\n\n"
            f"# Briefing {html.stem}\n\n"
            f"{body}\n\n"
            "## Links\n- [[AI News MOC]]\n",
            encoding="utf-8",
        )
        created += 1
        print(f"created {note.name}")
    print(f"vault-drop: {created} new digest note(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
