#!/usr/bin/env bash
# og.sh: render site/og/card.html to site/og.png, 1200 by 630, with Chrome (macOS's or CHROME).
# Run by hand after editing the card or after scripts/sync-brand.sh changes the logo; commit og.png.
set -euo pipefail
cd "$(dirname -- "$0")/.."
chrome=${CHROME:-"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"}
"$chrome" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --window-size=1200,630 --screenshot="$PWD/site/og.png" "file://$PWD/site/og/card.html" >/dev/null 2>&1
echo "og.sh: wrote site/og.png"
