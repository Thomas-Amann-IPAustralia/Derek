# CLAUDE.md — Octavius Rulebook Creation Pipeline

## Project Purpose

Build an automated pipeline that scrapes the Australian Government Style Manual website, extracts discrete style rules via LLM, generates executable detection code for each rule, tests that code, self-corrects failures, and publishes a validated rulebook as Parquet. The pipeline runs as GitHub Actions with Git-committed persistence.

---

## Architecture Overview

Six sequential phases, each a discrete GitHub Actions job:

1. **Markdown Clone** — Scrape site → markdown files + content manifest
2. **Rule Extraction** — Submit LLM batch; poll; collect → JSONL of individual rules
3. **Rules as Code** — Submit LLM batch; poll; collect → executable trigger code per rule
4. **Test** — Run trigger code against test strings
5. **Correct** — Submit LLM batch (gpt-4o); poll; collect; re-test via `run_tests.py --only-corrected`
6. **Publish** — JSONL → Parquet snapshot (manual trigger only)

Phases 2, 3, and 5 use the OpenAI Batch API, which can take up to 24 hours. Each is split into a **submit** job and a **collect** job. The collect job is triggered by a cron schedule (hourly poll) that checks batch status and exits early if not yet complete.

### Manual-only LLM submit

**The three `*_submit.yml` workflows (Phases 2, 3, 5) are `workflow_dispatch`
only** — they are never auto-chained from the previous phase. Only the repo
owner triggers them, which is the only way a token-consuming batch is ever
sent. Cron-driven `*_collect.yml` jobs and the test job (Phase 4) do not
consume tokens, so they continue to run automatically:

| Workflow | Trigger | Costs tokens? |
|---|---|---|
| `phase1_scrape.yml` | manual + monthly cron | no |
| `phase2_submit.yml` | manual only | **yes** |
| `phase2_collect.yml` | manual + hourly cron | no (polls only) |
| `phase3_submit.yml` | manual only | **yes** |
| `phase3_collect.yml` | manual + hourly cron | no (polls only) |
| `phase4_test.yml` | manual + after Phase 3 collect | no |
| `phase5_submit.yml` | manual only | **yes** |
| `phase5_collect.yml` | manual + hourly cron | no (polls + re-test) |
| `phase6_publish.yml` | manual only | no |

Working format throughout: `rules_working_draft.jsonl` (one JSON object per line, Git-committed).

---

## Repo Structure

```
octavius-rulebook/
├── CLAUDE.md                          # This file
├── .github/
│   └── workflows/
│       ├── phase1_scrape.yml
│       ├── phase2_submit.yml
│       ├── phase2_collect.yml
│       ├── phase3_submit.yml
│       ├── phase3_collect.yml
│       ├── phase4_test.yml
│       ├── phase5_submit.yml
│       ├── phase5_collect.yml
│       └── phase6_publish.yml
├── content/                           # Phase 1 output: markdown mirror of Style Manual
├── prompts/                           # One .md prompt per taxonomy (regex.md, spacy.md, etc.)
├── published/                         # Phase 6 output: rulebook.parquet + metadata
├── src/
│   ├── scrape.py                      # Phase 1 logic
│   ├── extract_rules.py               # Phase 2 logic
│   ├── generate_code.py               # Phase 3 logic
│   ├── run_tests.py                   # Phase 4 logic
│   ├── correct_rules.py               # Phase 5 logic
│   └── publish.py                     # Phase 6 logic
├── rules_working_draft.jsonl          # Living JSONL — single source of truth
├── sitemap_state.json                 # Last-seen <lastmod> per URL
├── content_manifest.json              # File list + SHA-256 hashes for Phase 1 output integrity
├── batch_state.json                   # Tracks pending Batch API request IDs per phase
├── amendment_log.json                 # Append-only correction audit trail
└── requirements.txt
```

---

## Taxonomy Registry

This is the canonical list of valid taxonomy values. Phase 2 extraction prompts **must use these exact strings** when assigning `taxonomy`. Phase 3 will fail with a file-not-found error if a value outside this list appears.

| Taxonomy | Prompt file | Generates `trigger_code`? | Notes |
|---|---|---|---|
| `regex` | `prompts/regex.md` | Yes | Python-compatible regex via `re` module |
| `spacy` | `prompts/spacy.md` | Yes | spaCy `Matcher` or `DependencyMatcher` pattern |
| `structural` | `prompts/structural.md` | Yes | AST or document-structure check |
| `lookup` | `prompts/lookup.md` | Yes | Checks against a word/phrase list in `lookup_list` |
| `semantic` | `prompts/semantic.md` | No — LLM sub-call template only | Not executable; documents intent for future implementation |
| `contextual` | `prompts/contextual.md` | No — LLM sub-call template only | Not executable; documents intent for future implementation |
| `discretionary` | *(none)* | No — skipped | Rule is advisory; `trigger_code: null`, `test_result: skip` |
| `multi-modal` | *(none)* | No — skipped | Requires visual/layout analysis; `trigger_code: null`, `test_result: skip` |
| `unassigned` | *(none)* | No — excluded from Phase 3 | Extraction anomaly; triggers loud failure threshold check |

**Phase 3 constraint:** If any `taxonomy` value appears in `rules_working_draft.jsonl` that is not in this table, Phase 3 submit must fail immediately with a clear error message listing the unknown value(s) and the `rule_id`(s) affected.

---

## `batch_state.json` Schema

All phases that use the Batch API read and write this single file. The schema must be followed exactly.

```json
{
  "phase": "3",
  "batch_ids": ["msgbatch_abc123", "msgbatch_def456"],
  "submitted_at": "2025-04-09T10:00:00Z"
}
```

- `phase`: string — which pipeline phase submitted these batches (`"2"`, `"3"`, or `"5"`).
- `batch_ids`: array of strings — one entry per submitted batch. **Collect must not proceed until every ID in this array reports `ended` status.**
- `submitted_at`: ISO 8601 timestamp of submission.

**On clear:** set `batch_state.json` to `{}` and commit. A submit job must verify `batch_state.json` is empty (or `{}`) before submitting new batches — a non-empty file means a previous phase's collect has not completed and the pipeline should not proceed.

---

## Phase-by-Phase Instructions

### Phase 1 — Markdown Clone

**Trigger:** Manual dispatch first run; cron every 30 days thereafter.

**What to build in `src/scrape.py`:**

1. Fetch the Style Manual sitemap. The URL defaults to
   `https://www.stylemanual.gov.au/sitemap.xml`; the `SITEMAP_URL`
   environment variable overrides it for testing against a mirror.
   (`SITEMAP_URL` is a plain repository variable, not a secret — the Style
   Manual is public.) Try `requests` with the descriptive
   `OctaviusRulebookBot/1.0` User-Agent first; if the request is dropped
   by the site's WAF (as `stylemanual.gov.au` does as of 2026), fall back
   to the Selenium driver.
2. Before scraping, check `robots.txt` at the sitemap's root domain. If the relevant paths are disallowed or a `Crawl-delay` directive is present, abort with a clear error message and do not proceed. Log the robots.txt response for inspection. `robots.txt` uses the same `requests`-then-Selenium fallback as the sitemap fetch.
3. Parse the response as either raw XML (`<urlset>` / `<sitemapindex>`) or the XSLT-rendered HTML table the Style Manual's sitemap serves to browsers (a `<table class="sitemap">` with one row per URL: URL / Last modification date / Change frequency / Priority). Extract `loc` and `lastmod` from each entry. Nested and paginated sitemaps are followed recursively in either shape.
4. Load `sitemap_state.json` from repo root. On first run, treat all pages as new.
5. For each new/changed URL: fetch rendered HTML via **Selenium headless Chrome** (see driver initialisation below), strip noise via **BeautifulSoup**, then pass the cleaned HTML through **trafilatura** to convert to clean markdown.
   - **Politeness delay:** Use `time.sleep(random.uniform(2, 4))` between page fetches — randomised to appear more human. Never request two pages back-to-back with no delay.
   - **Scroll simulation:** After the page body is detected, simulate human scrolling before extracting HTML:
     ```python
     driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 4);")
     time.sleep(random.uniform(2, 4))
     driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
     time.sleep(random.uniform(1, 3))
     ```
   - **Block detection:** After fetching `driver.page_source`, check the raw HTML (case-insensitive) against this list of failure signatures before processing. If any match, treat the page as failed — do not pass to trafilatura:
     ```python
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
     ```
   - **BeautifulSoup noise removal:** Before passing HTML to trafilatura, parse with BeautifulSoup and strip the following tags/selectors from the `<body>`: `nav`, `footer`, `header`, `script`, `style`, `aside`, `.noprint`, `#sidebar`. Pass the cleaned HTML string (not text) to trafilatura.
   - **Rate-limit back-off:** If a request returns HTTP 429 or 503, back off exponentially: wait 30s, then 60s, then 120s before retrying. After 3 failed retries on a single URL, log the failure, skip the URL, and continue — do not abort the entire run.
6. Write markdown to `content/` using URL path segments as directory structure.
   - Example: `https://www.stylemanual.gov.au/grammar-punctuation/punctuation/apostrophes` → `content/grammar-punctuation/punctuation/apostrophes.md`
7. Update `sitemap_state.json` with current `<lastmod>` values.
8. Write `content_manifest.json`: a JSON object mapping each relative file path in `content/` to its SHA-256 hash.
   ```json
   {
     "generated_at": "2025-04-09T10:00:00Z",
     "files": {
       "content/grammar-punctuation/punctuation/apostrophes.md": "a3f1c2...",
       "content/grammar-punctuation/punctuation/hyphens.md": "b7d4e9..."
     }
   }
   ```
9. Git-commit `content/` changes, `sitemap_state.json`, and `content_manifest.json` together in a single commit.

#### WebDriver Initialisation

Use the following `initialize_driver()` pattern. This configures headless Chrome with anti-detection flags and applies `selenium-stealth` patches. Use `ChromeDriverManager` for automatic driver version management.

```python
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth

def initialize_driver(with_proxy: bool = False) -> Optional[webdriver.Chrome]:
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--lang=en-US,en;q=0.9')
    # NOTE: Keep this generic User-Agent for stealth; the descriptive bot UA is sent
    # via a separate HTTP header in the sitemap/robots.txt fetch only (use requests lib).
    chrome_options.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    )
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    if with_proxy:
        proxy_host, proxy_port, proxy_user, proxy_pass = (
            os.environ.get(k) for k in ["PROXY_HOST", "PROXY_PORT", "PROXY_USER", "PROXY_PASS"]
        )
        if all([proxy_host, proxy_port, proxy_user, proxy_pass]):
            chrome_options.add_argument(
                f'--proxy-server=http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}'
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
```

**Proxy support:** The driver optionally routes through a proxy, configured via environment variables `PROXY_HOST`, `PROXY_PORT`, `PROXY_USER`, `PROXY_PASS`. In `fetch_with_retry`, attempt a direct connection first; if that returns a block-page signature or raises a `WebDriverException`, retry with `initialize_driver(with_proxy=True)` if proxy credentials are present.

**Explicit waits:** Use `WebDriverWait` to wait for page body presence before extracting HTML — do not rely solely on fixed sleeps for page-ready detection:
```python
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
    EC.presence_of_element_located((By.TAG_NAME, 'body'))
)
```
Use `PAGE_LOAD_TIMEOUT = 25` (seconds). After the wait, perform scroll simulation before extracting `driver.page_source`.

**Descriptive User-Agent for robots.txt / sitemap fetch:** When fetching `robots.txt` and the sitemap via `requests`, set a descriptive `User-Agent` that identifies the bot:
```
OctaviusRulebookBot/1.0 (+https://github.com/<your-org>/octavius-rulebook)
```
This is separate from the stealth User-Agent used in the Chrome driver. If the descriptive UA is blocked (as happens on `stylemanual.gov.au`), `scrape.py` falls back to Selenium using the stealth UA so the pipeline still completes.

**Dependencies:** `selenium`, `selenium-stealth`, `webdriver-manager`, `beautifulsoup4`, `lxml`, `trafilatura`, `requests`, `hashlib` (standard library).

**Constraints:**
- Selenium + stealth handles page fetch (supports JS-rendered content and anti-bot evasion).
- BeautifulSoup strips navigation noise *before* trafilatura receives the HTML.
- Trafilatura handles HTML→markdown conversion only — do not use it as a scraper.
- Use trafilatura consistently for conversion (same normalisation as Tripwire).
- `sitemap_state.json` and `content_manifest.json` must both be committed every run for persistence across ephemeral GitHub Actions runners.
- The robots.txt check (step 2) is mandatory on every run, not just the first.
- Block-page signature detection is mandatory — never commit a block page as a content file.

---

### Phase 2 — Rule Extraction

**Trigger:** `phase2_submit.yml` is `workflow_dispatch` only — it never auto-chains from Phase 1 because batch submission consumes LLM tokens. `phase2_collect.yml` runs on hourly cron (plus manual dispatch), checks batch status, and exits early if not complete.

**What to build in `src/extract_rules.py`:**

**Submit mode** (`extract_rules.py submit`):
1. Verify `content_manifest.json` exists. If it is absent, abort with: `"Phase 2 cannot proceed: content_manifest.json not found. Phase 1 may not have completed successfully."` This guards against reading a partial or uncommitted content state.
2. Read all `.md` files from `content/`. **Skip any file that already has rules in `rules_working_draft.jsonl`** (matched by the `source_file` field — this is the persistent dedup source across pipeline cycles) and any file currently in flight (`batch_state.json` → `processed_files`, which guards against a retried submit before its own collect completes). This prevents re-extraction — and so prevents wasted tokens — on re-runs.
3. For each unprocessed file, construct a prompt that instructs the LLM to identify every discrete style rule and return each as a separate JSONL object. The `taxonomy` field must be drawn from the **Taxonomy Registry** above — include the registry table in the prompt verbatim.
4. Submit via **OpenAI Batch API**, grouping by sitemap section.
5. Write to `batch_state.json`:
   ```json
   {
     "phase": "2",
     "batch_ids": ["msgbatch_abc123"],
     "submitted_at": "2025-04-09T10:00:00Z",
     "processed_files": [
       "content/grammar-punctuation/punctuation/apostrophes.md"
     ]
   }
   ```
   `processed_files` lists every source file included in the current in-flight submission. Cross-cycle persistence of "already extracted" is provided by `rules_working_draft.jsonl` — on a fresh cycle `batch_state.json` is `{}`, but files are still skipped if they already have rules in the draft.
6. Git-commit `batch_state.json`.

**Collect mode** (`extract_rules.py collect`):
1. Read `batch_state.json`. Check that `phase` is `"2"`. Poll status for **every ID in `batch_ids`**. If any ID is not yet complete, exit 0 (cron will retry next hour).
2. On all batches complete, retrieve results. Each returned object must include these fields:

| Field | Type | Content |
|---|---|---|
| `rule_id` | string | Slugified from page path + sequential index, e.g. `grammar-punctuation--apostrophes-001`. Use `-` as separator throughout — no `/` characters. |
| `source_url` | string | Originating page URL |
| `source_file` | string | Relative path to markdown source |
| `rule_summary` | string | One-sentence plain-English statement |
| `rule_detail` | string | Full extracted rule text |
| `taxonomy` | string | Must be a value from the Taxonomy Registry. Defaults to `unassigned` only if the LLM genuinely cannot determine a valid taxonomy. |
| `discretionary_flag` | boolean | `true` if source text frames the rule as discretionary |
| `extracted_at` | string | ISO 8601 timestamp |

3. Append all objects to `rules_working_draft.jsonl`.
4. Clear `batch_state.json` to `{}`. Git-commit both files.

**Critical prompt instruction:** The LLM must NOT merge related rules. One rule = one line. Compound rules (e.g. "use apostrophe for possession but not for plurals") must be split into separate entries.

---

### Phase 3 — Generate Rules as Code

**Trigger:** `phase3_submit.yml` is `workflow_dispatch` only — batch submission consumes LLM tokens, so it never auto-chains from Phase 2 collect. `phase3_collect.yml` runs on hourly cron (plus manual dispatch).

**What to build in `src/generate_code.py`:**

**Submit mode** (`generate_code.py submit`):
1. Read `rules_working_draft.jsonl`. Count `unassigned` rows.
2. **Unassigned threshold check:** Calculate `unassigned_ratio = unassigned_count / total_rows`. If this exceeds the threshold set by environment variable `MAX_UNASSIGNED_RATIO` (default: `0.05`), **abort immediately** with a loud failure:
   - Exit with a non-zero code.
   - Print a clear error message: `"PIPELINE ABORTED: {unassigned_count} of {total_rows} rules ({ratio:.1%}) have taxonomy 'unassigned', exceeding the MAX_UNASSIGNED_RATIO threshold of {threshold:.1%}. This indicates an extraction anomaly in Phase 2. Manual review required before proceeding."`
   - Publish this message as a GitHub Actions Job Summary.
   - Do not submit any batches.
3. If below threshold, **exclude `unassigned` rows from LLM submission** and continue. Log a warning (not a failure) listing the excluded `rule_id`s.
4. Verify all remaining rows have a `taxonomy` value present in the Taxonomy Registry. If any unknown value is found, abort with a clear error listing the unknown taxonomy values and affected `rule_id`s.
5. Group rows by `taxonomy`. For each group, load the matching prompt from `prompts/<taxonomy>.md`.
6. Send batches of **5 rows** to the LLM with the taxonomy-specific prompt. **Each row sent to the LLM must include its `rule_id` field. The prompt must instruct the LLM to echo back `rule_id` unchanged in every response object.**
7. Write to `batch_state.json`:
   ```json
   {
     "phase": "3",
     "batch_ids": ["msgbatch_abc123", "msgbatch_def456"],
     "submitted_at": "2025-04-09T10:00:00Z"
   }
   ```
8. Git-commit `batch_state.json`.

**Collect mode** (`generate_code.py collect`):
1. Read `batch_state.json`. Check `phase` is `"3"`. Poll **every ID in `batch_ids`**. Exit 0 if any is not yet complete.
2. On all batches complete, retrieve results.
3. **Match by `rule_id`, not positional index.** For each returned object, look up the matching row in `rules_working_draft.jsonl` by `rule_id`. If a returned object has no matching `rule_id` in the draft, log it as an error and skip it — do not append it to any row. If a draft row has no matching returned object (the LLM omitted it), log a warning and leave that row unchanged for manual review.
4. On a successful match, append these fields to the existing JSONL object:

| Field | Type | Content |
|---|---|---|
| `method` | string | Primary implementation method from taxonomy list |
| `requires` | array | Dependency methods if any |
| `method_notes` | string | Edge cases or interaction notes |
| `trigger_code` | string\|null | Implementation code (regex, spaCy rule, structural check, etc.) |
| `ui_flag` | string | User-facing message in Octavius UI |
| `test_fire` | array | Strings that SHOULD trigger the rule |
| `test_no_fire` | array | Strings that SHOULD NOT trigger the rule |
| `lookup_list` | string\|array\|null | Word/reference list for lookup/external rules |
| `code_token_count` | integer | Token count of `trigger_code` as measured by the project's tokeniser (use `tiktoken` with `cl100k_base` encoding for consistency) |
| `ui_flag_token_count` | integer | Token count of `ui_flag` (same tokeniser) |
| `test_token_count` | integer | Combined token count of all `test_fire` and `test_no_fire` strings (same tokeniser) |
| `code_generated_at` | string | ISO 8601 timestamp |

5. For `unassigned` rows (excluded from submission): set `trigger_code: null`, `test_result: skip`, `method_notes: "Taxonomy unassigned — requires manual review"`.
6. For `semantic`, `contextual`, `discretionary`, and `multi-modal` rows: set `trigger_code: null`. These travel through the pipeline as documentation of what Octavius explicitly does not automate.
7. Clear `batch_state.json` to `{}`. Write updated JSONL. Git-commit.

**Taxonomy-specific prompt constraints:**
- `regex` prompt → Python-compatible regex; avoid over-matching.
- `spacy` prompt → spaCy `Matcher` or `DependencyMatcher` pattern.
- `lookup` prompt → logic that checks against `lookup_list`; list must be returned as an array.
- `semantic` / `contextual` prompts → LLM sub-call template, not executable code.
- `discretionary` / `multi-modal` rules → set `trigger_code: null`, add explanatory note. **Skip these.**

**Prompt files required:** Create one `.md` per taxonomy in `prompts/`. Each must contain: the JSONL output schema (including the `rule_id` echo requirement), method-specific constraints, one worked example, and fallback instructions when the rule can't be cleanly implemented.

---

### Phase 4 — Run Tests

**Trigger:** Completes after Phase 3 collect; also called by Phase 5 with `--only-corrected` flag.

**What to build in `src/run_tests.py`:**

Supports two modes:
- Default: tests all rows.
- `--only-corrected`: tests only rows where `correction_model` is set and `test_result` is not yet `pass`.

1. Read `rules_working_draft.jsonl`.
2. For each row where `trigger_code` is not null, execute against `test_fire` and `test_no_fire` using the appropriate engine:
   - `regex` → Python `re` module
   - `spacy` → spaCy pipeline
   - `structural` → AST parser
   - `lookup` → list membership check against `lookup_list`
   - Others as appropriate per taxonomy
3. **Pass** = every `test_fire` triggers AND every `test_no_fire` does not.
4. Append to each row:

| Field | Type | Content |
|---|---|---|
| `test_result` | string | `pass`, `fail`, `skip` (null trigger code), or `frozen` (see Phase 5) |
| `test_run_at` | string | ISO 8601 timestamp |
| `error_log` | string\|null | Mismatch detail if fail; null otherwise |

5. Generate `test_report.md` from template: total tested, pass/fail/skip/frozen counts, table of failures with `rule_id`, `taxonomy`, truncated `error_log`. **Flag any `unassigned` taxonomy rows with a distinct warning section.**
6. **Publish `test_report.md` as a GitHub Actions Job Summary.**
7. Git-commit updated JSONL.

---

### Phase 5 — Correct Erroneous Rules

**Trigger:** `phase5_submit.yml` is `workflow_dispatch` only — batch submission consumes LLM tokens, so it never auto-chains from Phase 4. The script exits gracefully if there are no `test_result: fail` rows to correct. `phase5_collect.yml` runs on hourly cron (plus manual dispatch).

**What to build in `src/correct_rules.py`:**

**Submit mode** (`correct_rules.py submit`):
1. Filter `test_result: fail` rows (excluding `frozen` rows — see below). Group by `taxonomy`.
2. Send bundles of **3 failed rules** to a more capable model (Opus) via **Batch API**, including: `rule_id`, `rule_summary`, `rule_detail`, `trigger_code`, `test_fire`, `test_no_fire`, `error_log`.
3. Write to `batch_state.json`:
   ```json
   {
     "phase": "5",
     "batch_ids": ["msgbatch_xyz789"],
     "submitted_at": "2025-04-09T12:00:00Z"
   }
   ```
4. Git-commit `batch_state.json`.

**Collect mode** (`correct_rules.py collect`):
1. Read `batch_state.json`. Check `phase` is `"5"`. Poll **every ID in `batch_ids`**. Exit 0 if any is not yet complete.
2. On all batches complete, retrieve results. The LLM must return a JSON array — one object per corrected rule. Each object in the array must follow this schema:

```json
[
  {
    "rule_id": "grammar-punctuation--apostrophes-001",
    "trigger_code": "<corrected code string>",
    "issue_summary": "Plain-English description of what was wrong.",
    "correction_summary": "Plain-English description of what was changed.",
    "correction_model": "gpt-4o"
  }
]
```

   - `rule_id` must be echoed from the input. The prompt must require this explicitly.
   - If the LLM cannot correct a rule, it must still return an object for that `rule_id` with `trigger_code: null` and an `issue_summary` explaining why.
   - **Match returned objects to JSONL rows by `rule_id`, not positional index.**

3. For each matched row, update the JSONL:
   - Set `trigger_code` to the returned value (may be null if uncorrectable).
   - Update `code_generated_at` to current timestamp.
   - Add field `correction_model` with the model name.

4. Append amendment objects to `amendment_log.json`:
   ```json
   {
     "rule_id": "grammar-punctuation--apostrophes-001",
     "amended_at": "2025-04-09T10:30:00Z",
     "issue_summary": "Regex over-matched possessive 'its' due to missing word boundary assertion.",
     "correction_summary": "Added \\b boundary anchors around the pattern.",
     "correction_model": "gpt-4o"
   }
   ```

5. Re-test corrected rows by calling `run_tests.py --only-corrected`:
   - Now pass → `test_result: pass`
   - Still fail → `test_result: frozen` — **frozen until manual intervention.** These rows will not re-enter Phase 5 on subsequent pipeline runs.

6. Clear `batch_state.json` to `{}`. Git-commit updated JSONL + `amendment_log.json`.

**Why bundles of 3 (not 5)?** Correction is harder than generation — smaller bundles give the model more context per rule and reduce cross-contamination.

---

### Phase 6 — Publish Rulebook

**Trigger:** Manual dispatch only (requires your explicit approval).

**What to build in `src/publish.py`:**

1. Read `rules_working_draft.jsonl`.
2. **Validate:** No rows may have `test_result: fail`. Rows with `frozen` are permitted but surfaced as a warning.
3. Convert to `published/rulebook.parquet` using **pandas + pyarrow** with correct column types (strings, arrays, booleans, timestamps).
4. Write `published/rulebook_metadata.json`:
   ```json
   {
     "published_at": "<ISO 8601>",
     "total_rules": 0,
     "by_taxonomy": {},
     "skip_count": 0,
     "frozen_count": 0,
     "unassigned_count": 0,
     "sha256": "<SHA-256 hash of parquet file>"
   }
   ```
5. Commit both to `published/`. Optionally tag commit as `rulebook-v<N>`.

**Key principle:** JSONL is the editable source of truth. Parquet is a read-optimised snapshot. Publishing never writes back to the JSONL.

---

## Persistent Files (Git-Committed)

| File | Role | Mutated by |
|---|---|---|
| `sitemap_state.json` | Last-seen `<lastmod>` per URL | Phase 1 |
| `content_manifest.json` | SHA-256 hashes of all files in `content/` | Phase 1 |
| `batch_state.json` | Pending Batch API request IDs + processed file list | Phases 2, 3, 5 (submit/collect) |
| `rules_working_draft.jsonl` | Living rule database | Phases 2–5 |
| `amendment_log.json` | Append-only correction audit trail | Phase 5 |
| `content/**/*.md` | Markdown mirror of Style Manual | Phase 1 |
| `published/rulebook.parquet` | Snapshot for Octavius engine | Phase 6 |
| `published/rulebook_metadata.json` | Publication metadata + integrity hash | Phase 6 |

## Ephemeral Artefacts

| File | Role | Visibility |
|---|---|---|
| `test_report.md` | Test run summary | GitHub Actions Job Summary; optionally retained as workflow artefact for 30 days |

---

## Design Principles

1. **One rule, one JSONL line.** Never merge rules. Split compound rules.
2. **Git-committed persistence.** All state files are committed so ephemeral GitHub Actions runners can pick up where the last run left off.
3. **Selenium + stealth scrapes, BeautifulSoup cleans, trafilatura converts.** Selenium headless Chrome (with `selenium-stealth` anti-detection patches) fetches rendered HTML. BeautifulSoup strips navigation noise (`nav`, `footer`, `header`, `script`, `style`, `aside`, `.noprint`, `#sidebar`) from the DOM before trafilatura receives it. Trafilatura handles HTML→markdown conversion only. Consistent normalisation across Octavius and Tripwire.
4. **Submit/collect for Batch API.** Phases 2, 3, and 5 each split into a submit job and an hourly-cron collect job. Collect exits cleanly if any batch is not yet complete. Collect does not proceed until **all** batch IDs in `batch_state.json` report complete.
5. **Job Summaries for visibility.** Test reports published as GitHub Actions Job Summaries — no need to open the repo to see results.
6. **JSONL is source of truth.** Parquet is a downstream snapshot. Never edit via Parquet.
7. **Discretionary/multi-modal rules travel through the pipeline** with `trigger_code: null` and `test_result: skip`. They document what Octavius explicitly does not automate.
8. **`unassigned` taxonomy is an anomaly signal.** Rules tagged `unassigned` are excluded from LLM code generation and flagged prominently in test reports. If the unassigned rate exceeds `MAX_UNASSIGNED_RATIO` (default 5%), Phase 3 aborts loudly.
9. **Frozen after one correction attempt.** If a rule still fails after Phase 5 correction, it is set to `test_result: frozen` and will not re-enter the correction loop. Manual intervention required.
10. **Smaller correction bundles.** Phase 5 uses bundles of 3 (vs 5 in Phase 3) because debugging is harder than generation.
11. **Match by `rule_id`, never by position.** All LLM response parsing in Phases 3 and 5 matches returned objects to JSONL rows by `rule_id`. Positional matching is forbidden.
12. **Be a polite and stealthy scraper.** Phase 1 uses randomised delays (`random.uniform(2, 4)` seconds) between every request, simulates human scroll behaviour, applies `selenium-stealth` anti-detection patches, respects `robots.txt` on every run, and identifies itself via a descriptive `User-Agent` on non-browser requests (robots.txt and sitemap fetches). It backs off exponentially on rate-limit responses. Block-page signature detection prevents committing Cloudflare challenge pages or error screens as content.
13. **Taxonomy registry is the contract.** The canonical list of valid taxonomy values is defined once in this document. Phase 2 prompts and Phase 3 logic both derive from it. Unknown values cause immediate pipeline failure.
14. **Token counts use `tiktoken`.** All `*_token_count` fields are measured using `tiktoken` with `cl100k_base` encoding for consistency across runs.

---

## Session Protocol for Claude Code

Work in **one phase per session**. At the start of each session:

1. Re-read this `CLAUDE.md` for orientation.
2. Confirm which phase you are building.
3. Build, test locally where possible, and commit.
4. Do not proceed to the next phase without explicit instruction.

If you encounter an ambiguity, flag it and stop rather than making an assumption that could propagate through later phases.
