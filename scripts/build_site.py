#!/usr/bin/env python3
"""stats.devvm.dev: data/*.csv into a static site, with no JavaScript and no outside requests.

  site.py build OUT [--banner TEXT]   write the site into OUT (made or emptied first)

Stdlib only. Each chart is an SVG drawn here, with a data table under it and its CSV linked. Every value
from the data goes through html.escape, and the pages' Content-Security-Policy allows no scripts at all.
"""

import argparse
import hashlib
import html
import json
import math
import os
import shutil
import string
import sys
from datetime import datetime, timedelta, timezone

# python3 -I leaves the script's own folder off sys.path, so stats.py is found by its path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stats  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SITE = os.path.join(ROOT, "site")
E = html.escape
PAGES = [("index.html", "Overview"), ("releases.html", "Releases"), ("traffic.html", "Traffic"),
         ("about.html", "How it's counted")]
# The series slots, in the order every chart assigns them (style.css's .s1 to .s3, checked for a dark
# surface with the dataviz validator). Each entity keeps its slot on every chart.
SCRIPT, UPGRADE, BREW = "s2", "s1", "s3"


def slurp(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def fmt(n):
    return "{:,}".format(int(round(n)))


def nice_max(v):
    if v <= 0:
        return 1, 1
    step = 10 ** math.floor(math.log10(v / 4))
    for m in (1, 2, 2.5, 5, 10):
        if v / (step * m) <= 5:
            step *= m
            break
    return math.ceil(v / step) * step, step


# --- charts ---------------------------------------------------------------------------------

W, H, L, R, T, B = 720, 260, 56, 120, 16, 32  # the viewBox, and its margins (labels on the right)


def line_chart(cid, title, desc, series, x_labels, x_range=None):
    """series: [(name, slot, [(x, y), ...])], x numbers; x_labels(x0, x1) gives the ticks, and
    x_labels(x, x, point=True) a point's name for its tooltip. x_range fixes the x axis."""
    xs = [x for _, _, pts in series for x, _ in pts]
    ys = [y for _, _, pts in series for _, y in pts]
    if not xs:
        return '<p class="empty">No data yet.</p>'
    x0, x1 = x_range or (min(xs), max(xs))
    if x1 == x0:
        x1 = x0 + 1
    ymax, ystep = nice_max(max(ys) if ys else 1)
    px = lambda x: L + (x - x0) / (x1 - x0) * (W - L - R)
    py = lambda y: T + (1 - y / ymax) * (H - T - B)
    out = ['<svg class="chart" viewBox="0 0 %d %d" role="img" aria-labelledby="%s-t %s-d">' % (W, H, cid, cid),
           '<title id="%s-t">%s</title><desc id="%s-d">%s</desc>' % (cid, E(title), cid, E(desc))]
    y = 0
    while y <= ymax + 1e-9:
        out.append('<line class="grid" x1="%d" x2="%d" y1="%.1f" y2="%.1f"/>' % (L, W - R, py(y), py(y)))
        out.append('<text class="axis" x="%d" y="%.1f" text-anchor="end">%s</text>' % (L - 8, py(y) + 4, fmt(y)))
        y += ystep
    for x, label in x_labels(x0, x1):
        out.append('<text class="axis" x="%.1f" y="%d" text-anchor="middle">%s</text>' % (px(x), H - 10, E(label)))
    for name, slot, pts in series:
        pts = sorted(pts)
        if len(pts) > 1:
            d = " ".join("%s%.1f,%.1f" % ("M" if i == 0 else "L", px(x), py(y)) for i, (x, y) in enumerate(pts))
            out.append('<path class="line %s" d="%s"/>' % (slot, d))
        lx, ly = pts[-1]
        out.append('<circle class="dot %s" cx="%.1f" cy="%.1f" r="4"/>' % (slot, px(lx), py(ly)))
        out.append('<text class="label" x="%.1f" y="%.1f">%s %s</text>' % (px(lx) + 10, py(ly) + 4, E(name), fmt(ly)))
        # The hover layer without scripts: a bigger, invisible target per point, with a native tooltip.
        for x, y in pts:
            out.append('<circle class="hit" cx="%.1f" cy="%.1f" r="9"><title>%s, %s: %s</title></circle>'
                       % (px(x), py(y), E(name), E(x_labels(x, x, point=True)[0][1]), fmt(y)))
    out.append("</svg>")
    return "".join(out)


def bar_chart(cid, title, desc, items):
    """items: [(label, value, slot)]: horizontal bars from one baseline, the value at each tip."""
    if not items:
        return '<p class="empty">No data yet.</p>'
    vmax = max(v for _, v, _ in items) or 1
    left, bar, gap, width = 230, 20, 14, 480
    h = len(items) * (bar + gap) + gap
    out = ['<svg class="chart bars" viewBox="0 0 %d %d" role="img" aria-labelledby="%s-t %s-d">' % (W, h, cid, cid),
           '<title id="%s-t">%s</title><desc id="%s-d">%s</desc>' % (cid, E(title), cid, E(desc))]
    for i, (label, v, slot) in enumerate(items):
        y = gap + i * (bar + gap)
        w = max(v / vmax * (width - 70), 0)
        out.append('<text class="axis" x="%d" y="%d" text-anchor="end">%s</text>' % (left - 10, y + 14, E(label)))
        if w >= 4:  # square at the baseline, a 4px round at the data end
            out.append('<path class="bar %s" d="M%d,%dh%.1fa4,4 0 0 1 4,4v%da4,4 0 0 1 -4,4h-%.1fz"/>'
                       % (slot, left, y, w - 4, bar - 8, w - 4))
        out.append('<text class="label" x="%.1f" y="%d">%s</text>' % (left + w + 8, y + 14, fmt(v)))
    out.append('<line class="baseline" x1="%d" x2="%d" y1="%d" y2="%d"/></svg>' % (left, left, gap - 4, h - gap + 4))
    return "".join(out)


def legend(items):
    return '<ul class="legend">%s</ul>' % "".join(
        '<li><span class="swatch %s"></span>%s</li>' % (slot, E(name)) for name, slot in items)


def table(caption, head, rows, csv=None):
    link = ' <a href="data/%s">%s</a>' % (csv, E(csv)) if csv else ""
    body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % E(str(c)) for c in r) for r in rows)
    return ('<details><summary>The data%s</summary><table><caption>%s</caption><thead><tr>%s</tr></thead>'
            '<tbody>%s</tbody></table></details>' % (link and " (" + link.strip() + ")", E(caption),
                                                      "".join("<th>%s</th>" % E(h) for h in head), body))


def date_ticks(x0, x1, point=False):
    day = lambda x: datetime.fromtimestamp(x, timezone.utc).strftime("%b %-d")
    if point:
        return [(x0, datetime.fromtimestamp(x0, timezone.utc).strftime("%b %-d %H:%M UTC"))]
    ticks, seen = [], set()
    for i in range(5):  # up to five, one per day at most
        x = x0 + (x1 - x0) * i / 4
        if day(x) not in seen:
            seen.add(day(x))
            ticks.append((x, day(x)))
    return ticks


def day_ticks(x0, x1, point=False):
    if point:
        return [(x0, "day %g" % x0)]
    return [(d, "day %d" % d) for d in range(0, 15, 2)]


# --- the data -------------------------------------------------------------------------------

def load():
    rows = stats.read("downloads.csv")
    if not rows:
        sys.exit("site: no data: run stats.py ingest first")
    now = max(stats.ts(r["snapshot_at"]) for r in rows)
    rels = stats.releases(rows)
    rate, first = stats.completion_rate(rows, rels, now)
    return rows, now, rels, rate, first


def split(rows, tag, when, rate):
    c = stats.counts_at(rows, tag, when)
    return (stats.estimate(stats.subtract_annotations(c, tag, when), rate), c) if c else (None, None)


def totals_over_time(rows, rels, rate):
    """Archive downloads across releases at each snapshot, less known test downloads, as the tiles."""
    pts = []
    for at in sorted({r["snapshot_at"] for r in rows}):
        when = stats.ts(at)
        total = sum((split(rows, tag, when, rate)[0] or {"total": 0})["total"] for _, tag, _ in rels)
        pts.append((when.timestamp(), total))
    return pts


def curve(rows, tag, pub, now, rate):
    pts = {UPGRADE: [(0, 0)], SCRIPT: [(0, 0)], BREW: [(0, 0)]}
    table_rows = []
    for d in range(1, 15):
        when = pub + timedelta(days=d)
        if when > now + timedelta(days=1):
            break
        e, c = split(rows, tag, min(when, now), rate)
        if not e:
            continue
        x = min(d, (now - pub).total_seconds() / 86400)
        pts[UPGRADE].append((x, e["upgrade"]))
        pts[SCRIPT].append((x, e["script"]))
        pts[BREW].append((x, e["brew_manual"]))
        table_rows.append(("%.1f" % x, e["script"], e["upgrade"], e["brew_manual"], e["total"]))
    return pts, table_rows


# --- the pages ------------------------------------------------------------------------------

def tile(label, value, note):
    return ('<div class="tile"><div class="tile-label">%s</div><div class="tile-value">%s</div>'
            '<div class="tile-note">%s</div></div>' % (E(label), E(value), E(note)))


def overview(rows, now, rels, rate, first):
    finals = [(p, t) for p, t, pre in rels if pre == "false"]
    total = sum(split(rows, t, now, rate)[0]["total"] for _, t, _ in rels)
    tiles = [tile("Archive downloads", fmt(total), "every release, every platform, all time")]
    if finals:
        p, t = finals[0]
        e, _ = split(rows, t, now, rate)
        age = (now - stats.ts(p)).days
        tiles.append(tile("Upgrades to " + t, fmt(e["upgrade"]), "devvm upgrade, in %d days, estimated" % age))
        tiles.append(tile("New installs of " + t, fmt(e["script"]), "by install.sh, estimated"))
    tt = [r for r in stats.read("traffic_totals.csv") if r["kind"] == "views"]
    if tt:
        last = max(tt, key=lambda r: r["snapshot_at"])
        tiles.append(tile("Visitors", fmt(int(last["uniques"])), "unique, the repo's last 14 days"))
    pts = totals_over_time(rows, rels, rate)
    body = ['<div class="tiles">%s</div>' % "".join(tiles),
            "<h2>Downloads over time</h2>",
            '<p class="sub">All archive downloads, every release, at each snapshot.</p>',
            line_chart("total", "Archive downloads over time", "Cumulative archive downloads across releases.",
                       [("archives", UPGRADE, pts)], date_ticks),
            table("Archive downloads at each snapshot", ["snapshot (UTC)", "archives"],
                  [(datetime.fromtimestamp(x, timezone.utc).strftime("%Y-%m-%d %H:%M"), fmt(y)) for x, y in pts],
                  "downloads.csv")]
    return "".join(body)


def release_section(rows, now, rate, pub, tag, pre):
    e, c = split(rows, tag, now, rate)
    head = '<h2 id="%s">%s%s</h2><p class="sub">Published %s.</p>' % (
        E(tag), E(tag), ' <span class="pre">prerelease</span>' if pre == "true" else "", E(pub[:10]))
    est = [("New installs", e["script"], SCRIPT), ("Upgrades", e["upgrade"], UPGRADE),
           ("Homebrew or manual", e["brew_manual"], BREW)]
    parts = [head, "<h3>How it was installed</h3>",
             bar_chart("est-" + tag, tag + ": installs by path", "Estimated downloads by install path.", est),
             table(tag + " by install path", ["path", "downloads"], [(n, v) for n, v, _ in est], "downloads.csv")]
    if pre != "true":
        pts, trows = curve(rows, tag, stats.ts(pub), now, rate)
        parts += ["<h3>Its first 14 days</h3>",
                  legend([("Upgrades", UPGRADE), ("New installs", SCRIPT), ("Homebrew or manual", BREW)]),
                  line_chart("curve-" + tag, tag + ": its first 14 days",
                             "Cumulative estimated downloads by install path, by days since publishing.",
                             [("upgrades", UPGRADE, pts[UPGRADE]), ("new", SCRIPT, pts[SCRIPT]),
                              ("brew", BREW, pts[BREW])], day_ticks, x_range=(0, 14)),
                  table(tag + ", days since publishing", ["day", "new installs", "upgrades", "Homebrew or manual",
                                                          "archives"], trows, "downloads.csv")]
    plat = sorted(c["platforms"].items(), key=lambda kv: -kv[1])
    notes = [a for a in stats.read("annotations.csv") if a["tag"] == tag]
    parts += ["<h3>Platforms</h3>",
              '<p class="sub">Archive downloads by platform, with the known test downloads in them.</p>' if notes else "",
              bar_chart("plat-" + tag, tag + ": archives by platform", "Archive downloads by platform.",
                        [(k, v, UPGRADE) for k, v in plat]),
              table(tag + " by platform", ["platform", "archives"], plat, "downloads.csv")]
    if notes:
        parts.append('<h3>Known test downloads, left out</h3><ul class="notes">%s</ul>' % "".join(
            "<li>%s: %s archives, %s install.sh, %s signatures. %s</li>" % (
                E(a["date"]), E(a["archives"]), E(a["install_sh"]), E(a["minisig"]), E(a["note"])) for a in notes))
    return "<section>%s</section>" % "".join(parts)


def releases_page(rows, now, rels, rate, first):
    intro = ('<p class="sub">Each estimate comes from which files a download fetched: '
             '<a href="about.html">how it\'s counted</a>. install.sh\'s completion rate is %.2f, measured on %s.</p>'
             % (rate, E(first or "no release yet")))
    return intro + "".join(release_section(rows, now, rate, p, t, pre) for p, t, pre in rels)


def short(label):
    """A bar's label: a page without the repo's own prefix, and at most 28 characters (the table has it whole)."""
    if label.startswith("/devvmhq/devvm"):
        label = label[len("/devvmhq/devvm"):] or "/"
    return label if len(label) <= 28 else label[:27] + "…"


def traffic_page():
    parts = []
    for kind, what in (("views", "Views"), ("clones", "Clones")):
        rs = stats.read("traffic_%s.csv" % kind)
        day = lambda r: datetime.strptime(r["day"], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
        parts += ["<h2>%s</h2>" % what, legend([(what, UPGRADE), ("Unique", SCRIPT)]),
                  line_chart(kind, what + " by day", what + " of the devvm repo on GitHub, and unique ones, by day.",
                             [(kind, UPGRADE, [(day(r), int(r["count"])) for r in rs]),
                              ("unique", SCRIPT, [(day(r), int(r["uniques"])) for r in rs])], date_ticks),
                  table(what + " by day", ["day", what.lower(), "unique"],
                        [(r["day"], r["count"], r["uniques"]) for r in rs], "traffic_%s.csv" % kind)]
    for name, field, what in (("referrers.csv", "referrer", "Top referrers"), ("paths.csv", "path", "Top pages")):
        rs = stats.read(name)
        if not rs:
            continue
        last = max(r["snapshot_date"] for r in rs)
        top = sorted((r for r in rs if r["snapshot_date"] == last), key=lambda r: -int(r["count"]))
        parts += ["<h2>%s</h2>" % what, '<p class="sub">GitHub\'s top 10 for the 14 days to %s.</p>' % E(last),
                  bar_chart(field, what, what + " by views.", [(short(r[field]), int(r["count"]), UPGRADE) for r in top]),
                  table(what, [field, "views", "unique"], [(r[field], r["count"], r["uniques"]) for r in top], name)]
    return "".join(parts)


def page(name, title, body, now, banner, og):
    tpl = string.Template(slurp(os.path.join(SITE, "page.html")))
    nav = "".join('<a href="%s"%s>%s</a>' % (f, ' aria-current="page"' if f == name else "", E(t)) for f, t in PAGES)
    return tpl.substitute(title=E(title), nav=nav, body=body, path="" if name == "index.html" else name,
                          banner='<p class="banner">%s</p>' % E(banner) if banner else "",
                          updated=E(now.strftime("%Y-%m-%d %H:%M UTC")), og_image=E(og[0]), og_alt=E(og[1]))


def card_numbers(rows, now, rels, rate):
    """The card's two number tiles, its sparkline and its alt text, from the numbers the pages show."""
    total = sum(split(rows, t, now, rate)[0]["total"] for _, t, _ in rels)
    tiles = [("DOWNLOADS", fmt(total), "all releases")]
    alt = "devvm stats: %s archive downloads across all releases" % fmt(total)
    finals = [(p, t) for p, t, pre in rels if pre == "false"]
    if finals:
        p, t = finals[0]
        e = split(rows, t, now, rate)[0]
        days = max((now - stats.ts(p)).days, 0)
        what, n = ("upgrades", e["upgrade"]) if e["upgrade"] else ("new installs", e["script"])
        tiles.append(("LATEST " + t, fmt(n), "%s, %d day%s" % (what, days, "" if days == 1 else "s")))
        alt += "; %s, the latest release, has %s %s in %d days" % (t, fmt(n), what, days)
    return tiles, totals_over_time(rows, rels, rate), alt + ". Updated %s." % now.strftime("%Y-%m-%d")


def social_card(out, rows, now, rels, rate):
    """og-<hash>.png with today's numbers (and og.png, the same, for looking at), named by its content so
    social sites' caches see a new card when the numbers change. If drawing it fails, the site's static
    card stands in, so the build never fails over its image."""
    tiles, spark, alt = card_numbers(rows, now, rels, rate)
    try:
        import card
        png = card.render(os.path.join(out, "og.png"), tiles, spark)
    except Exception as err:  # noqa: BLE001 -- any failure falls back to the static card
        print("site: the social card failed (%s); using the static one" % err, file=sys.stderr)
        shutil.copy(os.path.join(SITE, "og.png"), os.path.join(out, "og.png"))
        png = slurp(os.path.join(out, "og.png"), "rb")
        alt = "devvm stats: release downloads and GitHub traffic, every day"
    name = "og-%s.png" % hashlib.sha256(png).hexdigest()[:12]
    shutil.copy(os.path.join(out, "og.png"), os.path.join(out, name))
    return name, alt


def build(out, banner):
    rows, now, rels, rate, first = load()
    if os.path.exists(out):
        shutil.rmtree(out)
    shutil.copytree(os.path.join(SITE, "brand"), out)
    for f in ("SOURCES", "og-template.png"):
        os.remove(os.path.join(out, f))
    shutil.copy(os.path.join(SITE, "style.css"), out)
    shutil.copytree(stats.DATA, os.path.join(out, "data"))
    og = social_card(out, rows, now, rels, rate)
    bodies = {"index.html": overview(rows, now, rels, rate, first),
              "releases.html": releases_page(rows, now, rels, rate, first),
              "traffic.html": traffic_page(),
              "about.html": slurp(os.path.join(SITE, "about.html"))}
    for name, title in PAGES:
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(page(name, title, bodies[name], now, banner, og))
    summary = {"updated": now.isoformat(), "completion_rate": rate, "releases": [
        dict(tag=t, published_at=p, prerelease=pre == "true", **split(rows, t, now, rate)[0]) for p, t, pre in rels]}
    with open(os.path.join(out, "data", "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    print("site: %d pages in %s" % (len(PAGES), out))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("out")
    b.add_argument("--banner", default="")
    a = p.parse_args()
    build(a.out, a.banner)


if __name__ == "__main__":
    main()
