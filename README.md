# Finance Agent

A CLI tool that fetches SEC filings and market data for a given stock ticker, extracts structured financial metrics, applies a probabilistic scoring model (0–100), and runs four LLM analyses to predict whether a stock price is likely to rise or fall in the next quarter.

**Scope**: SEC EDGAR only covers companies that file Form 10-K/10-Q — in practice, US-domiciled/US-listed companies. Foreign private issuers filing 20-F/40-F instead are not supported.

---

## Project Structure

```
finance_agent/
├── main.py          # Entry point + pipeline orchestration
├── extractor.py     # extract_10k(), extract_10q(), extract_vantage()
├── xbrl_helpers.py  # XBRL label constants + numeric fact pickers
├── filing_text.py   # Free-text (Risk Factors/MD&A/Legal) + segment data from HTML/R-files
├── scorer.py        # Scoring model (knockout filters + 5 blocks)
├── agent.py         # LLM agent (4 analysis functions, multi-provider)
├── get_data.py      # SEC/Alpha Vantage API calls, file I/O
├── .env             # API keys (not committed)
├── .env.example     # Key name reference
├── output/          # JSON files saved per ticker (numeric + *_text.json)
└── system_instruction.json
```

### Import chain

```
main.py
  ├── extractor.py  →  xbrl_helpers.py
  ├── scorer.py
  ├── agent.py
  └── get_data.py  →  filing_text.py
```

---

## Data Sources

| Source | Data | API |
|---|---|---|
| SEC EDGAR (direct, free) | Ticker → CIK mapping | `sec.gov/files/company_tickers.json` |
| SEC EDGAR (direct, free) | Company submission metadata, filing index | `data.sec.gov/submissions/` |
| SEC EDGAR (direct, free) | Structured XBRL financial facts (10-K/10-Q/8-K) | `data.sec.gov/api/xbrl/companyfacts/` |
| SEC EDGAR (direct, free) | Free text (Risk Factors, MD&A, Legal Proceedings), 8-K items | Primary filing HTML at `sec.gov/Archives/edgar/data/{cik}/{accession}/{primaryDocument}` |
| SEC EDGAR (direct, free) | Segment revenue/margin | Pre-rendered R-files, located via `FilingSummary.xml` in the same accession folder |
| Alpha Vantage | Market data, valuation multiples, analyst ratings | `OVERVIEW` endpoint |

All SEC endpoints are free and require no API key — only a descriptive `User-Agent` header, read from `.env` (see Setup below).

### `filing_text.py` — HTML scraping layer

`get_data.fetch_and_save_filing_text()` additionally downloads the primary filing document (HTML) and saves the extracted sections as `{TICKER}_{suffix}_text.json` next to the numeric file. `extractor.py` reads this companion file automatically — if it's missing, the affected fields stay empty (no crash).

- **10-K/10-Q free text** (`get_10k_sections()`/`get_10q_sections()`): section headings ("Item 1A. Risk Factors") are detected structurally rather than by text convention, since filers vary between ALL CAPS and mixed case — a heading is a tag whose own text is short and starts exactly with "Item N.". With multiple matches (table of contents vs. real heading), the longer tag wins, or the later one on a tie. Body text is then collected by walking forward in the DOM until the next heading.
- **8-K items** (`get_8k_items()`): 8-Ks are structurally simpler (heading and text often share one tag), so this scans the flattened text linearly for the SEC-wide `Item X.XX.` decimal format instead.
- **Segments** (`get_segment_data()`): SEC pre-renders a report (R1.htm, R2.htm, ...) for every XBRL disclosure, indexed in `FilingSummary.xml`. The matching R-file (ShortName containing "segment" + "revenue"/"sales") gets parsed; scale annotations ("$ in Millions" etc.) are normalized to raw USD to stay comparable with companyfacts. Revenue row labels vary by filer ("Revenue", "Sales to customers", "Net sales", ...) — an alias list covers the common ones. Repeating boilerplate sub-header rows are detected by frequency, not fixed text. Filers with very granular breakdowns (geography × product line) are capped to the 10 largest segments by revenue.

### Environment variables (`.env` format: `Key: "value"`)

```
SEC_USER_AGENT          # e.g. "YourAppName you@example.com" — required by SEC, no key needed
Alpha_Vantage_API_KEY
LLM_API_KEY
LLM_PROVIDER            # deepseek | openai | gemini | groq
```

---

## Pipeline (end-to-end flow)

```
User enters ticker symbol
        │
        ├─ Cached output files exist? → ask to reuse or re-fetch
        │
        ▼ (if fetching)
get_data.getCik()            → resolve ticker → CIK
get_data.getSubmissionData() → fetch filing index from SEC
get_data.fetch_and_save_filing() × 3  → XBRL JSON per filing type
get_data.fetch_and_save_overview()    → Alpha Vantage data
        │
        ▼ (saves to output/)
extract_10k()    → annual metrics + multi-year trends
extract_10q()    → quarterly metrics + balance sheet comparisons + segments
extract_vantage()→ valuation, profitability, analyst consensus, market data
        │
        ▼
scorer.score()  → knockout filters → 5 scoring blocks → probability_up
        │
        ▼
agent.analyze()           → overall assessment + direction
agent.analyze_mda()       → MD&A synthesis from scraped text + numbers
agent.extract_guidance()  → implicit forward-looking signals
agent.explain_anomalies() → weak block identification + discrepancies
```

---

## `main.py` — Entry Point

Handles user interaction and orchestrates the full pipeline. Contains no extraction or scoring logic.

### Cache check

On startup, `_cache_exists(ticker)` checks whether all four output files (`_10k.json`, `_10q.json`, `_8k.json`, `_vantage.json`) already exist. If yes, the user is asked whether to reuse them — skipping all API calls.

### Resilient file loading

Each output file is checked for existence before extraction. Missing files (e.g. if a filing was not found or the API call failed) are skipped with a message instead of crashing.

---

## `get_data.py` — Data Fetching

Handles all external API calls and file I/O. No scoring or extraction logic.

| Function | Purpose |
|---|---|
| `load_api_key(key_name)` | Reads a key from `.env` (format: `Key: "value"`) |
| `getCik(ticker)` | Resolves ticker to SEC CIK via SEC's free `company_tickers.json` |
| `getSubmissionData(cik)` | Fetches filing index from `data.sec.gov` |
| `get_latest_filing_by_form(data, form)` | Returns most recent filing of given type (10-K, 10-Q, 8-K) |
| `fetch_company_facts(cik)` | Fetches **all** structured XBRL facts for the company from `data.sec.gov/api/xbrl/companyfacts/` (one call per ticker, covers every filing) |
| `fetch_and_save_filing(filing, cik, ticker, suffix, company_facts)` | Filters `company_facts` down to the facts reported under one filing's accession number, saves to `output/` |
| `fetch_and_save_overview(ticker)` | Fetches Alpha Vantage OVERVIEW, saves to `output/` |

> **Note on format compatibility**: `_to_period_item()` converts each raw SEC fact (`{"val", "start", "end", "accn", ...}`) into the `{"value", "period": {"startDate"/"endDate" or "instant"}}` shape that `xbrl_helpers.py` expects, so the extraction layer below needed no changes.

---

## `xbrl_helpers.py` — XBRL Parsing Layer

Contains all label constants and every low-level helper. Nothing in this file makes network calls or reads files.

### Label Constants

Each filing type has a mapping dict with fallback chains of XBRL concept names per metric.

**`LABELS_10k`** — annual concepts:
`revenue`, `gross_profit`, `cost_of_revenue`, `operating_income`, `net_income`, `diluted_eps`, `rd_expense`, `sga_expense`, `cash`, `total_assets`, `total_liabilities`, `operating_cash_flow`, `capex`

**`LABELS_10Q` — `core_metrics`** — quarterly concepts (additional vs 10-K):
`gross_profit`, `cost_of_revenue`, `inventory`, `accounts_receivable`, `debt_current`, `debt_noncurrent`, `current_assets`, `current_liabilities`, `retained_earnings`, `stockholders_equity`

**`LABELS_8K`** — event flags and metadata fields.

### Key Helper Functions

| Function | Purpose |
|---|---|
| `_walk(obj, path)` | Recursive JSON walker yielding `(path, key, value)` tuples |
| `_find_key(obj, key)` | Exact recursive key lookup |
| `_get_by_path(obj, path)` | Dot-path accessor (e.g. `"CoverPage.DocumentFiscalPeriodFocus"`) |
| `_pick(data, names)` | Most recent unsegmented numeric fact from a fallback name list; on a tied end date, prefers the shortest duration (avoids picking a 9-month YTD figure over the actual 3-month quarter) |
| `_pick_all_periods(data, names)` | `{end_date: value}` for all periods — used for multi-year trends |
| `_pick_prior_instant(data, names)` | Second most recent instant value (prior fiscal year balance sheet) |
| `_pick_for_period(data, names, start, end)` | Fact for a specific date range — used for YoY/QoQ derivation |
| `_latest_duration_fact(data, names)` | Most recent duration fact with both start and end date |
| `_safe_change(current, previous)` | `(current - previous) / previous`, returns `None` on division by zero |
| `_derive_yoy_change(data)` | Revenue YoY from prior-year quarter in same filing |
| `_derive_qoq_change(data)` | Revenue QoQ if prior quarter is present in same filing |

Free-text and segment extraction (formerly here) now live in [filing_text.py](filing_text.py) — see above.

---

## `extractor.py` — Extraction Layer

Reads the saved JSON output files and returns structured Python dicts. Imports all helpers from `xbrl_helpers.py`.

### `extract_10k(path)` → dict

Returns from the most recent annual filing:

```python
{
  "metrics": {
    "revenue", "gross_profit", "operating_income", "net_income",
    "diluted_eps", "rd_expense", "sga_expense", "cash",
    "total_assets", "total_liabilities", "operating_cash_flow",
    "capex", "free_cash_flow",
    "gross_margin_pct", "operating_margin_pct", "net_margin_pct"
  },
  "trends": {
    "revenue", "gross_profit", "operating_income", "net_income",
    "total_assets", "operating_cash_flow", "shares_diluted",
    "asset_turnover",
    "gross_margin_pct", "operating_margin_pct", "net_margin_pct"
    # All as {end_date: value} dicts across all available years
  },
  "risk_factors": ["sentence 1", ...],   # first sentences of the scraped Item 1A section
  "mda_highlights": ["sentence 1", ...]  # first sentences of the scraped Item 7 (MD&A) section
}
```

**`gross_profit` fallback**: If the company does not report `GrossProfit` as an XBRL concept (e.g. Alphabet), it is derived as `Revenue − CostOfRevenue`. The same fallback applies to multi-year trend data.

**`risk_factors`/`mda_highlights` source**: read from the `{TICKER}_10k_text.json` companion file produced by `filing_text.get_10k_sections()` (see above) — empty if that file is missing.

### `extract_10q(path)` → dict

Returns from the most recent quarterly filing:

```python
{
  "core_metrics": {
    # Raw XBRL values (current quarter)
    "revenue", "gross_profit", "operating_income", "net_income",
    "eps_diluted", "cash", "total_assets", "total_liabilities",
    "stockholders_equity", "operating_cash_flow", "capex",
    "shares_outstanding", "inventory", "accounts_receivable",
    "debt_current", "debt_noncurrent", "current_assets",
    "current_liabilities", "retained_earnings",
    # Derived
    "free_cash_flow",           # OCF - |CapEx|
    "total_debt",               # debt_current + debt_noncurrent
    "gross_margin_pct",         # gross_profit / revenue (with CostOfRevenue fallback)
    "operating_margin_pct",
    "net_margin_pct",
    "current_ratio",            # current_assets / current_liabilities
    "current_ratio_prior",      # prior fiscal year end
    "leverage_ratio",           # total_debt / total_assets
    "leverage_ratio_prior",
    "total_debt_prior",
    "total_assets_prior"
  },
  "comparisons": {
    "yoy_change", "qoq_change",
    "current_quarter", "current_fiscal_year", "document_period_end"
  },
  "segments": {
    "period": {"start": ..., "end": ...},
    "segments": {
      "SegmentName": {
        "revenue", "gross_profit", "gross_margin_pct",
        "revenue_yoy_change", "gross_margin_pct_prior_year"
      }
    }
  },
  "mda_updates": {"liquidity_capital_resources", "results_of_operations", "highlights"},
  "risk_factor_changes": {"risk_factor_change_summary", "risk_factor_changes_flag"},
  "legal_proceedings": {"legal_proceedings_summary", "legal_proceedings_update_flag"}
}
```

### `extract_vantage(path)` → dict

```python
{
  "valuation":   {"market_cap", "pe_ratio", "forward_pe", "peg_ratio",
                  "price_to_book", "price_to_sales_ttm", "ev_to_revenue", "ev_to_ebitda"},
  "profitability": {"profit_margin", "operating_margin_ttm", "roa", "roe",
                    "ebitda", "eps_ttm", "gross_profit_ttm", "revenue_ttm"},
  "growth":      {"earnings_growth_yoy", "revenue_growth_yoy"},
  "analyst_consensus": {"target_price", "strong_buy", "buy", "hold", "sell",
                        "strong_sell", "total_analysts", "bullish_pct", "bearish_pct"},
  "metadata":    {"sector", "industry", "asset_type", "latest_quarter"},
  "market_data": {"beta", "week_52_high", "week_52_low", "ma_50_day", "ma_200_day",
                  "book_value_per_share", "shares_outstanding", "current_price_derived"}
}
```

---

## `scorer.py` — Scoring Model

### Architecture

```
Input: data_10k, data_10q, data_vantage
        │
        ▼
knockout_filters()        → pass/fail + flags dict
        │
  fail ─┤─ pass
        │
        ▼
score_quality()           → 0–30 pts
score_valuation()         → 0–25 pts
score_financial_strength()→ 0–20 pts
score_growth()            → 0–15 pts
score_momentum()          → 0–10 pts
        │
        ▼
total score (0–100)
probability_up = 0.25 + (score / 100) * 0.50   → range: 25%–75%
```

### Knockout Filters

Hard stops that prevent scoring. Returns `(passed: bool, reasons: list, flags: dict)`.

| Filter | Condition | Type |
|---|---|---|
| Negative equity | `stockholders_equity < 0` (non-financial only) | Knockout |
| OCF 2 years negative | Last 2 years of OCF both < 0 | Knockout |
| Altman Z-Score | Z < 1.1 (non-financial only) | Knockout |
| OCF/NI 2 years < 0.5 | Last 2 years both below 0.5 | Knockout |
| Negative equity (financial) | Same as above but for banks/REITs | **Flag** (−6 pts penalty) |
| OCF/NI 1 year < 0.5 | Only last year below 0.5 | **Flag** (−4 pts penalty) |

**Sector detection** (`_is_financial`): string matching on Alpha Vantage `Sector`/`Industry` fields against `FINANCIAL_SECTORS` and `FINANCIAL_INDUSTRIES` sets. No LLM used.

**Altman Z-Score** (public company version):
```
Z = 1.2*(Working Capital/TA) + 1.4*(Retained Earnings/TA)
  + 3.3*(EBIT/TA) + 0.6*(Market Cap/TL) + 1.0*(Revenue/TA)
```
Skipped entirely for financial companies. For non-financials: Z < 1.1 = Knockout; 1.1–2.6 scores 0–5 pts linearly.

### Score Blocks

#### Block 1 — Quality / Profitability (30 pts)

| Metric | Method | Points |
|---|---|---|
| ROA level | Linear 0%→10% | 4 |
| ROA YoY | Earnings growth > 0 | 3 |
| ROE level | Linear 0%→20% | 3 |
| Gross margin YoY delta | Linear 0→+5% | 3 |
| Operating margin YoY delta | Linear 0→+5% | 3 |
| Asset turnover YoY | Improved | 3 |
| Net income > 0 | Binary | 3 |
| Operating income > 0 | Binary | 2 |
| FCF > 0 | Binary | 3 |
| OCF > Net Income (Piotroski) | Binary | 3 |
| Accrual penalty (flag) | OCF/NI < 0.5 last year | −4 |

#### Block 2 — Valuation (25 pts)

| Metric | Method | Points |
|---|---|---|
| Forward P/E | Inverse linear 10→40 | 6 |
| PEG ratio | Inverse linear 0.5→2.5 | 5 |
| EV/EBITDA | Inverse linear 5→20 | 5 |
| Price/Sales | Inverse linear 1→10 | 4 |
| Price/Book | Inverse linear 1→5 | 3 |
| Forward P/E < Trailing P/E | Binary | 2 |

#### Block 3 — Financial Strength (20 pts)

| Metric | Method | Points |
|---|---|---|
| Altman Z (non-financial only) | Linear 1.1→2.6 | 5 |
| Debt/Assets | Inverse linear 0.2→0.6 | 4 |
| Cash/Debt | Linear 0.1→0.5 | 3 |
| Leverage YoY declining | Binary | 3 |
| Current ratio YoY improving | Binary | 2 |
| OCF > CapEx | Binary | 3 |
| Neg. equity penalty (financial) | Flag | −6 |

> **Financial company normalization**: Altman's 5 pts are skipped. The remaining 15 pts are normalized to 20: `(positive_score / 15) * 20`.

#### Block 4 — Growth (15 pts)

| Metric | Method | Points |
|---|---|---|
| Revenue growth YoY | Linear 0%→20% | 4 |
| Earnings growth YoY | Linear 0%→25% | 4 |
| Net income trend (3yr) | Positive and rising | 3 |
| Operating income trend (3yr) | Positive and rising | 2 |
| No dilution | Shares stable or declining | 2 |

#### Block 5 — Momentum (10 pts)

| Metric | Method | Points |
|---|---|---|
| Price > 200-day MA | Binary | 4 |
| Golden cross (50MA > 200MA) | Binary | 3 |
| Distance to 52w high (≤15%) | Graduated | 2 |
| Beta 0.7–1.3 | Binary | 1 |

### Output

```python
{
  "passed_knockout": bool,
  "knockout_reasons": ["reason 1", ...],
  "score": float,           # 0–100, None if knockout
  "max_score": 100,
  "probability_up": float,  # 0.25–0.75, None if knockout
  "signal": str,            # "Stark bullish" / "Bullish" / ... / "Stark bearish"
  "blocks": {
    "quality":            {"score": float, "max": 30, "details": {...}},
    "valuation":          {"score": float, "max": 25, "details": {...}},
    "financial_strength": {"score": float, "max": 20, "details": {...}},
    "growth":             {"score": float, "max": 15, "details": {...}},
    "momentum":           {"score": float, "max": 10, "details": {...}},
  },
  "flags": ["accrual_warning_1yr", ...]
}
```

### Signal thresholds

| Score | Signal |
|---|---|
| ≥ 75 | Stark bullish |
| ≥ 62 | Bullish |
| ≥ 50 | Leicht bullish |
| ≥ 38 | Leicht bearish |
| ≥ 25 | Bearish |
| < 25 | Stark bearish |

---

## `agent.py` — LLM Agent

**Provider**: configurable via `.env` (`LLM_PROVIDER`: deepseek | openai | gemini | groq, or a custom `LLM_URL`/`LLM_MODEL` for e.g. local Ollama). Default model per provider in `_PROVIDER_DEFAULTS`. Temperature 0.3.

All four functions share `_call_llm(system, user, max_tokens)`.

### `analyze()` — Overall assessment (600 tokens)

Receives full score breakdown, key financials, segment data, analyst consensus. Returns: score driver explanation + bullish/bearish arguments + directional verdict. Max 300 words.

### `analyze_mda()` — MD&A reconstruction (700 tokens)

Combines the real Item 1A/Item 7 risk-factor and MD&A excerpts scraped by `filing_text.py` with multi-year numerical trends (revenue, margins, OCF, segments, liquidity) — the LLM synthesizes both into a coherent discussion rather than reconstructing purely from numbers. Output: three sections — quarterly results, liquidity, key risks.

### `extract_guidance()` — Implicit forward signals (500 tokens)

Reads forward-looking signals from CapEx levels, R&D spend, inventory, Forward vs. Trailing P/E difference, and analyst target vs. current price. No earnings call transcript is available. Output: capital allocation signals, PE implication, consensus outlook.

### `explain_anomalies()` — Anomaly explanation (500 tokens)

Ranks scoring blocks by fill rate, identifies metrics with 0 points, detects cross-metric discrepancies (e.g., high revenue growth + extreme P/E, positive FCF + negative EPS growth). Output: weakest block explanation, structural vs. cyclical assessment, block inconsistencies.

---

## Module Overview

| File | Responsibility |
|---|---|
| [main.py](main.py) | Entry point, cache check, pipeline orchestration |
| [extractor.py](extractor.py) | `extract_10k`, `extract_10q`, `extract_vantage` |
| [xbrl_helpers.py](xbrl_helpers.py) | Label constants, numeric XBRL fact pickers |
| [filing_text.py](filing_text.py) | Freitext (Risk Factors/MD&A/Legal) + Segmentdaten aus HTML/R-Files |
| [scorer.py](scorer.py) | Knockout filters + 5 scoring blocks |
| [agent.py](agent.py) | Multi-provider LLM analyses |
| [get_data.py](get_data.py) | SEC/Alpha Vantage API calls, file I/O |

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install requests beautifulsoup4 lxml
```

Create `.env` (see `.env.example`) with:

```
SEC_USER_AGENT: "YourAppName your-email@example.com"   # required by SEC, not a real key
Alpha_Vantage_API_KEY: "your_alpha_vantage_key_here"
LLM_API_KEY:  "your_llm_api_key_here"
LLM_PROVIDER: "deepseek"   # deepseek | openai | gemini | groq
```

SEC EDGAR needs no API key — only the `User-Agent` header above, read at request time in `get_data._sec_headers()` / `filing_text._sec_headers()`.

## Running the Agent

```bash
python main.py
# → Enter ticker symbol when prompted (e.g. TSLA, AAPL, MSFT)
# → If cached data exists, you will be asked whether to reuse it
```

Output sequence:
1. Cache check — reuse or re-fetch
2. Filing dates found (10-K, 10-Q, 8-K)
3. Download from SEC's free XBRL API (companyfacts, one call per ticker) + primary filing HTML (text sections, segments)
4. Score block breakdown
5. LLM: overall assessment
6. LLM: MD&A analysis
7. LLM: implicit guidance
8. LLM: anomaly explanation

JSON output files are saved to `output/<TICKER>_10k.json`, `_10q.json`, `_8k.json`, `_vantage.json`, plus `_10k_text.json`/`_10q_text.json`/`_8k_text.json` for the scraped free-text/segment data.

---

## Known Limitations

- **US filers only**: SEC EDGAR only has 10-K/10-Q filings for companies registered with the SEC — practically, US-domiciled/US-listed companies. Foreign private issuers filing 20-F/40-F are not covered.
- **Free text/segments are best-effort HTML scraping**: `companyfacts` only returns numbers, so `risk_factors`, `mda_highlights`, `mda_updates`, `risk_factor_changes`, `legal_proceedings` (10-K/10-Q) and `segments` (10-Q) come from `filing_text.py` scraping the primary filing HTML / SEC R-files directly. Verified against two differently-formatted filers (Microsoft, Johnson & Johnson), but without the schema guarantee `companyfacts` has, since EDGAR HTML isn't structured consistently across filers. Known edge cases:
  - A 10-Q can legitimately omit Item 1A (Risk Factors) if nothing changed since the last 10-K — `risk_factor_change_summary` is then `None`, not a bug.
  - `liquidity_capital_resources` (10-Q) is only populated if the exact sub-heading "Liquidity and Capital Resources" appears within the MD&A text.
  - Segment tables vary a lot by filer: some combine revenue, cost, and operating income in one table (full gross-margin calculation possible), others report sales only (`gross_profit`/`gross_margin_pct` then stays `None`). Filers with very granular breakdowns (geography × product line) are capped to the 10 largest "segments" by revenue.
- **`GrossProfit` not reported by all companies**: Some companies (e.g. Alphabet) only report `CostOfRevenue`. The extractor derives gross profit as `Revenue − CostOfRevenue` automatically.
- **QoQ change**: Only available if the prior quarter data is present in the same 10-Q filing (usually not).
- **Probability range capped at 25%–75%**: By design — the model does not claim certainty.
- **Alpha Vantage free tier**: Limited to 25 API calls/day. `Forward P/E`, `PEG`, analyst ratings may be unavailable for smaller tickers.
- **Missing filings**: If a filing cannot be fetched (API error or not found), the corresponding extraction step is skipped gracefully.
- **SEC rate limits**: `data.sec.gov`/`www.sec.gov` allow up to ~10 requests/second and require the `User-Agent` header set via `SEC_USER_AGENT` — otherwise requests are blocked with a 403.
