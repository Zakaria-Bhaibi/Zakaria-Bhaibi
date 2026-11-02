#!/usr/bin/env python3
"""Draws the profile's stats cards as SVG files in assets/stats/.

Standard library only. No third-party service to go down or run out of quota.
If any source looks wrong it exits with an error WITHOUT touching the existing
cards, so the profile keeps the last good version and the Action shows as failed.
"""
import datetime
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request

USER = "Zakaria-Bhaibi"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "stats")
CYAN, TEXT, MUTED, GRID = "#00C8FF", "#8E8E9A", "#71717A", "#71717A33"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
LANG_COLORS = {
    "HTML": "#E34C26", "CSS": "#663399", "JavaScript": "#F1E05A", "TypeScript": "#3178C6",
    "Python": "#2DD4BF", "PHP": "#4F5D95", "Java": "#B07219", "C#": "#178600", "Shell": "#89E051",
    "SCSS": "#C6538C", "Liquid": "#67B8DE", "Vue": "#41B883", "TSQL": "#E38C00", "PLSQL": "#DAD8D8",
    "Dockerfile": "#384D54", "Batchfile": "#C1F12E", "PowerShell": "#012456",
}


def fetch(url, api=True):
    headers = {"User-Agent": "profile-stats"}
    if api:
        headers["Accept"] = "application/vnd.github+json"
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = "Bearer " + token
    else:
        headers["X-Requested-With"] = "XMLHttpRequest"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=40) as r:
        body = r.read().decode("utf-8")
    return json.loads(body) if api else body


def get_calendar(year):
    """Date -> count, from the same public calendar shown on the profile."""
    t = fetch(f"https://github.com/users/{USER}/contributions?from={year}-01-01&to={year}-12-31", api=False)
    cells = re.findall(r'<td[^>]*data-date="(\d{4}-\d\d-\d\d)"[^>]*id="([^"]+)"', t)
    tips = dict(re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)<', t))
    days = {}
    for date, cell in cells:
        m = re.match(r"\s*([\d,]+) contribution", tips.get(cell, ""))
        days[date] = int(m.group(1).replace(",", "")) if m else 0
    total = re.search(r"([\d,]+)\s+contributions?\s+in\s+" + str(year), t)
    if len(days) < 300 or not total:
        sys.exit(f"Calendar did not parse ({len(days)} days): refusing to overwrite the cards")
    total = int(total.group(1).replace(",", ""))
    # Guards against a markup change that quietly reads every day as zero.
    if sum(days.values()) != total:
        sys.exit(f"Calendar days add up to {sum(days.values())}, its total says {total}: refusing")
    return days, total


def get_repos():
    repos, page = [], 1
    while True:
        batch = fetch(f"https://api.github.com/users/{USER}/repos?type=owner&per_page=100&page={page}")
        repos += batch
        if len(batch) < 100:
            break
        page += 1
    if not repos:
        sys.exit("No repositories returned: refusing to overwrite the cards")
    return repos


def get_languages(repos):
    totals = {}
    for r in repos:
        if r["fork"]:
            continue
        for lang, size in fetch(r["languages_url"]).items():
            totals[lang] = totals.get(lang, 0) + size
    if not totals:
        sys.exit("No language data returned: refusing to overwrite the cards")
    return totals


def svg_open(w, h, label):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{html.escape(label)}" font-family="{FONT}">')


def stats_card(rows):
    h = 184
    s = [svg_open(440, h, "GitHub stats"),
         f'<text x="20" y="32" font-size="18" font-weight="600" fill="{CYAN}">GitHub stats</text>']
    for i, (label, value) in enumerate(rows):
        y = 64 + i * 26
        s.append(f'<circle cx="25" cy="{y - 5}" r="3.5" fill="{CYAN}"/>')
        s.append(f'<text x="40" y="{y}" font-size="14" fill="{TEXT}">{html.escape(label)}</text>')
        s.append(f'<text x="420" y="{y}" font-size="14" font-weight="600" fill="{CYAN}" text-anchor="end">{value:,}</text>')
    s.append("</svg>")
    return "".join(s)


def langs_card(totals):
    top = sorted(totals.items(), key=lambda kv: -kv[1])[:6]
    # Percentages are of ALL public code, so a seventh language is not inflated into the six.
    grand = sum(totals.values())
    h = 184
    s = [svg_open(440, h, "Top languages"),
         f'<text x="20" y="32" font-size="18" font-weight="600" fill="{CYAN}">Top languages</text>',
         '<clipPath id="bar"><rect x="20" y="46" width="400" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">']
    x = 20.0
    for lang, size in top:
        w = 400 * size / grand
        s.append(f'<rect x="{x:.2f}" y="46" width="{w:.2f}" height="10" fill="{LANG_COLORS.get(lang, CYAN)}"/>')
        x += w
    s.append(f'<rect x="{x:.2f}" y="46" width="{max(420 - x, 0):.2f}" height="10" fill="{GRID}"/></g>')
    for i, (lang, size) in enumerate(top):
        cx, cy = 26 + (i % 2) * 205, 82 + (i // 2) * 26
        s.append(f'<circle cx="{cx}" cy="{cy - 5}" r="5" fill="{LANG_COLORS.get(lang, CYAN)}"/>')
        s.append(f'<text x="{cx + 12}" y="{cy}" font-size="13" fill="{TEXT}">{html.escape(lang)} '
                 f'{100 * size / grand:.1f}%</text>')
    s.append(f'<text x="20" y="{h - 10}" font-size="11" fill="{MUTED}">Public repositories only</text></svg>')
    return "".join(s)


def activity_card(days, today):
    series = [(today - datetime.timedelta(days=30 - i)) for i in range(31)]
    values = [days.get(d.isoformat(), 0) for d in series]
    w, h, left, right, top, bottom = 900, 300, 48, 20, 52, 40
    pw, ph = w - left - right, h - top - bottom
    peak = max(max(values), 4)
    step = max(1, -(-peak // 4))
    ymax = step * 4
    X = lambda i: left + pw * i / 30
    Y = lambda v: top + ph - ph * v / ymax
    s = [svg_open(w, h, "Contribution activity, last 31 days"),
         f'<text x="{left}" y="30" font-size="18" font-weight="600" fill="{CYAN}">Contribution activity, last 31 days</text>']
    for k in range(5):
        y, v = Y(step * k), step * k
        s.append(f'<line x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>')
        s.append(f'<text x="{left - 10}" y="{y + 4:.1f}" font-size="12" fill="{MUTED}" text-anchor="end">{v}</text>')
    for i in range(0, 31, 5):
        s.append(f'<text x="{X(i):.1f}" y="{h - 14}" font-size="12" fill="{MUTED}" text-anchor="middle">'
                 f'{series[i].strftime("%b")} {series[i].day}</text>')
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(values))
    s.append(f'<polygon points="{X(0):.1f},{Y(0):.1f} {pts} {X(30):.1f},{Y(0):.1f}" fill="{CYAN}" fill-opacity="0.15"/>')
    s.append(f'<polyline points="{pts}" fill="none" stroke="{CYAN}" stroke-width="2" stroke-linejoin="round"/>')
    for i, v in enumerate(values):
        if v:
            s.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="3.5" fill="{CYAN}"><title>{series[i].isoformat()}: {v}</title></circle>')
    s.append("</svg>")
    return "".join(s)


def get_all_days(first_year, today):
    """Every day since the account opened, and the year totals checked against GitHub's own."""
    days, total = {}, 0
    for year in range(first_year, today.year + 1):
        d, n = get_calendar(year)
        days.update(d)
        total += n
    return {k: v for k, v in days.items() if k <= today.isoformat()}, total


def streaks(days, today):
    """Current streak survives an empty today: the day is not over yet."""
    one = datetime.timedelta(days=1)
    d = today if days.get(today.isoformat(), 0) else today - one
    current = 0
    while days.get(d.isoformat(), 0):
        current += 1
        d -= one
    best, best_start, best_end, run, start = 0, None, None, 0, None
    for key in sorted(days):
        if days[key]:
            start = key if run == 0 else start
            run += 1
            if run > best:
                best, best_start, best_end = run, start, key
        else:
            run = 0
    return current, best, best_start, best_end


def nice(iso, year=True):
    d = datetime.date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}" + (f", {d.year}" if year else "")


def streak_card(days, total, today):
    current, best, best_start, best_end = streaks(days, today)
    active = sorted(k for k, v in days.items() if v)
    if not active or sum(days.values()) != total:
        sys.exit("Streak data does not add up: refusing to overwrite the cards")
    span = nice(active[0]) + " - Present"
    best_span = f"{nice(best_start)} - {nice(best_end)}" if best else "None yet"
    w, h = 660, 170
    cols = [w / 6, w / 2, 5 * w / 6]
    s = [svg_open(w, h, f"{total} total contributions, current streak {current}, longest streak {best}")]
    for x in (w / 3, 2 * w / 3):
        s.append(f'<line x1="{x:.0f}" x2="{x:.0f}" y1="24" y2="{h - 24}" stroke="{GRID}"/>')
    s.append(f'<text x="{cols[0]:.0f}" y="76" font-size="30" font-weight="700" fill="{CYAN}" text-anchor="middle">{total:,}</text>')
    s.append(f'<text x="{cols[0]:.0f}" y="108" font-size="14" fill="{TEXT}" text-anchor="middle">Total contributions</text>')
    s.append(f'<text x="{cols[0]:.0f}" y="130" font-size="11" fill="{MUTED}" text-anchor="middle">{span}</text>')
    s.append(f'<circle cx="{cols[1]:.0f}" cy="66" r="36" fill="none" stroke="{CYAN}" stroke-width="4"/>')
    s.append(f'<text x="{cols[1]:.0f}" y="77" font-size="30" font-weight="700" fill="{CYAN}" text-anchor="middle">{current}</text>')
    s.append(f'<text x="{cols[1]:.0f}" y="128" font-size="14" font-weight="600" fill="{CYAN}" text-anchor="middle">Current streak</text>')
    s.append(f'<text x="{cols[2]:.0f}" y="76" font-size="30" font-weight="700" fill="{CYAN}" text-anchor="middle">{best}</text>')
    s.append(f'<text x="{cols[2]:.0f}" y="108" font-size="14" fill="{TEXT}" text-anchor="middle">Longest streak</text>')
    s.append(f'<text x="{cols[2]:.0f}" y="130" font-size="11" fill="{MUTED}" text-anchor="middle">{best_span}</text></svg>')
    return "".join(s)


GITHUB_MARK = ("M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 "
               "1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 "
               ".27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 "
               "1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 "
               "1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z")


def followers_badge(count):
    value = f"{count:,}"
    left, right = 122, 26 + 10 * len(value)
    return (svg_open(left + right, 28, f"Followers: {value}") +
            f'<rect width="{left}" height="28" fill="#050505"/><rect x="{left}" width="{right}" height="28" fill="{CYAN}"/>'
            f'<path transform="translate(10 6)" fill="#ffffff" d="{GITHUB_MARK}"/>'
            f'<text x="34" y="18" font-size="10" font-weight="700" letter-spacing="1.2" fill="#ffffff">FOLLOWERS</text>'
            f'<text x="{left + right / 2:.0f}" y="18" font-size="11" font-weight="700" fill="#050505" text-anchor="middle">{value}</text></svg>')


def main():
    today = datetime.datetime.now(datetime.timezone.utc).date()
    days, total = get_calendar(today.year)
    if today.month == 1:  # the 31-day window reaches into last year
        days.update(get_calendar(today.year - 1)[0])
    user = fetch(f"https://api.github.com/users/{USER}")
    repos = get_repos()
    prs = fetch("https://api.github.com/search/issues?per_page=1&q=" + urllib.parse.quote(f"author:{USER} type:pr"))["total_count"]
    owned = [r for r in repos if not r["fork"]]
    all_days, all_total = get_all_days(int(user["created_at"][:4]), today)
    cards = {
        "stats.svg": stats_card([
            (f"Contributions in {today.year}", total),
            ("Public repositories", len(owned)),
            ("Stars earned", sum(r["stargazers_count"] for r in owned)),
            ("Pull requests", prs),
            ("Followers", user["followers"]),
        ]),
        "top-langs.svg": langs_card(get_languages(repos)),
        "activity.svg": activity_card(days, today),
        "streak.svg": streak_card(all_days, all_total, today),
        "followers.svg": followers_badge(user["followers"]),
    }
    # Everything succeeded: only now touch the disk.
    os.makedirs(OUT, exist_ok=True)
    for name, svg in cards.items():
        tmp = os.path.join(OUT, name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(svg + "\n")
        os.replace(tmp, os.path.join(OUT, name))
    print(f"OK: {total} contributions in {today.year}, {len(owned)} repos, cards written")


if __name__ == "__main__":
    main()
