# Usage — Web Scraper with Scheduling

## Basic usage

```
python3 src/scraper.py --url <URL> [options]
```

| Flag | What it does |
|---|---|
| `--url URL` | Page to scrape |
| `--selector CSS` | Also extract elements matching this CSS selector |
| `--config FILE` | YAML file with a list of targets (url + selector) |
| `--interval SECONDS` | Repeat the scrape every N seconds (0 = run once) |
| `--runs N` | How many runs with `--interval` (default: 3 when interval is set, else 1) |
| `--delay SECONDS` | Polite pause between requests (default: 1) |
| `--state FILE` | JSON file for change-detection baselines (default with `--interval`: `scraper-state.json`) |
| `--output FILE` | Write the full JSON report to this file |
| `--ignore-robots` | Skip the robots.txt check (only for pages you may scrape) |
| `--demo` | Scrape the bundled sample page offline, twice |
| `--help` | Show all options (exits 0) |

## Config file

```yaml
targets:
  - url: https://example.com
    selector: h1
  - url: https://example.com/prices
    selector: ".price"
```

```bash
python3 src/scraper.py --config assets/config-example.yaml --interval 300 --runs 2
```

## Change detection

The first run for a URL saves a SHA-256 fingerprint of the extracted
content plus the data itself in the state file (`scraper-state.json` by
default when `--interval` is used, or the path given by `--state`).
Later runs compare and report:

- `new` — first run, baseline saved
- `unchanged` — fingerprint matches
- `changed` — fingerprint differs, with an added/removed summary per
  field (title, headings, links)

Delete the state file to reset a baseline.

## Scheduling with cron (permanent schedule)

`--interval` is for quick watches inside one process. For a schedule
that survives reboots, use cron. Example — check a page every hour and
append the summary to a log:

```cron
# crontab -e
0 * * * * cd /home/clamor/web-scraper-scheduler && /usr/bin/python3 src/scraper.py --url https://example.com --state scraper-state.json --output /tmp/scraper-report.json >> scraper.log 2>&1
```

Tips:

- Use absolute paths in cron (it runs with a minimal environment).
- Keep `--interval 0` (the default) in cron — cron itself is the scheduler.
- A daily 9am run: `0 9 * * * …`
- Check the log after the first scheduled run to confirm it fired.

## Politeness rules (built in, documented as a feature)

1. **robots.txt is checked** before every fetch. A disallowed URL is
   skipped with a message. `--ignore-robots` exists only for pages you
   own or have permission to scrape.
2. **Crawl delay** — `--delay` (default 1s) pauses between requests, and
   `--interval` spaces out repeated runs.
3. **Identifiable User-Agent** — `web-scraper-scheduler/1.0` is sent on
   every request.

Scrape public pages at a reasonable rate, respect terms of service, and
never use this to collect personal data.
