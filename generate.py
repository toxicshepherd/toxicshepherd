#!/usr/bin/env python3
"""Render dark_mode.svg and light_mode.svg for the GitHub profile card.

Stats come from the GitHub GraphQL API. Set ACCESS_TOKEN (or GITHUB_TOKEN) to a
personal access token with the `repo` and `read:user` scopes. Without a token the
script still renders, using zeroes, so the layout can be checked locally.

Only the standard library is used, so this runs anywhere python3 does.
"""

import argparse
import calendar
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(ROOT, "cache", "loc.json")
ENDPOINT = "https://api.github.com/graphql"

# Courier New and DejaVu Sans Mono both advance 0.6em per glyph, so the card can
# be laid out in character cells and converted to pixels at the end.
CHAR_RATIO = 0.60
FONT_SIZE = 12
LINE_H = 15
PAD = 18
GAP_CH = 4

THEMES = {
    "dark": {
        "bg": "#0d1117", "border": "#30363d", "art": "#8b949e", "label": "#58a6ff",
        "muted": "#484f58", "value": "#c9d1d9", "title": "#d2a8ff", "num": "#79c0ff",
        "green": "#3fb950", "red": "#f85149", "orange": "#d29922",
    },
    "light": {
        "bg": "#ffffff", "border": "#d0d7de", "art": "#6e7781", "label": "#0969da",
        "muted": "#afb8c1", "value": "#24292f", "title": "#8250df", "num": "#0550ae",
        "green": "#1a7f37", "red": "#cf222e", "orange": "#9a6700",
    },
}

TOKEN_RE = re.compile(r"\[\[(\w+)\|(.*?)\]\]")


# --------------------------------------------------------------------------- api


class GitHub:
    def __init__(self, token):
        self.token = token
        self.queries = 0

    def gql(self, query, variables=None):
        payload = json.dumps({"query": query, "variables": variables or {}}).encode()
        for attempt in range(5):
            req = urllib.request.Request(ENDPOINT, data=payload, method="POST")
            req.add_header("Authorization", "bearer " + self.token)
            req.add_header("Content-Type", "application/json")
            req.add_header("User-Agent", "profile-card-generator")
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    body = json.load(response)
            except urllib.error.HTTPError as exc:
                # 403 here is almost always the secondary rate limit, not a scope problem.
                if exc.code in (403, 429, 502, 503) and attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except urllib.error.URLError:
                if attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                raise

            self.queries += 1
            if body.get("errors"):
                messages = "; ".join(e.get("message", "?") for e in body["errors"])
                if "rate limit" in messages.lower() and attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError("GraphQL error: " + messages)
            return body["data"]
        raise RuntimeError("giving up after 5 attempts")

    def viewer(self):
        data = self.gql("query { viewer { id login name createdAt followers { totalCount } } }")
        return data["viewer"]

    def owned_repo_totals(self):
        """Public+private non-fork repos owned by the viewer: count and star total."""
        query = """
        query($cursor: String) {
          viewer {
            repositories(first: 100, after: $cursor, ownerAffiliations: [OWNER], isFork: false) {
              totalCount
              pageInfo { hasNextPage endCursor }
              nodes { stargazerCount }
            }
          }
        }"""
        cursor, total, stars = None, 0, 0
        while True:
            repos = self.gql(query, {"cursor": cursor})["viewer"]["repositories"]
            total = repos["totalCount"]
            stars += sum(n["stargazerCount"] for n in repos["nodes"])
            if not repos["pageInfo"]["hasNextPage"]:
                return total, stars
            cursor = repos["pageInfo"]["endCursor"]

    def contributed_count(self):
        query = """
        query {
          viewer {
            repositoriesContributedTo(
              first: 1
              includeUserRepositories: false
              contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY, PULL_REQUEST_REVIEW]
            ) { totalCount }
          }
        }"""
        return self.gql(query)["viewer"]["repositoriesContributedTo"]["totalCount"]

    def repos_with_commit_counts(self, viewer_id):
        """Every non-fork repo the viewer can reach, with their own commit count.

        The commit count doubles as a cache key: if it has not moved since the last
        run, the repo's line counts cannot have changed either.
        """
        query = """
        query($cursor: String, $id: ID!) {
          viewer {
            repositories(
              first: 60
              after: $cursor
              isFork: false
              ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]
            ) {
              pageInfo { hasNextPage endCursor }
              nodes {
                nameWithOwner
                defaultBranchRef {
                  target { ... on Commit { history(author: {id: $id}) { totalCount } } }
                }
              }
            }
          }
        }"""
        cursor, out = None, []
        while True:
            repos = self.gql(query, {"cursor": cursor, "id": viewer_id})["viewer"]["repositories"]
            for node in repos["nodes"]:
                branch = node.get("defaultBranchRef")
                if not branch or not branch.get("target"):
                    continue  # empty repo, nothing to count
                commits = branch["target"]["history"]["totalCount"]
                if commits:
                    out.append((node["nameWithOwner"], commits))
            if not repos["pageInfo"]["hasNextPage"]:
                return out
            cursor = repos["pageInfo"]["endCursor"]

    def repo_loc(self, name_with_owner, viewer_id):
        query = """
        query($owner: String!, $name: String!, $id: ID!, $cursor: String) {
          repository(owner: $owner, name: $name) {
            defaultBranchRef {
              target {
                ... on Commit {
                  history(first: 100, author: {id: $id}, after: $cursor) {
                    pageInfo { hasNextPage endCursor }
                    nodes { additions deletions }
                  }
                }
              }
            }
          }
        }"""
        owner, name = name_with_owner.split("/", 1)
        cursor, added, deleted = None, 0, 0
        while True:
            variables = {"owner": owner, "name": name, "id": viewer_id, "cursor": cursor}
            branch = self.gql(query, variables)["repository"]["defaultBranchRef"]
            history = branch["target"]["history"]
            for commit in history["nodes"]:
                added += commit["additions"]
                deleted += commit["deletions"]
            if not history["pageInfo"]["hasNextPage"]:
                return added, deleted
            cursor = history["pageInfo"]["endCursor"]


ZEROES = {
    "login": "CHANGE_ME", "followers": 0, "repos": 0, "stars": 0, "contributed": 0,
    "commits": 0, "loc": 0, "loc_added": 0, "loc_deleted": 0,
    "created_at": date.today().isoformat(),
}


def collect_stats(token):
    if not token:
        return dict(ZEROES)

    api = GitHub(token)
    viewer = api.viewer()
    repos, stars = api.owned_repo_totals()
    contributed = api.contributed_count()

    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as fh:
            cache = json.load(fh)

    tracked = api.repos_with_commit_counts(viewer["id"])
    commits = added = deleted = 0
    fresh = {}
    for index, (name, repo_commits) in enumerate(sorted(tracked), 1):
        # The cache is committed to a public repo, so it must not carry the names
        # of private repositories. Hash them.
        key = hashlib.sha256(name.encode("utf-8")).hexdigest()
        hit = cache.get(key)
        if hit and hit.get("commits") == repo_commits:
            repo_added, repo_deleted = hit["additions"], hit["deletions"]
        else:
            print(f"  [{index}/{len(tracked)}] counting {name}", file=sys.stderr)
            repo_added, repo_deleted = api.repo_loc(name, viewer["id"])
        fresh[key] = {"commits": repo_commits, "additions": repo_added, "deletions": repo_deleted}
        commits += repo_commits
        added += repo_added
        deleted += repo_deleted

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(fresh, fh, indent=1, sort_keys=True)

    print(f"  {api.queries} GraphQL queries, {len(tracked)} repos", file=sys.stderr)
    return {
        "login": viewer["login"],
        "created_at": viewer["createdAt"][:10],
        "followers": viewer["followers"]["totalCount"],
        "repos": repos,
        "stars": stars,
        "contributed": contributed,
        "commits": commits,
        "loc": added - deleted,
        "loc_added": added,
        "loc_deleted": deleted,
    }


# ------------------------------------------------------------------------ layout


def uptime(birthday):
    born = date.fromisoformat(birthday)
    today = date.today()
    years = today.year - born.year
    months = today.month - born.month
    days = today.day - born.day
    if days < 0:
        months -= 1
        prev_month = today.month - 1 or 12
        prev_year = today.year if today.month > 1 else today.year - 1
        days += calendar.monthrange(prev_year, prev_month)[1]
    if months < 0:
        years -= 1
        months += 12

    def unit(value, name):
        return f"{value} {name}" if value == 1 else f"{value} {name}s"

    return ", ".join([unit(years, "year"), unit(months, "month"), unit(days, "day")])


def substitute(text, values):
    for key, value in values.items():
        placeholder = "{" + key + "}"
        if placeholder in text:
            rendered = f"{value:,}" if isinstance(value, int) else str(value)
            text = text.replace(placeholder, rendered)
    return text


def parse_markup(text, default):
    """Split '[[green|+12]] ok' into [('+12','green'), (' ok', default)]."""
    parts, pos = [], 0
    for match in TOKEN_RE.finditer(text):
        if match.start() > pos:
            parts.append((text[pos:match.start()], default))
        parts.append((match.group(2), match.group(1)))
        pos = match.end()
    if pos < len(text):
        parts.append((text[pos:], default))
    return parts


def visible_len(text):
    return len(TOKEN_RE.sub(lambda m: m.group(2), text))


def build_card(config, values):
    width = config.get("card_width", 66)
    header = config["header"]
    lines = []

    prompt = f"{header['user']}@{header['host']} "
    lines.append([(prompt, "title"), ("-" * max(1, width - len(prompt)), "muted")])

    for block in config["blocks"]:
        if block.get("title"):
            prefix = f"- {block['title']} "
            lines.append([(prefix, "title"), ("-" * max(1, width - len(prefix)), "muted")])

        for label, raw in block["rows"]:
            value = substitute(raw, values)
            prefix = f"- {label}: "
            filler = width - len(prefix) - 1 - visible_len(value)
            if filler < 1:
                # Value is too long for the card; let it overflow rather than truncate.
                filler = 1
            line = [(prefix, "label"), ("." * filler, "muted"), (" ", "value")]
            line.extend(parse_markup(value, "value"))
            lines.append(line)

    return lines


# ------------------------------------------------------------------------ render


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_svg(theme_name, art_lines, card_lines):
    theme = THEMES[theme_name]
    char_w = FONT_SIZE * CHAR_RATIO
    art_w = max((len(line) for line in art_lines), default=0)
    columns = art_w + GAP_CH + max(sum(len(t) for t, _ in line) for line in card_lines)
    width = round(PAD * 2 + columns * char_w)
    height = round(PAD * 2 + max(len(art_lines), len(card_lines)) * LINE_H)

    styles = "".join(f".{key}{{fill:{color}}}" for key, color in theme.items() if key not in ("bg", "border"))
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="GitHub profile card">',
        f"<style>text{{font-family:'Courier New',Courier,'DejaVu Sans Mono',monospace;"
        f"font-size:{FONT_SIZE}px;white-space:pre;font-variant-ligatures:none}}{styles}</style>",
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8" '
        f'fill="{theme["bg"]}" stroke="{theme["border"]}"/>',
    ]

    def baseline(index):
        return PAD + FONT_SIZE + index * LINE_H

    for i, line in enumerate(art_lines):
        if line.strip():
            out.append(f'<text class="art" x="{PAD}" y="{baseline(i)}" xml:space="preserve">{esc(line)}</text>')

    card_x = round(PAD + (art_w + GAP_CH) * char_w)
    for i, line in enumerate(card_lines):
        spans = "".join(f'<tspan class="{cls}">{esc(text)}</tspan>' for text, cls in line if text)
        out.append(f'<text x="{card_x}" y="{baseline(i)}" xml:space="preserve">{spans}</text>')

    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="skip the API and render with zeroes")
    args = parser.parse_args()

    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as fh:
        config = json.load(fh)

    token = None if args.offline else (os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    if not args.offline and not token:
        # Falling through to zeroes here would quietly publish an empty card.
        sys.exit("ACCESS_TOKEN ist nicht gesetzt. Fuer eine lokale Vorschau: generate.py --offline")
    if args.offline:
        print("! --offline: Statistiken werden als 0 gerendert", file=sys.stderr)
    stats = collect_stats(token)

    configured = config.get("github_username")
    if token and configured not in ("CHANGE_ME", stats["login"]):
        print(f"! config.json says {configured!r} but the token belongs to {stats['login']!r}", file=sys.stderr)

    # No birthday configured? Count from the account creation date instead, so the
    # card never states an age nobody supplied.
    since = config.get("birthday") or stats["created_at"]
    values = dict(stats, uptime=uptime(since))

    with open(os.path.join(ROOT, config["ascii_art"]), encoding="utf-8") as fh:
        art_lines = fh.read().rstrip("\n").split("\n")

    card_lines = build_card(config, values)

    for theme in THEMES:
        path = os.path.join(ROOT, f"{theme}_mode.svg")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render_svg(theme, art_lines, card_lines))
        print(f"wrote {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
