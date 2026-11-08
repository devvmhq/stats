#!/usr/bin/env bash
# make-glyphs.sh FONT.otf: write site/og/glyphs.txt, Departure Mono's printable ASCII as 1-bit pixels,
# which scripts/card.py draws the social card with. Departure Mono is a pixel font: at 11px each glyph is a
# 7 by 11 grid of whole pixels, so rendering it there without antialiasing loses nothing, and the card
# scales those pixels by whole numbers (22, 33, 44, 66px), as devvm.dev's cards use it.
# Run by hand with ImageMagick (magick) when the font changes; the build itself needs only Python.
# FONT: devvm's docs/assets/fonts/departure-mono/DepartureMono-Regular.otf at site/brand/SOURCES's commit.
set -euo pipefail
font=${1:?usage: make-glyphs.sh DepartureMono-Regular.otf}
cd "$(dirname -- "$0")/.."
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
chars=$(printf '%s' ' !"#$%&'"'"'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvwxyz{|}~')
# label: reads @ and \ specially, so the text goes through a file.
printf '%s' "$chars" >"$tmp/chars.txt"
magick -density 72 -background black -fill white -font "$font" -pointsize 11 +antialias \
  "label:@$tmp/chars.txt" -depth 8 gray:"$tmp/g.raw"
height=$(magick -density 72 -font "$font" -pointsize 11 +antialias "label:@$tmp/chars.txt" -format %h info:)
{
  echo "# Departure Mono's glyphs at 11px, 7 pixels wide, from scripts/make-glyphs.sh."
  echo "# font sha256 $(shasum -a 256 "$font" | cut -c1-64)"
  echo "height $height"
  python3 -I - "$tmp/g.raw" "$height" "$chars" <<'EOF'
import sys
raw, h, chars = open(sys.argv[1], "rb").read(), int(sys.argv[2]), sys.argv[3]
w = len(raw) // h
for i, c in enumerate(chars):
    print("glyph %d" % ord(c))
    for y in range(h):
        print("".join("#" if raw[y * w + i * 7 + x] > 127 else "." for x in range(7)))
EOF
} >site/og/glyphs.txt
echo "make-glyphs.sh: wrote site/og/glyphs.txt (${#chars} glyphs, $height rows)"
