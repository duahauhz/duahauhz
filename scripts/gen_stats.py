#!/usr/bin/env python3
"""Render assets/stats.svg for the profile README from the GitHub API.

Standard library only. Needs a token in GH_TOKEN (the Actions GITHUB_TOKEN is enough).
Env: GH_USER (default duahauhz), OUT (default assets/stats.svg).
"""
import datetime as dt
import json
import os
import urllib.request
from xml.sax.saxutils import escape

USER = os.environ.get("GH_USER", "duahauhz")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
OUT = os.environ.get("OUT", "assets/stats.svg")

LIME, CYAN, ORANGE, PINK, YELLOW, GREY = "#c6ff3d", "#38e1ff", "#ff8a3d", "#ff4d8d", "#ffd23d", "#8796a8"
PALETTE = [LIME, CYAN, ORANGE, PINK, YELLOW, GREY]
MONO = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
SANS = "'Space Grotesk', 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif"


def api(url, payload=None):
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload else None)
    req.add_header("User-Agent", "profile-stats")
    req.add_header("Accept", "application/vnd.github+json")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch():
    user = api(f"https://api.github.com/users/{USER}")
    repos, page = [], 1
    while True:
        chunk = api(f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}&type=owner")
        repos += chunk
        if len(chunk) < 100:
            break
        page += 1
    own = [r for r in repos if not r["fork"]]

    langs = {}
    for r in sorted(own, key=lambda x: x["pushed_at"], reverse=True)[:40]:
        for name, n in api(r["languages_url"]).items():
            langs[name] = langs.get(name, 0) + n

    q = """query($login:String!){user(login:$login){contributionsCollection{
      totalCommitContributions totalPullRequestContributions
      contributionCalendar{totalContributions weeks{contributionDays{contributionCount date weekday}}}}}}"""
    gql = api("https://api.github.com/graphql", {"query": q, "variables": {"login": USER}})
    cc = gql["data"]["user"]["contributionsCollection"]
    return {
        "repos": user["public_repos"],
        "followers": user["followers"],
        "stars": sum(r["stargazers_count"] for r in own),
        "commits": cc["totalCommitContributions"],
        "prs": cc["totalPullRequestContributions"],
        "total": cc["contributionCalendar"]["totalContributions"],
        "weeks": cc["contributionCalendar"]["weeks"],
        "langs": langs,
    }


def streaks(weeks):
    days = [d for w in weeks for d in w["contributionDays"]]
    best = cur = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] > 0 else 0
        best = max(best, run)
    # current streak: walk back from the latest day (today may still be empty)
    i = len(days) - 1
    if i >= 0 and days[i]["contributionCount"] == 0:
        i -= 1
    while i >= 0 and days[i]["contributionCount"] > 0:
        cur += 1
        i -= 1
    return cur, best


def level(n, mx):
    if n <= 0:
        return 0
    r = n / mx
    return 1 if r <= .25 else 2 if r <= .5 else 3 if r <= .75 else 4


def text(x, y, s, size=13, fill="#e8eef5", family=MONO, weight=500, anchor="start", spacing=0):
    sp = f' letter-spacing="{spacing}"' if spacing else ""
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}"{sp}>{escape(str(s))}</text>')


def render(d):
    W, H, PAD = 1200, 456, 48
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="GitHub stats for {escape(USER)}">']
    out.append('<defs><clipPath id="bar"><rect x="48" y="214" width="1104" height="10" rx="5"/></clipPath>'
               '<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">'
               '<path d="M40 0H0V40" fill="none" stroke="#141c26" stroke-width="1"/></pattern></defs>')
    out.append(f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="22" fill="#0b1016" stroke="#1f2833"/>')
    out.append(f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="22" fill="url(#grid)" opacity=".7"/>')

    # header
    out.append(f'<circle cx="{PAD+5}" cy="42" r="5" fill="{LIME}"/>')
    out.append(text(PAD + 20, 47, f"GITHUB / {USER}", 14, LIME, spacing=2))
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    out.append(text(W - PAD, 47, f"UPDATED {today} - AUTO DAILY", 12, GREY, anchor="end", spacing=1.5))

    # metrics
    cols = [("REPOSITORIES", d["repos"]), ("STARS", d["stars"]), ("FOLLOWERS", d["followers"]),
            ("COMMITS / YEAR", d["commits"]), ("PULL REQUESTS / YEAR", d["prs"])]
    cw = (W - 2 * PAD) / len(cols)
    for i, (label, val) in enumerate(cols):
        x = PAD + i * cw + (0 if i == 0 else 24)
        if i:
            out.append(f'<line x1="{PAD + i*cw}" y1="82" x2="{PAD + i*cw}" y2="146" stroke="#1f2833"/>')
        out.append(text(x, 126, f"{val:,}", 48, "#e8eef5", SANS, 700))
        out.append(text(x, 148, label, 11.5, GREY, spacing=1.6))

    # languages
    out.append(text(PAD, 196, "LANGUAGES", 11.5, GREY, spacing=1.6))
    total = sum(d["langs"].values()) or 1
    top = sorted(d["langs"].items(), key=lambda kv: kv[1], reverse=True)
    shown = top[:5]
    other = sum(v for _, v in top[5:])
    if other:
        shown.append(("Other", other))
    if not shown:
        shown = [("No code yet", 1)]
        total = 1
    out.append('<g clip-path="url(#bar)"><rect x="48" y="214" width="1104" height="10" fill="#141c26"/>')
    x = 48.0
    for i, (name, v) in enumerate(shown):
        w = 1104 * v / total
        out.append(f'<rect x="{x:.2f}" y="214" width="{w:.2f}" height="10" fill="{PALETTE[i % len(PALETTE)]}"/>')
        x += w
    out.append("</g>")
    lx = PAD
    for i, (name, v) in enumerate(shown):
        out.append(f'<rect x="{lx}" y="244" width="10" height="10" rx="3" fill="{PALETTE[i % len(PALETTE)]}"/>')
        label = f"{name} {100*v/total:.1f}%"
        out.append(text(lx + 18, 254, label, 13, "#c9d4df"))
        lx += 30 + 8.2 * len(label)

    # heatmap
    out.append(text(PAD, 292, "CONTRIBUTIONS / LAST 12 MONTHS", 11.5, GREY, spacing=1.6))
    shades = ["#141c26", "#2c3d14", "#55741a", "#8bbd24", LIME]
    days = [x["contributionCount"] for w in d["weeks"] for x in w["contributionDays"]]
    mx = max(days) if days and max(days) else 1
    pitch, size, gy = 15, 12, 304
    for wi, w in enumerate(d["weeks"]):
        for day in w["contributionDays"]:
            lv = level(day["contributionCount"], mx)
            out.append(f'<rect x="{PAD + wi*pitch}" y="{gy + day["weekday"]*pitch}" width="{size}" height="{size}" rx="3" fill="{shades[lv]}"/>')
    hx = PAD + 53 * pitch + 28
    cur, best = streaks(d["weeks"])
    out.append(text(hx, 330, f'{d["total"]:,}', 40, "#e8eef5", SANS, 700))
    out.append(text(hx, 350, "CONTRIBUTIONS", 11.5, GREY, spacing=1.6))
    out.append(text(hx + 150, 330, f"{cur}", 40, LIME, SANS, 700))
    out.append(text(hx + 150, 350, "CURRENT STREAK", 11.5, GREY, spacing=1.6))
    out.append(text(hx, 396, f"{best}", 40, "#e8eef5", SANS, 700))
    out.append(text(hx, 416, "LONGEST STREAK", 11.5, GREY, spacing=1.6))
    # legend under the heatmap
    out.append(text(PAD, 438, "LESS", 10.5, GREY, spacing=1.2))
    for i, c in enumerate(shades):
        out.append(f'<rect x="{PAD + 40 + i*16}" y="428" width="12" height="12" rx="3" fill="{c}"/>')
    out.append(text(PAD + 40 + 5 * 16 + 6, 438, "MORE", 10.5, GREY, spacing=1.2))
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    svg = render(fetch())
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(svg + "\n")
    print("wrote", OUT, len(svg), "bytes")
