"""The social card, 1200 by 630, with the current numbers, drawn in pure Python (stdlib only).

It starts from devvm's own card template (site/brand/og-template.png: the logo, the lime bar), as
devvm.dev's page cards do, and draws Departure Mono from site/og/glyphs.txt with every font pixel a whole
square of screen pixels, so there's no antialiasing and the card has exactly devvm's four colours. It's
written as a 4-colour indexed PNG. No network, no secrets, no Chrome.
"""

import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "..", "site")
W, H = 1200, 630
BLACK, LIME, TEXT, GREY = 0, 1, 2, 3
PALETTE = [(0, 0, 0), (0x7F, 0xFF, 0x00), (0xEE, 0xEE, 0xEE), (0x8F, 0x93, 0xA2)]


def read_png(path):
    """An 8-bit RGB or RGBA, non-interlaced PNG's pixels, as rows of (r, g, b)."""
    with open(path, "rb") as f:
        data = f.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat, w = 8, b"", 0
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            assert depth == 8 and ctype in (2, 6) and not interlace, "unsupported PNG"
            bpp = 3 if ctype == 2 else 4
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    raw, stride, rows, prev = zlib.decompress(idat), w * bpp, [], bytearray(w * bpp)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], (prev[i - bpp] if i >= bpp else 0)
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append([tuple(line[x * bpp:x * bpp + 3]) for x in range(w)])
        prev = line
    return rows


def write_png(path, px):
    """px: rows of palette indexes, written as an indexed PNG."""
    raw = b"".join(b"\x00" + bytes(r) for r in px)
    chunk = lambda k, b: struct.pack(">I", len(b)) + k + b + struct.pack(">I", zlib.crc32(k + b) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 3, 0, 0, 0))
           + chunk(b"PLTE", b"".join(bytes(c) for c in PALETTE))
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return png


def glyphs():
    g, rows, cur, height = {}, [], None, 0
    with open(os.path.join(SITE, "og", "glyphs.txt"), encoding="utf-8") as f:
        lines = f.read().splitlines()
    for line in lines:
        line = line.rstrip("\n")
        if line.startswith("height "):
            height = int(line.split()[1])
        elif line.startswith("glyph "):
            cur = int(line.split()[1])
            g[cur] = rows = []
        elif cur is not None and line and line[0] in ".#":
            rows.append(line)
    assert len(g) == 95 and all(len(r) == height for r in g.values()), "glyphs.txt is incomplete"
    return g


class Card:
    def __init__(self, template):
        index = {c: i for i, c in enumerate(PALETTE)}
        # The template's colours are devvm's four; anything else (there is none) becomes black.
        self.px = [[index.get(c, BLACK) for c in row] for row in read_png(template)]
        self.g = glyphs()

    def rect(self, x, y, w, h, color):
        for yy in range(max(y, 0), min(y + h, H)):
            row = self.px[yy]
            for xx in range(max(x, 0), min(x + w, W)):
                row[xx] = color

    def text(self, s, x, y, size, color):
        """s at size (a multiple of 11), its 15-row cell's top at y; returns the width drawn."""
        k = size // 11
        for i, ch in enumerate(s):
            for r, line in enumerate(self.g.get(ord(ch), self.g[63])):
                for c, p in enumerate(line):
                    if p == "#":
                        self.rect(x + (i * 7 + c) * k, y + r * k, k, k, color)
        return len(s) * 7 * k

    def frame(self, x, y, w, h, t, color):
        self.rect(x, y, w, t, color)
        self.rect(x, y + h - t, w, t, color)
        self.rect(x, y, t, h, color)
        self.rect(x + w - t, y, t, h, color)

    def line(self, x0, y0, x1, y1, t, color):
        """A t-pixel square pen along the line, so its edges stay hard."""
        n = max(abs(x1 - x0), abs(y1 - y0), 1)
        for i in range(n + 1):
            self.rect(round(x0 + (x1 - x0) * i / n) - t // 2, round(y0 + (y1 - y0) * i / n) - t // 2, t, t, color)


def number_size(s, width):
    """The largest size in 11px steps up to 66 that fits s in width."""
    for size in (66, 55, 44, 33):
        if len(s) * 7 * size // 11 <= width:
            return size
    return 22


def render(path, stats_tiles, spark):
    """stats_tiles: two (label, number, sub) tiles; spark: [(x, y)] for the third, downloads over time."""
    c = Card(os.path.join(SITE, "brand", "og-template.png"))
    c.rect(80, 530, 400, 40, BLACK)  # the template's devvm.dev, replaced by this site's address
    c.text("STATS", 88, 200, 22, LIME)
    c.text("Who installs devvm", 88, 236, 44, TEXT)
    boxes = [(88, 330), (440, 330), (792, 320)]
    top, h = 316, 196
    for (x, w), tile in zip(boxes, list(stats_tiles) + [None]):
        c.frame(x, top, w, h, 2, GREY)
        if tile:
            label, num, sub = tile
            c.text(label, x + 22, top + 18, 22, GREY)
            size = number_size(num, w - 44)
            c.text(num, x + 22, top + 64 + (66 - size) // 2, size, TEXT)
            c.text(sub, x + 22, top + 150, 22, GREY)
    x, w = boxes[2]
    c.text("OVER TIME", x + 22, top + 18, 22, GREY)
    if spark:
        left, right, y0, y1 = x + 26, x + w - 26, top + 172, top + 66
        xs, ys = [p[0] for p in spark], [p[1] for p in spark]
        sx = (right - left) / ((max(xs) - min(xs)) or 1)
        sy = (y0 - y1) / (max(ys) or 1)
        # One snapshot is one point, at the right end, where the newest point always is.
        pts = [(round(left + (px - min(xs)) * sx) if len(xs) > 1 else right, round(y0 - py * sy)) for px, py in spark]
        c.rect(left - 4, y0 + 4, right - left + 8, 2, GREY)  # the baseline
        for a, b in zip(pts, pts[1:]):
            c.line(a[0], a[1], b[0], b[1], 4, LIME)
        c.rect(pts[-1][0] - 5, pts[-1][1] - 5, 10, 10, LIME)  # the newest point
    c.text("stats.devvm.dev", 88, 538, 22, LIME)
    return write_png(path, c.px)
