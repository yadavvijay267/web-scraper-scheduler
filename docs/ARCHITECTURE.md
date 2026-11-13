# Architecture — Web Scraper with Scheduling

Single-file tool: `src/scraper.py`.

## Flow

```
CLI args (argparse)
  ├─ --demo → run_demo()              scrape bundled sample page twice, offline
  └─ else   → load targets (--url or --config YAML)
               └─ for each run (1, or N with --interval):
                    for each target:
                      robots_allowed()      urllib.robotparser, fail-open
                      fetch()               requests + User-Agent + timeout
                      extract()             BeautifulSoup (or stdlib fallback)
                        ├─ title, h1–h3, links (resolved to absolute)
                        └─ selector matches (BeautifulSoup only)
                      content_fingerprint() SHA-256 of canonical JSON
                      compare with state file → new / unchanged / changed
                      diff_lines()            added/removed per field
                      print_report()          human summary on stdout
                    sleep(--delay) between requests, --interval between runs
               └─ --output → full JSON report
```

## Key decisions

- **Change detection hashes extracted content, not raw HTML.** A page
  whose ads or timestamps change but whose headings/links don't is
  correctly reported as unchanged.
- **State is a plain JSON file** (`scraper-state.json`), not SQLite —
  human-readable, easy to inspect and delete to reset a baseline.
- **BeautifulSoup is preferred but optional.** Without it, a stdlib
  `html.parser` fallback still extracts title/headings/links; only CSS
  selectors require BeautifulSoup (the error message says so).
- **robots.txt failures are fail-open.** If robots.txt itself can't be
  fetched, the scrape proceeds — blocking on an unreachable robots file
  would make the tool useless on flaky networks.
- **In-process `--interval` vs cron.** `--interval` is a convenience for
  short watches; `docs/USAGE.md` documents cron for permanent schedules,
  because a long-lived process is the wrong tool for that job.

## Tests

`tests/test_scraper.py` runs fully offline: extraction from the bundled
sample page and inline HTML, selector matching, fingerprint stability,
and the new → unchanged → changed state machine using a temp state file.
Run with `python3 -m pytest tests/ -v`.
