"""Keep the Discord commission board in sync with open issues on the org's active projects.

A project is active while its repository is public, not archived, not a fork and not a template.
Its close date is the latest due date among its open milestones.

Usage:
  python .github/scripts/commission_board.py                # edit the board message
  python .github/scripts/commission_board.py --staff-check  # also warn staff if fewer than 2 are open
  python .github/scripts/commission_board.py --self-test

Environment:
  DISCORD_BOARD_WEBHOOK  webhook in #commission-board (required)
  BOARD_MESSAGE_ID       the board message to edit; when empty, one is posted and its ID printed
  DISCORD_STAFF_WEBHOOK  webhook in #moderator-only (only for --staff-check)
  GITHUB_TOKEN           optional, raises the GitHub API rate limit
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ORG = "The-Pulse-Engine"
SKIP = {".github"}
MIN_OPEN = 2
COLOR = 0xE8760A
MAX_LINES = 12  # per card; keeps three cards well under Discord's 6000-character embed total
DIFFICULTY = {"easy": 0, "good first issue": 0, "medium": 1, "hard": 2}
UA = "DiscordBot (https://github.com/The-Pulse-Engine/.github, 1.0)"
HEADER = (
    "## Commission board\n"
    "Pick an open issue and comment on it to claim it. A maintainer assigns it to you, "
    "and your PR has to land before the project closes. Stuck? Ask in <#1573932790813163531>.\n"
    "-# Updated <t:{now}:R>"
)


def request(url, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": UA, **(headers or {})})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for attempt in (1, 2):  # one retry for a transient error, then fail
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code in (404, 400, 401, 403) or attempt == 2:
                raise
        except urllib.error.URLError:
            if attempt == 2:
                raise
        time.sleep(5)


def github(path):
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return request(f"https://api.github.com{path}", headers=headers)


def active(repos):
    keep = [
        r for r in repos
        if r["name"] not in SKIP
        and not (r.get("archived") or r.get("fork") or r.get("private") or r.get("is_template"))
    ]
    return sorted(keep, key=lambda r: r["name"].lower())


def fetch():
    projects = []
    for repo in active(github(f"/orgs/{ORG}/repos?type=public&per_page=100")):
        name = repo["name"]
        issues = [i for i in github(f"/repos/{ORG}/{name}/issues?state=open&per_page=100") if "pull_request" not in i]
        milestones = github(f"/repos/{ORG}/{name}/milestones?state=open&sort=due_on&direction=asc")
        due = max((m["due_on"] for m in milestones if m.get("due_on")), default=None)  # the last milestone is the close date
        projects.append({"repo": repo, "issues": issues, "due": due})
    return projects


def unix(stamp):
    return int(datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp())


def issue_line(issue):
    labels = [l["name"].lower() for l in issue.get("labels", [])]
    level = next((l for l in ("easy", "medium", "hard") if l in labels), None)
    if "good first issue" in labels:
        level = "first issue"
    title = issue["title"].replace("[", "(").replace("]", ")")
    if len(title) > 90:
        title = title[:87].rstrip() + "..."
    tag = f"`{level}` " if level else ""
    who = issue.get("assignees") or []
    claim = " - claimed by " + ", ".join(a["login"] for a in who) if who else ""
    return f"{tag}[#{issue['number']} {title}]({issue['html_url']}){claim}"


def sort_key(issue):
    labels = [l["name"].lower() for l in issue.get("labels", [])]
    rank = min((DIFFICULTY[l] for l in labels if l in DIFFICULTY), default=3)
    return (bool(issue.get("assignees")), rank, issue["number"])


def card(project):
    repo, issues, due = project["repo"], sorted(project["issues"], key=sort_key), project["due"]
    lines = [repo.get("description") or "", ""]
    if due:
        lines.append(f"**Closes <t:{unix(due)}:R>** (<t:{unix(due)}:D>)")
    else:
        lines.append("No close date yet.")
    lines.append("")
    if issues:
        open_count = sum(1 for i in issues if not i.get("assignees"))
        lines.append(f"**{open_count} of {len(issues)} open to claim**")
        lines += [issue_line(i) for i in issues[:MAX_LINES]]
        if len(issues) > MAX_LINES:
            lines.append(f"+{len(issues) - MAX_LINES} more [on GitHub]({repo['html_url']}/issues)")
    else:
        lines.append("No open issues yet. New ones are on the way.")
    text = "\n".join(lines).strip()
    return {"title": repo["name"], "url": repo["html_url"], "color": COLOR, "description": text[:4096]}


def payload(projects, now):
    embeds = [card(p) for p in projects[:10]]
    content = HEADER.format(now=int(now.timestamp()))
    if not embeds:
        content += "\n\nNothing is open right now. The next project opens soon."
    return {"content": content, "embeds": embeds, "allowed_mentions": {"parse": []}}


def embed_chars(body):
    return sum(len(e.get("title", "")) + len(e.get("description", "")) for e in body["embeds"])


def publish(body):
    hook = os.environ.get("DISCORD_BOARD_WEBHOOK", "").strip()
    if not hook:
        raise SystemExit("DISCORD_BOARD_WEBHOOK is not set.")
    message_id = os.environ.get("BOARD_MESSAGE_ID", "").strip()
    if not message_id:
        sent = request(f"{hook}?wait=true", "POST", body)
        print(f"Posted a new board message. Set the BOARD_MESSAGE_ID variable to {sent['id']}")
        return
    try:
        request(f"{hook}/messages/{message_id}", "PATCH", body)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise SystemExit("The board message is gone. Clear BOARD_MESSAGE_ID and run the workflow once to post a new one.")
        raise
    print(f"Board updated: {len(body['embeds'])} projects")


def staff_check(count):
    if count >= MIN_OPEN:
        return
    hook = os.environ.get("DISCORD_STAFF_WEBHOOK", "").strip()
    if not hook:
        print("Fewer than 2 projects are open, but DISCORD_STAFF_WEBHOOK is not set.")
        return
    request(hook, "POST", {
        "content": f"Only {count} project{'s' if count != 1 else ''} open on the commission board. "
                   f"The rule is at least {MIN_OPEN}.",
        "allowed_mentions": {"parse": []},
    })


def self_test():
    now = datetime(2026, 11, 22, tzinfo=timezone.utc)

    def issue(n, labels=(), who=(), title="Fix it"):
        return {"number": n, "title": title, "html_url": f"i{n}",
                "labels": [{"name": l} for l in labels], "assignees": [{"login": w} for w in who]}

    repos = [
        {"name": ".github"}, {"name": "Old", "archived": True}, {"name": "Fork", "fork": True},
        {"name": "Tpl", "is_template": True}, {"name": "beta"}, {"name": "Alpha"},
    ]
    assert [r["name"] for r in active(repos)] == ["Alpha", "beta"]

    issues = [issue(3, ["hard"]), issue(1, ["easy"], ["sky"]), issue(2, ["medium"]), issue(4, ["good first issue"])]
    c = card({"repo": {"name": "A", "html_url": "u", "description": "Does A"}, "issues": issues, "due": "2026-12-01T08:00:00Z"})
    body = c["description"].splitlines()
    assert body[0] == "Does A"
    assert "<t:1796112000:R>" in c["description"]
    assert "**3 of 4 open to claim**" in c["description"]
    order = [l.split("#")[1].split(" ")[0] for l in body if l.startswith(("`", "["))]
    assert order == ["4", "2", "3", "1"], order  # unclaimed first, easiest first
    assert "`first issue` [#4" in c["description"] and "claimed by sky" in c["description"]

    empty = card({"repo": {"name": "B", "html_url": "u", "description": None}, "issues": [], "due": None})
    assert "No close date yet." in empty["description"] and "No open issues yet" in empty["description"]

    tricky = issue_line(issue(9, title="[x] @everyone " + "y" * 200))
    assert "[x]" not in tricky.split("](")[0][1:] and "..." in tricky

    many = [issue(n, ["medium"], title="t" * 90) for n in range(1, 41)]
    big = payload([{"repo": {"name": f"P{k}", "html_url": "u", "description": "d" * 200}, "issues": many,
                    "due": "2026-12-01T00:00:00Z"} for k in range(3)], now)
    assert embed_chars(big) < 6000, embed_chars(big)
    assert all(len(e["description"]) <= 4096 for e in big["embeds"])
    assert "+28 more" in big["embeds"][0]["description"]
    assert len(big["content"]) < 2000 and big["allowed_mentions"] == {"parse": []}
    assert "Nothing is open" in payload([], now)["content"]
    print("self-test passed")


def main():
    if "--self-test" in sys.argv:
        return self_test()
    projects = fetch()
    body = payload(projects, datetime.now(timezone.utc))
    publish(body)
    if "--staff-check" in sys.argv:
        staff_check(len(projects))


if __name__ == "__main__":
    main()
