#!/usr/bin/env python3
"""devvm's adoption stats: ingest GitHub snapshots into CSVs, and report on them.

  stats.py ingest DIR [--label L]   merge DIR's releases-/views-/clones-/referrers-/paths-<stamp>.json
  stats.py report [--days N]        print the report (markdown) to stdout

Stdlib only. Every CSV is rewritten whole, sorted, so a re-run changes nothing it already has.
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

# STATS_DATA points it at another folder, as the tests and the site's preview do.
DATA = os.environ.get("STATS_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
STAMP = re.compile(r"^(releases|views|clones|referrers|paths)-(\d{4}-\d{2}-\d{2}T\d{6}Z)\.json$")
ARCHIVE = re.compile(r"^devvm-(?P<ver>[0-9][^-]*(?:-[a-z]+\.[0-9]+)?)-(?P<os>darwin|linux)-(?P<arch>arm64|amd64)\.tar\.gz$")
SOURCE = re.compile(r"^devvm-[0-9][0-9A-Za-z.-]*\.tar\.gz$")

SCHEMAS = {
    "downloads.csv": ["snapshot_at", "label", "tag", "prerelease", "published_at", "asset", "kind", "os", "arch", "download_count"],
    "traffic_views.csv": ["day", "count", "uniques", "seen_at"],
    "traffic_clones.csv": ["day", "count", "uniques", "seen_at"],
    "traffic_totals.csv": ["snapshot_at", "label", "kind", "count", "uniques"],
    "referrers.csv": ["snapshot_date", "referrer", "count", "uniques"],
    "paths.csv": ["snapshot_date", "path", "title", "count", "uniques"],
    "annotations.csv": ["date", "tag", "archives", "install_sh", "minisig", "note"],
}
KEYS = {
    "downloads.csv": ("snapshot_at", "tag", "asset"),
    "traffic_views.csv": ("day",),
    "traffic_clones.csv": ("day",),
    "traffic_totals.csv": ("snapshot_at", "kind"),
    "referrers.csv": ("snapshot_date", "referrer"),
    "paths.csv": ("snapshot_date", "path"),
}


def read(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write(name, rows):
    key = KEYS[name]
    rows = sorted(rows, key=lambda r: tuple(r[k] for k in key))
    tmp = os.path.join(DATA, name + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMAS[name], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, os.path.join(DATA, name))


def kind_of(asset):
    m = ARCHIVE.match(asset)
    if m:
        return "archive", m["os"], m["arch"]
    if SOURCE.match(asset):
        return "source", "", ""
    return {"install.sh": "install_sh", "SHA256SUMS": "sums", "SHA256SUMS.minisig": "minisig"}.get(asset, "other"), "", ""


def iso(stamp):
    return datetime.strptime(stamp, "%Y-%m-%dT%H%M%SZ").strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # gh api --paginate --slurp gives a list of pages; the baseline is one flat list.
    if isinstance(data, list) and data and isinstance(data[0], list):
        data = [x for page in data for x in page]
    return data


def upsert(name, new, replace=None):
    """new's rows win over old ones with the same key; replace(row) drops old rows first."""
    key = KEYS[name]
    rows = {tuple(r[k] for k in key): r for r in read(name) if not (replace and replace(r))}
    for r in new:
        rows[tuple(r[k] for k in key)] = r
    write(name, rows.values())


def last_counts(old, tag, before):
    """tag's counts by asset in its last snapshot before before."""
    snaps = [r["snapshot_at"] for r in old if r["tag"] == tag and r["snapshot_at"] < before]
    if not snaps:
        return None
    last = max(snaps)
    return {r["asset"]: r["download_count"] for r in old if r["tag"] == tag and r["snapshot_at"] == last}


def ingest_releases(data, at, label):
    old, rows = read("downloads.csv"), []
    for rel in data:
        if rel.get("draft"):
            continue  # a draft's counts aren't anyone's
        now = {a["name"]: str(a["download_count"]) for a in rel.get("assets", [])}
        # A release whose counts haven't moved since its last snapshot gets no rows: the report
        # reads each release's last snapshot before a time, so nothing is lost, and old releases
        # stop growing the file. Labelled snapshots (release day, tests) are always written.
        if label == "scheduled" and last_counts(old, rel["tag_name"], at) == now:
            continue
        for a in rel.get("assets", []):
            kind, os_, arch = kind_of(a["name"])
            rows.append({"snapshot_at": at, "label": label, "tag": rel["tag_name"],
                         "prerelease": str(bool(rel.get("prerelease"))).lower(),
                         "published_at": rel.get("published_at") or "", "asset": a["name"],
                         "kind": kind, "os": os_, "arch": arch, "download_count": str(a["download_count"])})
    upsert("downloads.csv", rows)


def ingest_traffic(kind, data, at, label):
    name = "traffic_%s.csv" % kind
    old = {r["day"]: r for r in read(name)}
    new = []
    for d in data.get(kind, []):
        day = d["timestamp"][:10]
        if day in old and old[day]["seen_at"] > at:
            continue  # an older snapshot never overwrites a newer one's value
        new.append({"day": day, "count": str(d["count"]), "uniques": str(d["uniques"]), "seen_at": at})
    upsert(name, new)
    upsert("traffic_totals.csv", [{"snapshot_at": at, "label": label, "kind": kind,
                                   "count": str(data.get("count", 0)), "uniques": str(data.get("uniques", 0))}])


# Referrers this public repo doesn't name: a temporary tunnel's or a private network's host can be
# one person's, so it's kept as a kind, not a name.
PRIVATE_REFERRER = re.compile(
    r"(^|\.)(trycloudflare\.com|ngrok(-free)?\.(app|dev|io)|loca\.lt|localhost|local|internal|lan)$"
    r"|^\d{1,3}(\.\d{1,3}){3}$|:")


def public_referrer(host):
    return "(a private or temporary host)" if PRIVATE_REFERRER.search(host.lower()) else host


def ingest_popular(name, field, data, at):
    date = at[:10]
    if field == "referrer":
        merged = {}
        for d in data:
            host = public_referrer(d["referrer"])
            m = merged.setdefault(host, {"referrer": host, "count": 0, "uniques": 0})
            m["count"] += d["count"]
            m["uniques"] += d["uniques"]
        data = list(merged.values())
    rows = [{"snapshot_date": date, field: d[field], "count": str(d["count"]), "uniques": str(d["uniques"]),
             **({"title": d.get("title", "")} if field == "path" else {})} for d in data]
    # A day's top 10 is replaced whole by a later run that day.
    upsert(name, rows, replace=lambda r: r["snapshot_date"] == date)


def ingest(directory, label):
    os.makedirs(DATA, exist_ok=True)
    found = sorted((m[2], m[1], f) for f in os.listdir(directory) if (m := STAMP.match(f)))
    if not found:
        sys.exit("ingest: no snapshot files in " + directory)
    for stamp, kind, f in found:
        at, data = iso(stamp), load(os.path.join(directory, f))
        if kind == "releases":
            ingest_releases(data, at, label)
        elif kind in ("views", "clones"):
            ingest_traffic(kind, data, at, label)
        elif kind == "referrers":
            ingest_popular("referrers.csv", "referrer", data, at)
        else:
            ingest_popular("paths.csv", "path", data, at)
    print("ingested %d files (%s)" % (len(found), label))


# --- the report -----------------------------------------------------------------------------

def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def counts_at(rows, tag, when):
    """The counts by kind (and archives by platform) in tag's last snapshot at or before when."""
    snaps = sorted({r["snapshot_at"] for r in rows if r["tag"] == tag and ts(r["snapshot_at"]) <= when})
    if not snaps:
        return None
    c = {"archive": 0, "install_sh": 0, "sums": 0, "minisig": 0, "source": 0, "platforms": {}}
    for r in rows:
        if r["tag"] == tag and r["snapshot_at"] == snaps[-1]:
            n = int(r["download_count"])
            if r["kind"] in c:
                c[r["kind"]] += n
            if r["kind"] == "archive":
                c["platforms"]["%s/%s" % (r["os"], r["arch"])] = n
    return c


def releases(rows):
    """(published_at, tag, prerelease) for every release, the newest first."""
    return sorted({(r["published_at"], r["tag"], r["prerelease"]) for r in rows}, reverse=True)


def completion_rate(rows, rels, now):
    """The share of install.sh fetches that went on to download, and the release it's measured on:
    the first release, which nobody could upgrade to, so its minisig downloads are all install.sh's,
    up to the next release, after which its install.sh is no longer the latest."""
    finals = [(p, t) for p, t, pre in sorted(rels) if pre == "false"]
    if not finals:
        return 1.0, None
    until = ts(finals[1][0]) if len(finals) > 1 else now
    fc = counts_at(rows, finals[0][1], until)
    return (min(fc["minisig"] / fc["install_sh"], 1.0) if fc and fc["install_sh"] else 1.0), finals[0][1]


def subtract_annotations(c, tag, until=None):
    """c less the known test downloads annotated for tag (on or before until's date, when given)."""
    for a in read("annotations.csv"):
        if a["tag"] == tag and (until is None or a["date"] <= until.strftime("%Y-%m-%d")):
            c["archive"] -= int(a["archives"] or 0)
            c["install_sh"] -= int(a["install_sh"] or 0)
            c["minisig"] -= int(a["minisig"] or 0)
    return c


def estimate(c, rate):
    """Split c's downloads by the way devvm was installed: see the README's Reading the numbers."""
    script = round(c["install_sh"] * rate)
    return {"script": script, "upgrade": max(c["minisig"] - script, 0),
            "brew_manual": max(c["archive"] - c["sums"], 0), "total": c["archive"]}


def report(days):
    rows = read("downloads.csv")
    if not rows:
        sys.exit("report: no data: run stats.py ingest first")
    now = max(ts(r["snapshot_at"]) for r in rows)
    rels = releases(rows)
    rate, first = completion_rate(rows, rels, now)
    out =["# devvm adoption", "", "Latest snapshot: %s. install.sh completion rate: %.2f (from %s)." %
           (now.strftime("%Y-%m-%d %H:%M UTC"), rate, first), "",
           "| release | published | archives | install.sh | upgrades (devvm upgrade) | brew or manual | platforms |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    for pub, tag, pre in rels:
        c = subtract_annotations(counts_at(rows, tag, now), tag)
        e = estimate(c, rate)
        plat = ", ".join("%s %d" % kv for kv in sorted(c["platforms"].items()))
        out.append("| %s%s | %s | %d | %d | %d | %d | %s |" % (tag, " (pre)" if pre == "true" else "", pub[:10],
                   e["total"], c["install_sh"], e["upgrade"], e["brew_manual"], plat))
    for pub, tag, pre in rels:
        if pre == "true" or not pub:
            continue
        out += ["", "## %s: its first %d days" % (tag, days), "",
                "| day | archives | install.sh | minisig | upgrades (cumulative) |", "| --- | --- | --- | --- | --- |"]
        for d in range(1, days + 1):
            when = ts(pub) + timedelta(days=d)
            if when > now + timedelta(days=1):
                break
            c = counts_at(rows, tag, when)
            if c:
                out.append("| %d | %d | %d | %d | %d |" % (d, c["archive"], c["install_sh"], c["minisig"], estimate(c, rate)["upgrade"]))
    out += ["", "## Traffic by week", "", "| week of | views | clones |", "| --- | --- | --- |"]
    weeks = {}
    for kind in ("views", "clones"):
        for r in read("traffic_%s.csv" % kind):
            d = datetime.strptime(r["day"], "%Y-%m-%d")
            wk = (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")
            weeks.setdefault(wk, {"views": 0, "clones": 0})[kind] += int(r["count"])
    for wk in sorted(weeks)[-12:]:
        out.append("| %s | %d | %d |" % (wk, weeks[wk]["views"], weeks[wk]["clones"]))
    refs = read("referrers.csv")
    if refs:
        last = max(r["snapshot_date"] for r in refs)
        out += ["", "## Top referrers, the 14 days to %s" % last, ""]
        out += ["- %s: %s (%s unique)" % (r["referrer"], r["count"], r["uniques"])
                for r in sorted((r for r in refs if r["snapshot_date"] == last), key=lambda r: -int(r["count"]))]
    print("\n".join(out))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest")
    i.add_argument("dir")
    i.add_argument("--label", default="scheduled")
    r = sub.add_parser("report")
    r.add_argument("--days", type=int, default=14)
    a = p.parse_args()
    if a.cmd == "ingest":
        if not re.fullmatch(r"[A-Za-z0-9 ._-]{1,40}", a.label):
            sys.exit("ingest: a label is 1 to 40 letters, digits, spaces, dots, dashes or underscores")
        ingest(a.dir, a.label)
    else:
        report(a.days)


if __name__ == "__main__":
    main()
