"""Tests for scraper.py — run with:  python3 -m pytest tests/ -v

Parsing and change-detection tests run entirely offline against the
bundled sample page and inline HTML strings. No network is used.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import scraper


SAMPLE_HTML = (Path(__file__).resolve().parent.parent / "assets" / "sample-page.html").read_text(encoding="utf-8")


def test_extract_title_and_headings():
    data = scraper.extract(SAMPLE_HTML, base_url="https://example.com")
    assert data["title"] == "Sample News Page — Demo Only"
    texts = [h["text"] for h in data["headings"]]
    assert "Demo Daily — Sample Page" in texts
    assert "Headline: Local Library Reopens" in texts
    assert "Headline: Market Day Returns" in texts
    assert "Weather" in texts


def test_extract_links_resolves_relative_urls():
    data = scraper.extract(SAMPLE_HTML, base_url="https://example.com/news/")
    hrefs = [l["href"] for l in data["links"]]
    assert "https://example.com/library" in hrefs
    assert "https://example.com/about" in hrefs
    assert len(hrefs) == 3


def test_extract_selector_matches():
    data = scraper.extract(SAMPLE_HTML, selector="h2")
    assert data["selector"] == "h2"
    assert len(data["matches"]) == 2
    assert data["matches"][0].startswith("Headline: Local Library")


def test_extract_empty_page():
    data = scraper.extract("<html><body></body></html>")
    assert data["title"] == ""
    assert data["headings"] == []
    assert data["links"] == []


def test_fingerprint_is_stable_and_content_sensitive():
    a = scraper.extract(SAMPLE_HTML)
    b = scraper.extract(SAMPLE_HTML)
    assert scraper.content_fingerprint(a) == scraper.content_fingerprint(b)
    changed = scraper.extract(SAMPLE_HTML.replace("Library Reopens", "Library Closes"))
    assert scraper.content_fingerprint(a) != scraper.content_fingerprint(changed)


def test_change_detection_new_then_unchanged_then_changed(tmp_path):
    state_path = tmp_path / "state.json"
    state = scraper.load_state(state_path)
    r1 = scraper.scrape_target("file://sample", None, state, state_path, html_override=SAMPLE_HTML)
    assert r1["change"] == "new"
    r2 = scraper.scrape_target("file://sample", None, state, state_path, html_override=SAMPLE_HTML)
    assert r2["change"] == "unchanged"
    edited = SAMPLE_HTML.replace("Headline: Market Day Returns", "Headline: Market Day Cancelled")
    r3 = scraper.scrape_target("file://sample", None, state, state_path, html_override=edited)
    assert r3["change"] == "changed"
    assert "headings" in r3["diff"] or "links" in r3["diff"] or "title" in r3["diff"]


def test_state_file_is_written_and_reloadable(tmp_path):
    state_path = tmp_path / "state.json"
    state = scraper.load_state(state_path)
    scraper.scrape_target("file://sample", None, state, state_path, html_override=SAMPLE_HTML)
    assert state_path.exists()
    reloaded = scraper.load_state(state_path)
    assert "file://sample" in reloaded


def test_diff_lines_reports_added_and_removed():
    old = {"title": "T", "headings": [{"level": "h1", "text": "A"}], "links": []}
    new = {"title": "T", "headings": [{"level": "h1", "text": "B"}], "links": []}
    diff = scraper.diff_lines(old, new)
    assert "headings" in diff
    assert len(diff["headings"]["added"]) == 1
    assert len(diff["headings"]["removed"]) == 1


def test_diff_lines_empty_when_identical():
    data = {"title": "T", "headings": [], "links": []}
    assert scraper.diff_lines(data, data) == {}


def test_config_loading(tmp_path):
    config = tmp_path / "targets.yaml"
    config.write_text("targets:\n  - url: https://example.com\n    selector: h1\n", encoding="utf-8")
    targets = scraper.load_targets_from_config(config)
    assert targets == [{"url": "https://example.com", "selector": "h1"}]
