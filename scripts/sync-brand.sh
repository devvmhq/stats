#!/usr/bin/env bash
# sync-brand.sh REPO COMMIT: copy REPO's files in site/brand/SOURCES (devvmhq/devvm, or
# Instrument/instrument-sans) again from github.com at COMMIT, and rewrite their lines in SOURCES with
# the new commit and SHA-256s. Run it when devvm's branding or a font changes; review git diff, commit.
# sync-brand.sh --check: each file in site/brand matches its SHA-256 in SOURCES (mise run lint).
set -euo pipefail
cd "$(dirname -- "$0")/../site/brand"

rows() { grep -E '^[0-9a-f]{64}  ' SOURCES; }
check() { rows | awk '{ print $1 "  " $2 }' | shasum -a 256 -c --quiet -; }
if [[ ${1:-} == --check ]]; then
  check
  exit
fi

[[ $# -eq 2 && $2 =~ ^[0-9a-f]{40}$ ]] || {
  echo "usage: sync-brand.sh REPO COMMIT (a full 40-character commit), or sync-brand.sh --check" >&2
  exit 2
}
repo=$1 commit=$2
rows | awk -v r="$repo" '$3 == r { found = 1 } END { exit !found }' || {
  echo "sync-brand: SOURCES has no files from $repo" >&2
  exit 2
}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
sed -n '/^#/p' SOURCES >"$tmp/SOURCES"
while read -r sum name from at path; do
  if [[ $from == "$repo" ]]; then
    # Upstream paths can hold [ and ], as a variable font's name does.
    url="https://raw.githubusercontent.com/$from/$commit/$(printf '%s' "$path" | sed 's/\[/%5B/g; s/\]/%5D/g')"
    mkdir -p "$tmp/files/$(dirname -- "$name")"
    curl --proto '=https' -fsSL -o "$tmp/files/$name" "$url"
    sum=$(shasum -a 256 "$tmp/files/$name" | cut -c1-64) at=$commit
  fi
  echo "$sum  $name  $from  $at  $path" >>"$tmp/SOURCES"
done < <(rows)
cp -R "$tmp/files/." .
mv "$tmp/SOURCES" SOURCES
check
echo "sync-brand: $repo's files are at ${commit:0:12}; review git diff, then commit"
