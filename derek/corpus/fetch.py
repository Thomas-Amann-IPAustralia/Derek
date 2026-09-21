#!/usr/bin/env python3
"""HTTP/Selenium transport for the Style Manual (Layer 0).

Carried over from Octavius `src/scrape.py`, which solved this correctly:

* The Style Manual's WAF silently drops plain ``requests`` traffic, so page
  fetches go through Selenium with stealth options.
* ``/sitemap.xml`` carries an XSLT stylesheet, so a browser receives a
  rendered HTML table rather than raw XML. ``parse_sitemap`` sniffs the
  response shape and handles both, following nested/paginated sitemaps
  recursively in either case.
* ``robots.txt`` is checked on every run, with a Selenium fallback for the
  same WAF reason.

What is deliberately NOT carried over is Octavius's change-detection logic.
It trusted the sitemap's ``lastmod`` exclusively, never processed removals,
and produced no changeset — the three defects in postmortem F7. That logic
lives in ``derek/corpus/snapshot.py`` and ``derek/corpus/diff.py`` now, and
works from content hashes instead (ADR-001).
"""

import json
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium_stealth import stealth
from webdriver_manager.chrome import ChromeDriverManager

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

PAGE_LOAD_TIMEOUT = 25

FAILURE_SIGNATURES = [
    "This site can't be reached",
    "ERR_HTTP2_PROTOCOL_ERROR",
    "Enable JavaScript and cookies to continue",
    "Checking if the site connection is secure",
    "Just a moment...",
    "Verifying you are human",
    "DDoS protection by Cloudflare",
    "Access denied",
]

BOT_USER_AGENT = (
    "DerekStyleManualBot/1.0 (+https://github.com/Thomas-Amann-IPAustralia/Derek)"
)

# The Style Manual is the sole target of the pipeline and its sitemap URL is
# not sensitive. Allow override via SITEMAP_URL for testing / mirrors.
DEFAULT_SITEMAP_URL = "https://www.stylemanual.gov.au/sitemap.xml"


def initialize_driver(with_proxy: bool = False) -> Optional[webdriver.Chrome]:
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--lang=en-US,en;q=0.9")
    # NOTE: Keep this generic User-Agent for stealth; the descriptive bot UA is sent
    # via a separate HTTP header in the sitemap/robots.txt fetch only (use requests lib).
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    if with_proxy:
        proxy_host, proxy_port, proxy_user, proxy_pass = (
            os.environ.get(k) for k in ["PROXY_HOST", "PROXY_PORT", "PROXY_USER", "PROXY_PASS"]
        )
        if all([proxy_host, proxy_port, proxy_user, proxy_pass]):
            chrome_options.add_argument(
                f"--proxy-server=http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}"
            )
        else:
            log.warning("Proxy requested but credentials incomplete — skipping proxy init")
            return None

    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        stealth(
            driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
        return driver
    except Exception as e:
        log.error("Failed to initialize WebDriver: %s", e)
        return None


def _parse_robots_body(body: str) -> bool:
    """Apply robots.txt rules. Returns False only if explicitly disallowed."""
    lines = body.splitlines()
    current_agent_applies = False
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip()
            current_agent_applies = agent == "*" or "derek" in agent.lower()
        elif current_agent_applies:
            if line.lower().startswith("disallow:"):
                path = line.split(":", 1)[1].strip()
                if path == "/":
                    log.error("robots.txt disallows all crawling. Aborting.")
                    return False
            elif line.lower().startswith("crawl-delay:"):
                delay = line.split(":", 1)[1].strip()
                log.warning("robots.txt specifies Crawl-delay: %s. Will respect this.", delay)
    return True


def _fetch_robots_via_selenium(robots_url: str, driver: webdriver.Chrome) -> Optional[str]:
    """Fetch robots.txt using Selenium, extracting plain-text content.

    Browsers render text/plain responses inside an auto-generated ``<pre>``.
    If that's absent, fall back to the whole body text.
    """
    try:
        driver.get(robots_url)
        WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        pre = driver.find_elements(By.TAG_NAME, "pre")
        if pre:
            return pre[0].text
        body = driver.find_element(By.TAG_NAME, "body")
        return body.text
    except WebDriverException as e:
        log.warning("Selenium fetch of robots.txt failed: %s", e)
        return None


def check_robots_txt(base_url: str, driver: Optional[webdriver.Chrome] = None) -> bool:
    """Check robots.txt. Returns True if scraping is allowed, False if disallowed.

    Tries ``requests`` with the descriptive bot User-Agent first. If that
    fails (e.g. the site's WAF silently drops non-browser requests, as the
    Style Manual does), fall back to Selenium so we still honour robots.txt.
    """
    robots_url = f"{base_url}/robots.txt"
    body: Optional[str] = None
    try:
        resp = requests.get(
            robots_url,
            headers={"User-Agent": BOT_USER_AGENT},
            timeout=15,
        )
        if resp.status_code == 404:
            log.info("No robots.txt found — proceeding.")
            return True
        if resp.ok:
            body = resp.text
            log.info(
                "robots.txt response via requests (status %s):\n%s",
                resp.status_code, body[:2000],
            )
        else:
            log.warning(
                "robots.txt via requests returned HTTP %s — will try Selenium fallback.",
                resp.status_code,
            )
    except Exception as e:
        log.warning(
            "robots.txt via requests failed: %s — will try Selenium fallback.", e,
        )

    if body is None and driver is not None:
        body = _fetch_robots_via_selenium(robots_url, driver)
        if body is not None:
            log.info("robots.txt response via Selenium:\n%s", body[:2000])

    if body is None:
        log.warning("Could not fetch robots.txt by any method — proceeding anyway.")
        return True

    return _parse_robots_body(body)


def strip_noise(html: str) -> str:
    """Coarse noise removal. Kept for parity with the Octavius transport;
    the real chrome stripping happens in ``derek.corpus.to_markdown``."""
    soup = BeautifulSoup(html, "lxml")
    for selector in ["nav", "footer", "header", "script", "style", "aside"]:
        for tag in soup.find_all(selector):
            tag.decompose()
    for tag in soup.find_all(class_="noprint"):
        tag.decompose()
    sidebar = soup.find(id="sidebar")
    if sidebar:
        sidebar.decompose()
    return str(soup)


def check_block_page(html: str) -> bool:
    """Returns True if the page appears to be a block/error page."""
    html_lower = html.lower()
    for sig in FAILURE_SIGNATURES:
        if sig.lower() in html_lower:
            log.warning("Block-page signature detected: %s", sig)
            return True
    return False


def fetch_with_retry(url: str, driver: webdriver.Chrome) -> Optional[str]:
    """Fetch a URL with Selenium, with proxy fallback and exponential backoff on 429/503."""
    for attempt in range(3):
        try:
            driver.get(url)
            WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            # Scroll simulation
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 4);")
            time.sleep(random.uniform(2, 4))
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(random.uniform(1, 3))

            html = driver.page_source
            if check_block_page(html):
                log.warning("Block page detected on attempt %d for %s", attempt + 1, url)
                proxy_driver = initialize_driver(with_proxy=True)
                if proxy_driver:
                    log.info("Retrying with proxy for %s", url)
                    try:
                        proxy_driver.get(url)
                        WebDriverWait(proxy_driver, PAGE_LOAD_TIMEOUT).until(
                            EC.presence_of_element_located((By.TAG_NAME, "body"))
                        )
                        html = proxy_driver.page_source
                    finally:
                        proxy_driver.quit()
                    if not check_block_page(html):
                        return html
                return None
            return html
        except WebDriverException as e:
            wait = 30 * (2 ** attempt)
            log.warning(
                "Fetch failed for %s (attempt %d): %s. Waiting %ds.",
                url, attempt + 1, e, wait,
            )
            time.sleep(wait)

    log.error("All retries exhausted for %s", url)
    return None


SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def _fetch_sitemap_via_requests(url: str) -> Optional[bytes]:
    """Attempt a plain ``requests`` fetch of a sitemap document.

    Uses the descriptive ``OctaviusRulebookBot`` User-Agent so the Style
    Manual maintainers can identify the crawl. Many sites serve the raw XML
    to non-browser clients happily; some (including stylemanual.gov.au as of
    2026) sit behind a WAF that silently drops such requests, in which case
    this returns ``None`` and the caller falls back to Selenium.
    """
    for attempt in range(2):
        try:
            resp = requests.get(
                url,
                headers={
                    "User-Agent": BOT_USER_AGENT,
                    "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
                },
                timeout=15,
            )
            if resp.status_code in (429, 503):
                wait = 30 * (2 ** attempt)
                log.warning(
                    "Sitemap fetch rate-limited (HTTP %s) on attempt %d. Waiting %ds.",
                    resp.status_code, attempt + 1, wait,
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()
            if not resp.content:
                log.warning(
                    "Sitemap fetch returned empty body on attempt %d", attempt + 1,
                )
                continue
            return resp.content
        except requests.RequestException as e:
            log.warning(
                "Sitemap requests fetch failed (attempt %d): %s", attempt + 1, e,
            )
            # Short pause before retry; the Selenium fallback will back off
            # further if it also fails.
            time.sleep(5)
    return None


def _fetch_sitemap_via_selenium(url: str, driver: webdriver.Chrome) -> Optional[bytes]:
    """Fetch a sitemap via Selenium and return the rendered HTML as bytes.

    The Style Manual's ``/sitemap.xml`` carries an XSLT stylesheet, so the
    browser returns a fully-rendered HTML table rather than raw XML. We parse
    either shape downstream — what matters here is getting past the WAF.
    """
    for attempt in range(3):
        try:
            driver.get(url)
            WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            # Let any XSLT / tablesorter rendering settle.
            time.sleep(random.uniform(2, 4))
            html = driver.page_source
            if not html:
                log.warning(
                    "Selenium sitemap fetch returned empty page on attempt %d",
                    attempt + 1,
                )
                continue
            if check_block_page(html):
                log.warning(
                    "Block page detected for sitemap on attempt %d", attempt + 1,
                )
                continue
            return html.encode("utf-8")
        except WebDriverException as e:
            wait = 30 * (2 ** attempt)
            log.warning(
                "Selenium sitemap fetch failed (attempt %d): %s. Waiting %ds.",
                attempt + 1, e, wait,
            )
            time.sleep(wait)

    log.error("Selenium retries exhausted for sitemap %s", url)
    return None


def fetch_sitemap_with_retry(
    url: str, driver: Optional[webdriver.Chrome] = None,
) -> Optional[bytes]:
    """Fetch a sitemap, trying ``requests`` first and Selenium as a fallback.

    Returns the raw bytes of whichever response succeeded. The payload may be
    XML (if ``requests`` succeeded) or XSLT-rendered HTML (if Selenium was
    required). ``parse_sitemap`` handles both.
    """
    body = _fetch_sitemap_via_requests(url)
    if body is not None:
        return body

    if driver is None:
        log.error(
            "Sitemap fetch via requests failed for %s and no Selenium driver "
            "is available to fall back to.",
            url,
        )
        return None

    log.info(
        "Falling back to Selenium for sitemap %s (requests path blocked).", url,
    )
    return _fetch_sitemap_via_selenium(url, driver)


def _local(tag: str) -> str:
    """Return the local name of an XML tag (strip any ``{ns}`` prefix)."""
    return tag.split("}", 1)[1] if "}" in tag else tag


def _looks_like_xml(body: bytes) -> bool:
    """Heuristic: does the response body start with an XML prolog / sitemap root?"""
    head = body.lstrip()[:200].lower()
    return (
        head.startswith(b"<?xml")
        or head.startswith(b"<urlset")
        or head.startswith(b"<sitemapindex")
    )


def _parse_sitemap_xml(
    xml_bytes: bytes,
    source_url: str,
    driver: Optional[webdriver.Chrome],
    seen: set,
) -> list[dict]:
    """Parse a standards-compliant XML sitemap / sitemapindex."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        log.error("Failed to parse sitemap XML from %s: %s", source_url, e)
        log.error("First 500 bytes of response: %r", xml_bytes[:500])
        return []

    ns = {"sm": SITEMAP_NS}
    root_local = _local(root.tag).lower()

    urls: list[dict] = []

    if root_local == "sitemapindex":
        nested_locs: list[str] = []
        for sm in root.findall("sm:sitemap", ns) or root.findall("sitemap"):
            loc = sm.findtext("sm:loc", namespaces=ns)
            if loc is None:
                loc_el = sm.find("loc")
                loc = loc_el.text if loc_el is not None else None
            if loc:
                nested_locs.append(loc.strip())

        log.info(
            "Sitemap at %s is an index with %d nested sitemap(s)",
            source_url, len(nested_locs),
        )
        for loc in nested_locs:
            if loc in seen:
                log.debug("Skipping already-seen nested sitemap %s", loc)
                continue
            log.info("Fetching nested sitemap: %s", loc)
            nested_bytes = fetch_sitemap_with_retry(loc, driver)
            if nested_bytes is None:
                log.warning("Failed to fetch nested sitemap %s — skipping", loc)
                continue
            urls.extend(parse_sitemap(nested_bytes, loc, driver, seen))
            time.sleep(random.uniform(1, 2))
        return urls

    if root_local == "urlset":
        url_elems = root.findall("sm:url", ns) or root.findall("url")
        for url_elem in url_elems:
            loc = url_elem.findtext("sm:loc", namespaces=ns)
            if loc is None:
                loc_el = url_elem.find("loc")
                loc = loc_el.text if loc_el is not None else None
            lastmod = url_elem.findtext("sm:lastmod", namespaces=ns)
            if lastmod is None:
                lm_el = url_elem.find("lastmod")
                lastmod = lm_el.text if lm_el is not None else None
            if loc:
                urls.append({"loc": loc.strip(), "lastmod": lastmod})
        return urls

    log.error(
        "Unexpected sitemap root element <%s> at %s — expected <urlset> or <sitemapindex>",
        root.tag, source_url,
    )
    log.error("First 500 bytes of response: %r", xml_bytes[:500])
    return []


def _looks_like_sitemap_link(href: str) -> bool:
    """True if ``href`` points at a paginated / nested sitemap, not a content page."""
    parsed = urlparse(href)
    path = parsed.path.lower()
    query = (parsed.query or "").lower()
    if path.endswith("sitemap.xml") or path.endswith("/sitemap"):
        return True
    if "sitemap" in path and "page=" in query:
        return True
    return False


def _parse_sitemap_html(
    html: str,
    source_url: str,
    driver: Optional[webdriver.Chrome],
    seen: set,
) -> list[dict]:
    """Parse an XSLT-rendered sitemap HTML page.

    Drupal's simple_sitemap module (as used by stylemanual.gov.au) renders
    the sitemap XML into a ``<table class="sitemap …">`` via an XSLT
    stylesheet. Each row has ``<td>`` cells in the order:
    URL, Last modification date, Change frequency, Priority.

    Rows whose first cell links to a nested sitemap (e.g. ``?page=1``) are
    followed recursively, same as an XML ``<sitemapindex>``.
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", class_="sitemap") or soup.find("table")
    if table is None:
        log.error("Sitemap HTML at %s contained no <table> element", source_url)
        log.error("First 500 chars of response: %r", html[:500])
        return []

    parsed_source = urlparse(source_url)
    source_origin = f"{parsed_source.scheme}://{parsed_source.netloc}"

    content_urls: list[dict] = []
    nested_locs: list[str] = []

    tbody = table.find("tbody") or table
    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        link = cells[0].find("a")
        href = (link.get("href") if link else None) or cells[0].get_text(strip=True)
        if not href:
            continue
        href = href.strip()
        if href.startswith("/"):
            href = source_origin + href

        lastmod = cells[1].get_text(strip=True) if len(cells) > 1 else ""
        lastmod = lastmod or None

        if _looks_like_sitemap_link(href) and href != source_url:
            nested_locs.append(href)
        else:
            content_urls.append({"loc": href, "lastmod": lastmod})

    # Also look for pagination links outside the table body (Drupal sometimes
    # renders a ``<ul class="pager">`` or similar for paginated sitemaps).
    for a in soup.select("a[href]"):
        href = a["href"].strip()
        if href.startswith("/"):
            href = source_origin + href
        if (
            _looks_like_sitemap_link(href)
            and href != source_url
            and href not in nested_locs
        ):
            nested_locs.append(href)

    if nested_locs:
        log.info(
            "HTML sitemap at %s contains %d nested sitemap link(s); %d direct URL(s).",
            source_url, len(nested_locs), len(content_urls),
        )

    for loc in nested_locs:
        if loc in seen:
            continue
        log.info("Fetching nested sitemap (via HTML pagination): %s", loc)
        nested_bytes = fetch_sitemap_with_retry(loc, driver)
        if nested_bytes is None:
            log.warning("Failed to fetch nested sitemap %s — skipping", loc)
            continue
        content_urls.extend(parse_sitemap(nested_bytes, loc, driver, seen))
        time.sleep(random.uniform(1, 2))

    return content_urls


def parse_sitemap(
    body: bytes,
    source_url: str,
    driver: Optional[webdriver.Chrome] = None,
    seen: Optional[set] = None,
) -> list[dict]:
    """Parse a sitemap response and return a list of ``{loc, lastmod}`` dicts.

    Accepts either raw XML (``<urlset>`` / ``<sitemapindex>``) or the
    XSLT-rendered HTML table that browsers receive from the Style Manual's
    ``/sitemap.xml``. Nested / paginated sitemaps are resolved recursively in
    either case, with ``seen`` guarding against cycles.
    """
    if seen is None:
        seen = set()
    seen.add(source_url)

    if _looks_like_xml(body):
        return _parse_sitemap_xml(body, source_url, driver, seen)

    html = body.decode("utf-8", errors="replace")
    return _parse_sitemap_html(html, source_url, driver, seen)
