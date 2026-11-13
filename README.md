# Web Scraper with Scheduling

Fetch a page, extract its title, headings, links and CSS-selector matches,
and watch it for changes — on demand, on a repeat interval, or on a cron
schedule.

![Status](https://img.shields.io/badge/status-working-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)

## Features

- **Extract** — title, `h1`–`h3` headings, all links (relative URLs
  resolved), plus any CSS selector you pass with `--selector`.
- **Change detection** — a fingerprint of the extracted content is saved
  to `scraper-state.json`; later runs report `new` / `unchanged` /
  `changed`, with an added/removed summary of what changed.
- **Scheduled runs** — `--interval <seconds>` repeats the scrape in
  process; for a permanent schedule, use cron (see
  [docs/USAGE.md](docs/USAGE.md)).
- **Config-driven targets** — watch many pages from one YAML file
  (`assets/config-example.yaml`).
- **Polite by design** — checks `robots.txt` before every fetch, sends a
  real User-Agent, and honours a crawl delay (`--delay`, default 1s).
- **Demo mode** (`--demo`) — scrapes the bundled sample page with no
  network, twice, so you can see change detection work.
- **JSON output** — `--output report.json` writes the full report.

## Tech Stack

- Python 3.9+, `requests`, `BeautifulSoup4`
- `PyYAML` for config files
- `pytest` for tests (dev only)
- Works without BeautifulSoup too (stdlib `html.parser` fallback —
  selector matching then needs BeautifulSoup)

## How to Run

```bash
# Install dependencies
pip install -r requirements.txt

# See all options
python3 src/scraper.py --help

# Scrape a page once
python3 src/scraper.py --url https://example.com

# Extract just the h2 headings
python3 src/scraper.py --url https://example.com --selector "h2"

# Repeat every 60 seconds, 3 times, tracking changes
python3 src/scraper.py --url https://example.com --interval 60 --runs 3

# Watch every target in a config file every 5 minutes
python3 src/scraper.py --config assets/config-example.yaml --interval 300

# No network? Try the offline demo
python3 src/scraper.py --demo
```

See [docs/USAGE.md](docs/USAGE.md) for the full usage guide, the cron
setup, and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how it works.

## Screenshots

`screenshots/demo-output.txt` shows a real `--demo` run, and
[screenshots/SCREENSHOTS.md](screenshots/SCREENSHOTS.md) explains where
to put terminal screenshots.

## Tests

```bash
python3 -m pytest tests/ -v
```

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Clamor.
