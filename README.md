# devvm stats

How many people install and upgrade [devvm](https://github.com/devvmhq/devvm), counted every day and published at **[stats.devvm.dev](https://stats.devvm.dev/)**.

GitHub keeps two kinds of numbers for devvm. The first is each release's download count for each of its files, a running total. The second is the repo's traffic: views and clones by day, the top 10 referrers and the top 10 pages, which GitHub keeps for only 14 days. Once a day, a workflow in this repo reads both and adds them to CSV files in [`data/`](data/), so the history grows past GitHub's 14 days. Then it builds the site from those files. The first data point is a snapshot taken by hand on 8 November 2026, before devvm 0.1.1.

devvm itself sends nothing to anyone: these numbers are only what GitHub already counts.

## How the numbers are counted

A download count says only that a file was downloaded, but each way of installing devvm downloads a different set of a release's files:

| How | install.sh | archive | SHA256SUMS | SHA256SUMS.minisig |
| --- | --- | --- | --- | --- |
| The install script (curl, then bash) | yes | yes | yes | yes |
| devvm upgrade | no | yes | yes | yes |
| Homebrew | no | yes | no | no |

So for each release:

- **New installs** are the install.sh downloads times the share of them that go on to install. That share, 0.79, is measured on devvm 0.1.0, the first release, which nobody could have upgraded to.
- **Upgrades** are the signature downloads, less the new installs, since only the install script and devvm upgrade download the signature.
- **Homebrew or manual** is the archive downloads, less the SHA256SUMS downloads. A brew install and a brew upgrade look the same.

Known test downloads, when devvm's maintainer checks a release, are listed in [`data/annotations.csv`](data/annotations.csv) and taken out.

These numbers can't tell how many people use devvm, which version anyone runs, Homebrew installs apart from upgrades, or unique visitors over more than GitHub's 14 days. [How it's counted](https://stats.devvm.dev/about.html) explains each one.

## Privacy

Every number is a total, with no IP addresses, user names or anything per person. A referrer that's a temporary or private host, such as a tunnel's, is stored only as "(a private or temporary host)", not by its name. The raw files GitHub returns aren't kept. The site has no analytics, no cookies and no scripts, and it loads nothing from anywhere else: its fonts and images are its own files, listed with their sources in [`site/brand/SOURCES`](site/brand/SOURCES).

## What's here

| Path | What |
| --- | --- |
| `data/*.csv` | the numbers: downloads per release and file at each snapshot, traffic by day, the top referrers and pages, annotations |
| `REPORT.md` | the same, as a markdown report, written with each snapshot |
| `scripts/stats.py` | `ingest DIR` merges GitHub's JSON into `data/`; `report` prints `REPORT.md` |
| `scripts/build_site.py` | `build OUT` writes the site from `data/` (stdlib Python, no JavaScript) |
| `scripts/card.py` | the social card with the current numbers, drawn pixel by pixel in devvm's four colours |
| `site/` | the page template, the CSS, the How it's counted page, the brand files and fonts |
| `.github/workflows/snapshot.yml` | the daily snapshot, then the site's build and its deploy to GitHub Pages |

`mise run lint` checks the workflows (actionlint, zizmor), the shell scripts (shellcheck) and the brand files' checksums, and runs the tests. `mise run preview` builds the site from `data/` and serves it on http://127.0.0.1:8000/.

## For the maintainer

- **After publishing a release,** take a labelled snapshot: `gh workflow run snapshot.yml --repo devvmhq/stats -f label="release v0.1.1"`.
- **After testing a release on your own machines,** add a line to `data/annotations.csv` with the downloads the tests made, written plainly with no machine names or addresses, for example "The maintainer's release check on four machines." Labelled snapshots before and after a test session (`-f label="before tests"`) give the exact numbers.
- **The token:** the workflow reads devvm's traffic with the GitHub App `devvmhq-stats`, installed on devvmhq/devvm with Administration: read and nothing else. Its Client ID is the variable `STATS_APP_CLIENT_ID`, and its private key is the secret `STATS_APP_PRIVATE_KEY` in the `stats` environment, which only `main` can use. Until the variable is set, the snapshot is skipped and only the site deploys. Rotate the key once a year: generate a new one on the App's page, run `gh secret set STATS_APP_PRIVATE_KEY --repo devvmhq/stats --env stats < key.pem`, run the workflow, then delete the old key.
- **When a snapshot fails,** the workflow opens the issue "Snapshots are failing". A day's traffic is lost once it's 14 days old.
- **When devvm's branding changes,** run `scripts/sync-brand.sh devvmhq/devvm COMMIT`, and `scripts/make-glyphs.sh` with devvm's Departure Mono OTF if the font changed. For a new Instrument Sans release, run `scripts/sync-brand.sh Instrument/instrument-sans COMMIT`.
- **Scheduled workflows** in a public repo stop after 60 days without activity. The daily commits keep it active, but if the site's "Updated" date stops moving, re-enable the workflow in the Actions tab.

## Licence

The data (`data/`, `REPORT.md`) and the site's text are dedicated to the public domain under [CC0 1.0](LICENSE-CC0). The code is under the [MIT license](LICENSE). The fonts in `site/brand/fonts/` are under the SIL Open Font License 1.1, with each one's licence beside it, and devvm's logo, icons and card template are devvm's, under its MIT license.
