import json
import os
import re
import struct
import tempfile
import unittest

import stats


def release(tag, counts, pre=False, published="2026-11-06T16:23:11Z"):
    return {"tag_name": tag, "prerelease": pre, "draft": False, "published_at": published,
            "assets": [{"name": n, "download_count": c} for n, c in counts.items()]}


class StatsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        stats.DATA = os.path.join(self.tmp.name, "data")
        self.raw = os.path.join(self.tmp.name, "raw")
        os.makedirs(self.raw)

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, name, data):
        for f in os.listdir(self.raw):
            os.remove(os.path.join(self.raw, f))
        with open(os.path.join(self.raw, name), "w") as f:
            json.dump(data, f)

    def test_kind_of(self):
        self.assertEqual(stats.kind_of("devvm-0.2.0-rc.1-linux-arm64.tar.gz"), ("archive", "linux", "arm64"))
        self.assertEqual(stats.kind_of("devvm-0.1.0.tar.gz"), ("source", "", ""))
        self.assertEqual(stats.kind_of("SHA256SUMS.minisig"), ("minisig", "", ""))

    def test_ingest_twice_changes_nothing(self):
        self.put("releases-2026-11-08T183024Z.json", [release("v0.1.0", {"install.sh": 3})])
        stats.ingest(self.raw, "baseline")
        before = stats.read("downloads.csv")
        stats.ingest(self.raw, "baseline")
        self.assertEqual(stats.read("downloads.csv"), before)

    def test_unchanged_release_skipped(self):
        self.put("releases-2026-11-08T183024Z.json", [release("v0.1.0", {"install.sh": 3})])
        stats.ingest(self.raw, "baseline")
        self.put("releases-2026-11-09T061700Z.json", [[release("v0.1.0", {"install.sh": 3})]])
        stats.ingest(self.raw, "scheduled")
        self.assertEqual(len(stats.read("downloads.csv")), 1)

    def test_older_traffic_never_wins(self):
        day = {"timestamp": "2026-11-07T00:00:00Z", "count": 9, "uniques": 4}
        self.put("views-2026-11-09T061700Z.json", {"count": 9, "uniques": 4, "views": [day]})
        stats.ingest(self.raw, "scheduled")
        self.put("views-2026-11-08T183024Z.json", {"count": 5, "uniques": 2, "views": [dict(day, count=5)]})
        stats.ingest(self.raw, "baseline")
        self.assertEqual(stats.read("traffic_views.csv")[0]["count"], "9")

    def test_private_referrers_merged(self):
        self.put("referrers-2026-11-08T183024Z.json", [
            {"referrer": "a-b-c.trycloudflare.com", "count": 1, "uniques": 1},
            {"referrer": "192.168.1.4", "count": 2, "uniques": 1},
            {"referrer": "t.co", "count": 5, "uniques": 5}])
        stats.ingest(self.raw, "baseline")
        got = {r["referrer"]: r["count"] for r in stats.read("referrers.csv")}
        self.assertEqual(got, {"(a private or temporary host)": "3", "t.co": "5"})

    def test_site_escapes_and_has_no_scripts(self):
        import build_site
        self.put("releases-2026-11-08T183024Z.json", [release("v0.1.0", {"install.sh": 3, "SHA256SUMS.minisig": 2})])
        stats.ingest(self.raw, "baseline")
        self.put("referrers-2026-11-08T183024Z.json", [{"referrer": "<script>x</script>.example", "count": 1, "uniques": 1}])
        stats.ingest(self.raw, "baseline")
        out = os.path.join(self.tmp.name, "site")
        build_site.build(out, "")
        for name, _ in build_site.PAGES:
            with open(os.path.join(out, name), encoding="utf-8") as f:
                text = f.read()
            self.assertIn("Content-Security-Policy", text)
            self.assertNotIn("<script", text)

    def built_card(self):
        import build_site
        self.put("releases-2026-11-08T183024Z.json", [release("v0.1.0", {
            "devvm-0.1.0-darwin-arm64.tar.gz": 9, "install.sh": 3, "SHA256SUMS": 3, "SHA256SUMS.minisig": 2})])
        stats.ingest(self.raw, "baseline")
        out = os.path.join(self.tmp.name, "site")
        build_site.build(out, "")
        with open(os.path.join(out, "index.html"), encoding="utf-8") as f:
            name = re.search(r'og:image" content="https://stats.devvm.dev/(og-[0-9a-f]{12}\.png)"', f.read())
        self.assertTrue(name, "index.html names a content-hashed card")
        with open(os.path.join(out, name.group(1)), "rb") as f:
            return f.read()

    def test_card_is_four_colours(self):
        png = self.built_card()
        width, height, depth, ctype = struct.unpack(">IIBB", png[16:26])
        self.assertEqual((width, height, depth, ctype), (1200, 630, 8, 3))  # indexed
        plte = png.index(b"PLTE")
        self.assertEqual(struct.unpack(">I", png[plte - 4:plte])[0], 12)  # four RGB entries

    def test_card_falls_back(self):
        import card
        saved = card.render
        card.render = lambda *a: 1 / 0
        try:
            png = self.built_card()
        finally:
            card.render = saved
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "og.png"), "rb") as f:
            self.assertEqual(png, f.read())


if __name__ == "__main__":
    unittest.main()
