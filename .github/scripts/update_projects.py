"""Rebuild the project table in profile/README.md from the org's public repositories.

Usage:
  python .github/scripts/update_projects.py            # fetch and rewrite the README
  python .github/scripts/update_projects.py --self-test
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ORG = "The-Pulse-Engine"
README = Path(__file__).resolve().parents[2] / "profile" / "README.md"
START, END = "<!-- projects:start -->", "<!-- projects:end -->"
SKIP = {".github"}
ACTIVE_DAYS = 30
BADGE = "https://img.shields.io/badge/-{label}-{color}?style=flat-square"
SHIELD = "https://img.shields.io/github/{kind}/{org}/{repo}?style=flat-square&label=&color=2A2A2A"


def fetch_repos():
    req = urllib.request.Request(
        f"https://api.github.com/orgs/{ORG}/repos?type=public&per_page=100",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "pulseengine-profile"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def status(repo, now):
    if repo.get("archived"):
        return BADGE.format(label="Archived", color="888888"), "Archived"
    pushed = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))
    if now - pushed <= timedelta(days=ACTIVE_DAYS):
        return BADGE.format(label="Active", color="E8760A"), "Active"
    return BADGE.format(label="Quiet", color="C4C0B8"), "Quiet"


def cell(text):
    # A pipe or newline in a description would break the table row.
    return re.sub(r"\s+", " ", text or "").replace("|", "\\|").strip()


def render(repos, now):
    rows = [r for r in repos if r["name"] not in SKIP and not r.get("fork") and not r.get("private")]
    rows.sort(key=lambda r: r["pushed_at"], reverse=True)
    rows.sort(key=lambda r: bool(r.get("archived")))  # stable sort: archived repos go last
    if not rows:
        return "No public projects yet. Ask in the Discord to see what is in progress."
    out = [
        "| Project | What it does | Language | Stars | Last commit | Status |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        name = r["name"]
        badge, label = status(r, now)
        out.append(
            f"| [**{cell(name)}**]({r['html_url']}) "
            f"| {cell(r.get('description')) or 'Description coming soon.'} "
            f"| {cell(r.get('language')) or 'Mixed'} "
            f"| ![Stars]({SHIELD.format(kind='stars', org=ORG, repo=name)}) "
            f"| ![Last commit]({SHIELD.format(kind='last-commit', org=ORG, repo=name)}) "
            f"| ![{label}]({badge}) |"
        )
    out.append("")
    out.append("<sub>Updated daily from our public repositories.</sub>")
    return "\n".join(out)


def replace_block(text, block):
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        raise SystemExit(f"Markers {START} and {END} are missing from {README}")
    return pattern.sub(lambda _: f"{START}\n{block}\n{END}", text, count=1)


def self_test():
    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    repos = [
        {"name": ".github", "html_url": "u0", "pushed_at": "2026-11-22T00:00:00Z"},
        {"name": "Old", "html_url": "u1", "pushed_at": "2026-01-01T00:00:00Z", "description": "a | b\nc", "language": None},
        {"name": "New", "html_url": "u2", "pushed_at": "2026-11-20T00:00:00Z", "description": None, "language": "Go"},
        {"name": "Gone", "html_url": "u3", "pushed_at": "2026-11-21T00:00:00Z", "archived": True},
        {"name": "Fork", "html_url": "u4", "pushed_at": "2026-11-21T00:00:00Z", "fork": True},
    ]
    table = render(repos, now)
    lines = [l for l in table.splitlines() if l.startswith("| [")]
    assert [l.split("**")[1] for l in lines] == ["New", "Old", "Gone"], lines
    assert "-Active-" in lines[0] and "-Quiet-" in lines[1] and "-Archived-" in lines[2]
    assert "a \\| b c" in lines[1] and "| Mixed |" in lines[1]
    assert "Description coming soon." in lines[0]
    assert "Updated daily" in table
    assert "No public projects yet" in render([], now)
    doc = f"top\n{START}\nold\n{END}\nbottom"
    new = replace_block(doc, "X")
    assert new == f"top\n{START}\nX\n{END}\nbottom"
    assert replace_block(new, "X") == new
    print("self-test passed")


def main():
    if "--self-test" in sys.argv:
        return self_test()
    text = README.read_text(encoding="utf-8")
    new = replace_block(text, render(fetch_repos(), datetime.now(timezone.utc)))
    if new != text:
        README.write_text(new, encoding="utf-8", newline="\n")
        print("README updated")
    else:
        print("README already current")


if __name__ == "__main__":
    main()
