#!/usr/bin/env python3
"""Drop daily-briefing digests into the Obsidian vault as per-day notes.

Sources, in priority order:
  1. weekly/YYYY-WNN.html — day-sections (data-date) with structured story
     cards. This is the live format the cloud trigger has produced since
     2026-04-19.
  2. archive/YYYY-MM-DD.html — legacy daily files (Mar–Apr 2026), converted
     with a generic text extraction, only for dates not covered by a weekly.

Each day becomes ~/Vault/03-Resources/AI-News/YYYY-MM-DD.md with:
  - frontmatter (type: digest, date, week, categories, high count)
  - "High signal" section (HIGH stories + key takeaways)
  - per-category story lists with source links
  - "Portfolio watch" — keyword-matched links to vault project notes,
    so news that should swing project/spec decisions surfaces next to
    the note where that decision lives.

Idempotent: existing notes are never overwritten EXCEPT today's and
yesterday's, which are regenerated (day-sections grow with UPDATE threads).

Vault Improvement Plan, Phase 4.1 (v2 — weekly-format aware).
"""

import datetime
import html as htmllib
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

REPO = Path.home() / "daily-briefing"
VAULT_FEED = Path.home() / "Vault" / "03-Resources" / "AI-News"

CATEGORY_NAMES = {
    "ai": "🧠 AI / Machine Learning",
    "apple": "🍎 Apple / iOS",
    "security": "🔒 Security",
    "dev": "🛠 Dev Tools",
    "business": "💼 Business",
    "hardware": "⚙️ Hardware",
    "oss": "🌐 Open Source",
    "policy": "🏛 Policy",
}

# keyword (regex, case-insensitive) -> vault notes whose decisions the story may swing
PORTFOLIO_WATCH = [
    (r"foundation models|apple intelligence|private cloud compute|core ml|afm\b",
     ["[[AFM3-PCC-impact-2026-06-10]]", "[[Clarity]]"]),
    (r"app store (?:polic|rule|fee|review|guideline)|app review",
     ["[[Apps MOC]]"]),
    (r"swiftui|swiftdata|xcode|ios \d\d|storekit",
     ["[[Apps MOC]]"]),
    (r"podcast|transcri|whisper|text.to.speech|\btts\b|elevenlabs",
     ["[[Podcast Pipeline Automation]]", "[[PodFlow SaaS]]"]),
    (r"\bclaude\b|anthropic|agent framework|claude code",
     ["[[Second-Me Harness]]"]),
    (r"instagram|tiktok|youtube api|social media api|fastapi",
     ["[[SocialFlow Pro]]"]),
    (r"gemma|ollama|open.weight|local llm|on.device model",
     ["[[Podcast Pipeline Automation]]", "[[AFM3-PCC-impact-2026-06-10]]"]),
]


def strip_tags(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", htmllib.unescape(text)).strip()


def parse_story_card(chunk: str) -> dict:
    head = re.search(r'<h4><a href="([^"]+)"[^>]*>(.*?)</a></h4>', chunk, re.S)
    analysis = re.search(r'class="story-analysis">(.*?)</p>', chunk, re.S)
    takeaway = re.search(r'class="key-takeaway">(.*?)</div>', chunk, re.S)
    importance = re.search(r'data-importance="(\w+)"', chunk)
    searchable = re.search(r'data-searchable="([^"]*)"', chunk)
    source = re.search(r'class="tag tag-source">(.*?)</span>', chunk, re.S)
    updates = [
        (strip_tags(d), strip_tags(t))
        for d, t in re.findall(
            r'class="update-date">(.*?)</div>\s*<p class="update-text">(.*?)</p>', chunk, re.S)
    ]
    return {
        "url": head.group(1) if head else "",
        "headline": strip_tags(head.group(2)) if head else "(no headline)",
        "analysis": strip_tags(analysis.group(1)) if analysis else "",
        "takeaway": strip_tags(takeaway.group(1)) if takeaway else "",
        "importance": importance.group(1) if importance else "medium",
        "searchable": searchable.group(1) if searchable else "",
        "source": strip_tags(source.group(1)) if source else "",
        "updates": updates,
    }


def parse_day_section(section: str) -> list:
    """Return [(category_id, category_label, [stories])]."""
    out = []
    cat_chunks = re.split(r'<div class="category cat-', section)[1:]
    for cc in cat_chunks:
        cat_id = re.match(r"(\w+)", cc).group(1)
        label_m = re.search(r"<h3>(.*?)</h3>", cc, re.S)
        label = strip_tags(label_m.group(1)) if label_m else CATEGORY_NAMES.get(cat_id, cat_id)
        stories = [parse_story_card(sc) for sc in re.split(r'<div class="story-card"', cc)[1:]]
        out.append((cat_id, label, stories))
    return out


def portfolio_watch(stories: list) -> dict:
    hits = {}
    for s in stories:
        haystack = f"{s['headline']} {s['searchable']} {s['analysis']}".lower()
        for pattern, notes in PORTFOLIO_WATCH:
            if re.search(pattern, haystack):
                for n in notes:
                    hits.setdefault(n, []).append(s["headline"])
    return hits


def render_day(date: str, week: str, source_file: str, categories: list) -> str:
    all_stories = [s for _, _, stories in categories for s in stories]
    high = [s for s in all_stories if s["importance"] == "high"]
    watch = portfolio_watch(all_stories)

    lines = [
        "---",
        "type: digest",
        f"date: {date}",
        f"week: \"{week}\"",
        f"source: {source_file}",
        f"categories: [{', '.join(c for c, _, _ in categories)}]",
        f"stories: {len(all_stories)}",
        f"high: {len(high)}",
        "---",
        "",
        f"# Tech Briefing — {date}",
        "",
    ]
    if high:
        lines.append("## 🔥 High signal")
        lines.append("")
        for s in high:
            lines.append(f"- **[{s['headline']}]({s['url']})** ({s['source']})")
            if s["analysis"]:
                lines.append(f"  {s['analysis']}")
            if s["takeaway"]:
                lines.append(f"  > {s['takeaway']}")
        lines.append("")
    if watch:
        lines.append("## 🎯 Portfolio watch")
        lines.append("")
        for note, headlines in watch.items():
            lines.append(f"- {note}:")
            for h in sorted(set(headlines)):
                lines.append(f"  - {h}")
        lines.append("")
    for _, label, stories in categories:
        if not stories:
            continue
        lines.append(f"## {label}")
        lines.append("")
        for s in stories:
            tag = "" if s["importance"] != "low" else " ·low·"
            lines.append(f"- [{s['headline']}]({s['url']}) — {s['source']}{tag}")
            if s["importance"] != "low" and s["analysis"]:
                lines.append(f"  {s['analysis']}")
            for ud, ut in s["updates"]:
                lines.append(f"  - **{ud}:** {ut}")
        lines.append("")
    lines += ["## Links", "- [[AI News MOC]]", ""]
    return "\n".join(lines)


# Legacy generic extraction for archive/*.html dailies
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


def convert_legacy(html_path: Path) -> str:
    p = TextExtract()
    p.feed(html_path.read_text(encoding="utf-8", errors="replace"))
    return re.sub(r"\n{3,}", "\n\n", "".join(p.parts)).strip()


def main():
    backfill = "--all" in sys.argv
    today = datetime.date.today()
    refresh = {str(today), str(today - datetime.timedelta(days=1))}
    cutoff = today - datetime.timedelta(days=10)
    VAULT_FEED.mkdir(parents=True, exist_ok=True)
    created, covered = 0, set()

    for weekly in sorted((REPO / "weekly").glob("*.html")):
        week = weekly.stem
        html = weekly.read_text(encoding="utf-8", errors="replace")
        sections = re.split(r'<div class="day-section" data-date="', html)[1:]
        for sec in sections:
            date = re.match(r"([0-9]{4}-[0-9]{2}-[0-9]{2})", sec).group(1)
            covered.add(date)
            if not backfill and datetime.date.fromisoformat(date) < cutoff:
                continue
            note = VAULT_FEED / f"{date}.md"
            if note.exists() and date not in refresh:
                continue
            body = render_day(date, week, f"weekly/{weekly.name}", parse_day_section(sec))
            if note.exists() and note.read_text() == body:
                continue
            note.write_text(body, encoding="utf-8")
            created += 1
            print(f"wrote {note.name} (from {weekly.name})")

    for daily in sorted((REPO / "archive").glob("*.html")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})$", daily.stem)
        if not m or m.group(1) in covered:
            continue
        date = m.group(1)
        if not backfill and datetime.date.fromisoformat(date) < cutoff:
            continue
        note = VAULT_FEED / f"{date}.md"
        if note.exists():
            continue
        note.write_text(
            "---\n"
            "type: digest\n"
            f"date: {date}\n"
            f"source: archive/{daily.name}\n"
            "legacy: true\n"
            "---\n\n"
            f"# Tech Briefing — {date}\n\n"
            f"{convert_legacy(daily)}\n\n"
            "## Links\n- [[AI News MOC]]\n",
            encoding="utf-8",
        )
        created += 1
        print(f"wrote {note.name} (legacy)")

    print(f"vault-drop: {created} note(s) written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
