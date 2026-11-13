#!/usr/bin/env python3
"""web-scraper-scheduler — fetch a page, extract data, watch for changes.

Scrapes a URL on demand or on a schedule, extracts the title, headings,
links and (optionally) elements matching a CSS selector, and reports when
the extracted content changes between runs.

Usage:
    python3 src/scraper.py --url https://example.com
    python3 src/scraper.py --url https://example.com --selector "h2"
    python3 src/scraper.py --url https://example.com --interval 60 --runs 3
    python3 src/scraper.py --config assets/config-example.yaml --interval 300
    python3 src/scraper.py --demo

Scheduling note: --interval runs the scraper in-process (good for a quick
watch). For a permanent schedule, use cron — see docs/USAGE.md.

Politeness is built in: robots.txt is checked before every fetch, a crawl
delay is honoured between requests, and a real User-Agent is sent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None

VERSION = "1.0.0"
USER_AGENT = "web-scraper-scheduler/1.0 (+https://example.com; polite scraper)"
DEFAULT_TIMEOUT = 15


# ---------------------------------------------------------------- parsing

class _FallbackParser(HTMLParser):
    """Stdlib-only extractor used when BeautifulSoup is not installed."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.headings = []
        self.links = []
        self._in_title = False
        self._heading_tag = None
        self._buf = ""

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
            self._buf = ""
        elif tag in ("h1", "h2", "h3"):
            self._heading_tag = tag
            self._buf = ""
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append({"text": "", "href": href})

    def handle_data(self, data):
        if self._in_title or self._heading_tag:
            self._buf += data

    def handle_endtag(self, tag):
        if tag == "title":
            self.title = self._buf.strip()
            self._in_title = False
        elif tag in ("h1", "h2", "h3") and self._heading_tag == tag:
            text = self._buf.strip()
            if text:
                self.headings.append({"level": tag, "text": text})
            self._heading_tag = None


def extract(html: str, base_url: str = "", selector: str | None = None) -> dict:
    """Extract title, headings, links (and selector matches) from HTML."""
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        headings = [
            {"level": tag.name, "text": tag.get_text(" ", strip=True)}
            for tag in soup.find_all(["h1", "h2", "h3"])
            if tag.get_text(strip=True)
        ]
        links = []
        for a in soup.find_all("a", href=True):
            links.append({
                "text": a.get_text(" ", strip=True)[:120],
                "href": urljoin(base_url, a["href"]),
            })
        result = {"title": title, "headings": headings, "links": links}
        if selector:
            result["selector"] = selector
            result["matches"] = [
                el.get_text(" ", strip=True)[:300]
                for el in soup.select(selector)
            ]
        return result

    # Fallback: no selector support without BeautifulSoup.
    if selector:
        raise RuntimeError(
            "CSS selectors need BeautifulSoup — install it with "
            "`pip install beautifulsoup4` (see requirements.txt)."
        )
    parser = _FallbackParser()
    parser.feed(html)
    links = [
        {"text": "", "href": urljoin(base_url, link["href"])}
        for link in parser.links
    ]
    return {"title": parser.title, "headings": parser.headings, "links": links}


def content_fingerprint(data: dict) -> str:
    """Stable hash of the extracted content, for change detection."""
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- fetching

def robots_allowed(url: str, user_agent: str = USER_AGENT) -> bool:
    """True if robots.txt allows fetching *url* (fail-open on any error)."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True  # robots.txt unreachable — do not block on that alone


def fetch(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    if requests is None:
        raise RuntimeError(
            "The 'requests' library is required — install it with "
            "`pip install -r requirements.txt`."
        )
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------- state

def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def diff_lines(old: dict, new: dict) -> dict:
    """Summarise what changed between two extraction results."""
    changes = {}
    for key in ("title", "headings", "links"):
        old_set = {json.dumps(v, sort_keys=True) for v in old.get(key, [])} \
            if isinstance(old.get(key), list) else {str(old.get(key, ""))}
        new_set = {json.dumps(v, sort_keys=True) for v in new.get(key, [])} \
            if isinstance(new.get(key), list) else {str(new.get(key, ""))}
        added, removed = new_set - old_set, old_set - new_set
        if added or removed:
            changes[key] = {"added": sorted(added)[:10], "removed": sorted(removed)[:10]}
    return changes


# ---------------------------------------------------------------- running

def scrape_target(url: str, selector: str | None, state: dict,
                  state_path: Path | None, html_override: str | None = None) -> dict:
    """Scrape one URL (or given HTML) and return the report dict."""
    if html_override is None:
        html = fetch(url)
    else:
        html = html_override
    data = extract(html, base_url=url, selector=selector)
    data["url"] = url
    fingerprint = content_fingerprint(data)
    report = {"url": url, "data": data, "fingerprint": fingerprint}

    if state_path is not None:
        previous = state.get(url)
        if previous is None:
            report["change"] = "new"
        elif previous.get("fingerprint") == fingerprint:
            report["change"] = "unchanged"
        else:
            report["change"] = "changed"
            report["diff"] = diff_lines(previous.get("data", {}), data)
        state[url] = {"fingerprint": fingerprint, "data": data}
        save_state(state_path, state)
    else:
        report["change"] = "not-tracked"
    return report


def print_report(report: dict, run_no: int | None = None) -> None:
    prefix = f"[run {run_no}] " if run_no else ""
    data = report["data"]
    print(f"{prefix}{report['url']}")
    print(f"{prefix}  Title: {data['title'] or '(none)'}")
    print(f"{prefix}  Headings: {len(data['headings'])}  Links: {len(data['links'])}")
    if "matches" in data:
        print(f"{prefix}  Selector '{data['selector']}': {len(data['matches'])} match(es)")
        for m in data["matches"][:5]:
            print(f"{prefix}    - {m}")
    for h in data["headings"][:5]:
        print(f"{prefix}  {h['level'].upper()}: {h['text']}")
    change = report["change"]
    if change == "new":
        print(f"{prefix}  Change: first run — baseline saved.")
    elif change == "unchanged":
        print(f"{prefix}  Change: unchanged since last run.")
    elif change == "changed":
        print(f"{prefix}  Change: CHANGED since last run!")
        for key, d in report.get("diff", {}).items():
            for item in d["added"]:
                print(f"{prefix}    + {key}: {item[:160]}")
            for item in d["removed"]:
                print(f"{prefix}    - {key}: {item[:160]}")
    print()


def load_targets_from_config(path: Path) -> list[dict]:
    """Load [{url, selector}] from a YAML config file."""
    import yaml  # PyYAML is a declared dependency of this project

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    targets = []
    for item in data.get("targets", []):
        targets.append({"url": item["url"], "selector": item.get("selector")})
    return targets


def run_demo() -> int:
    """Scrape the bundled sample page (no network) twice to show the flow."""
    sample = Path(__file__).resolve().parent.parent / "assets" / "sample-page.html"
    html = sample.read_text(encoding="utf-8")
    state: dict = {}
    state_path = Path("scraper-state.json")
    print("Demo: scraping the bundled sample page (no network needed).")
    print(f"Sample page: {sample}\n")
    report1 = scrape_target("file://sample-page.html", "h2", state, state_path,
                            html_override=html)
    print_report(report1, run_no=1)
    report2 = scrape_target("file://sample-page.html", "h2", state, state_path,
                            html_override=html)
    print_report(report2, run_no=2)
    print("Demo complete — second run reports 'unchanged' (change detection works).")
    print(f"State file left at: {state_path.resolve()} (delete it to reset the baseline).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scraper.py",
        description="Fetch a page, extract its title/headings/links, and watch "
                    "for changes on a schedule.",
        epilog="For a permanent schedule use cron — see docs/USAGE.md. "
               "robots.txt is always checked first; use --ignore-robots only "
               "on pages you own or have permission to scrape.",
    )
    parser.add_argument("--url", help="page to scrape")
    parser.add_argument("--selector", help="CSS selector to extract (needs BeautifulSoup)")
    parser.add_argument("--config", type=Path,
                        help="YAML file with a list of targets (url + selector)")
    parser.add_argument("--interval", type=float, default=0,
                        help="seconds between repeated runs (0 = run once)")
    parser.add_argument("--runs", type=int, default=None,
                        help="how many runs with --interval (default: 3)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="polite crawl delay between requests in seconds (default: 1)")
    parser.add_argument("--state", type=Path, default=None,
                        help="JSON file storing baselines for change detection")
    parser.add_argument("--output", type=Path,
                        help="write the full JSON report to this file")
    parser.add_argument("--ignore-robots", action="store_true",
                        help="skip the robots.txt check (only for pages you may scrape)")
    parser.add_argument("--demo", action="store_true",
                        help="scrape the bundled sample page (no network needed)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.demo:
        return run_demo()

    targets: list[dict] = []
    if args.config:
        if not args.config.is_file():
            print(f"Error: config file not found: {args.config}", file=sys.stderr)
            return 2
        targets = load_targets_from_config(args.config)
        if not targets:
            print(f"Error: no targets found in {args.config}", file=sys.stderr)
            return 2
    elif args.url:
        targets = [{"url": args.url, "selector": args.selector}]
    else:
        print("Error: give --url, --config, or --demo.", file=sys.stderr)
        return 2

    if args.interval < 0:
        print("Error: --interval must be 0 or more.", file=sys.stderr)
        return 2
    runs = args.runs if args.runs is not None else (3 if args.interval > 0 else 1)
    if runs < 1:
        print("Error: --runs must be 1 or more.", file=sys.stderr)
        return 2

    state_path = args.state
    if state_path is None and args.interval > 0:
        state_path = Path("scraper-state.json")
    state = load_state(state_path) if state_path is not None else {}

    all_reports = []
    try:
        for run_no in range(1, runs + 1):
            for target in targets:
                url = target["url"]
                if not args.ignore_robots and not robots_allowed(url):
                    print(f"Skipping {url}: disallowed by robots.txt "
                          f"(use --ignore-robots only if you may scrape it).")
                    continue
                try:
                    report = scrape_target(url, target.get("selector"), state,
                                           state_path)
                except Exception as exc:
                    print(f"Error scraping {url}: {exc}", file=sys.stderr)
                    continue
                all_reports.append(report)
                print_report(report, run_no=run_no if runs > 1 else None)
                time.sleep(args.delay)
            if run_no < runs:
                print(f"Waiting {args.interval:g}s until run {run_no + 1}… "
                      f"(Ctrl+C to stop)\n")
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped by user.")

    if args.output and all_reports:
        args.output.write_text(json.dumps(all_reports, indent=2), encoding="utf-8")
        print(f"Full JSON report written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
