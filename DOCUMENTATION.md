# Finance Agent — Technical Documentation

## Overview

A CLI tool that fetches SEC filings and market data for a given stock ticker, extracts structured financial metrics, applies a probabilistic scoring model (0–100), and runs four LLM analyses to predict whether a stock price is likely to rise or fall in the next quarter.

---

## Project Structure

```
finance_agent/
├── main.py          # Entry point + pipeline orchestration
├── extractor.py     # extract_10k(), extract_10q(), extract_vantage()
├── xbrl_helpers.py  # XBRL label constants + all parsing/traversal helpers
├── scorer.py        # Scoring model (knockout filters + 5 blocks)
├── agent.py         # DeepSeek LLM agent (4 analysis functions)
├── get_data.py      # SEC/Alpha Vantage API calls, file I/O
├── .env             # API keys (not committed)
├── .env.example     # Key name reference
├── output/          # JSON files saved per ticker
└── system_instruction.json
```

### Import chain

```
main.py
  ├── extractor.py  →  xbrl_helpers.py
  ├── scorer.py
  ├── agent.py
  └── get_data.py
        └── sec_api.XbrlApi  (lazy — imported only inside fetch_and_save_filing)
```

---

## Data Sources

| Source | Data | API |
|---|---|---|
| SEC EDGAR (via sec-api.io) | 10-K, 10-Q, 8-K filings as XBRL JSON | `XbrlApi.xbrl_to_json()` |
| SEC EDGAR (direct) | Company submission metadata, CIK lookup | `data.sec.gov/submissions/` |
| Alpha Vantage | Market data, valuation multiples, analyst ratings | `OVERVIEW` endpoint |

### API Keys required (`.env` format: `Key: "value"`)

```
SEC_API_KEY
Alpha_Vantage_API_KEY
DeepSeek_API_KEY
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
agent.analyze_mda()       → MD&A reconstruction from numbers
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
| `getCik(ticker)` | Resolves ticker to SEC CIK via sec-api.io |
| `getSubmissionData(cik)` | Fetches filing index from `data.sec.gov` |
| `get_latest_filing_by_form(data, form)` | Returns most recent filing of given type (10-K, 10-Q, 8-K) |
| `fetch_and_save_filing(filing, cik, ticker, suffix)` | Converts filing to XBRL JSON via sec-api.io, saves to `output/` |
| `fetch_and_save_overview(ticker)` | Fetches Alpha Vantage OVERVIEW, saves to `output/` |

> `XbrlApi` is imported **lazily** inside `fetch_and_save_filing()` to avoid slow startup — the sec-api library loads heavy dependencies (pandas, numpy) and would otherwise block the prompt by several minutes.

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
| `_pick(data, names)` | Most recent unsegmented numeric fact from a fallback name list |
| `_pick_all_periods(data, names)` | `{end_date: value}` for all periods — used for multi-year trends |
| `_pick_prior_instant(data, names)` | Second most recent instant value (prior fiscal year balance sheet) |
| `_pick_for_period(data, names, start, end)` | Fact for a specific date range — used for YoY/QoQ derivation |
| `_latest_duration_fact(data, names)` | Most recent duration fact with both start and end date |
| `_extract_segment_data(data)` | Revenue + gross profit by business segment via XBRL segment axis |
| `_safe_change(current, previous)` | `(current - previous) / previous`, returns `None` on division by zero |
| `_derive_yoy_change(data)` | Revenue YoY from prior-year quarter in same filing |
| `_derive_qoq_change(data)` | Revenue QoQ if prior quarter is present in same filing |
| `_mda_highlights(data)` | Up to 3 key sentences from MD&A section |
| `_liquidity_text(data)` | Liquidity & Capital Resources section text |
| `_results_text(data)` | Results of Operations section text |
| `_risk_factor_summary(data)` | Risk Factors section text |
| `_legal_summary(data)` | Legal Proceedings section text |

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
  "risk_factors": ["sentence 1", ...],   # up to 5 sentences containing "risk"
  "mda_highlights": ["sentence 1", ...]  # up to 3 MDA key sentences
}
```

**`gross_profit` fallback**: If the company does not report `GrossProfit` as an XBRL concept (e.g. Alphabet), it is derived as `Revenue − CostOfRevenue`. The same fallback applies to multi-year trend data.

**Risk factor extraction**: Text is capped at 2,000,000 characters before regex search to prevent catastrophic backtracking on large filings.

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

## `agent.py` — DeepSeek LLM Agent

**Model**: `deepseek-chat` (DeepSeek-V3) via OpenAI-compatible REST API at `https://api.deepseek.com/chat/completions`. Temperature 0.3.

All four functions share `_call_deepseek(system, user, max_tokens)`.

### `analyze()` — Overall assessment (600 tokens)

Receives full score breakdown, key financials, segment data, analyst consensus. Returns: score driver explanation + bullish/bearish arguments + directional verdict. Max 300 words.

### `analyze_mda()` — MD&A reconstruction (700 tokens)

XBRL does not contain narrative text. DeepSeek reconstructs the likely management discussion from multi-year numerical trends (revenue, margins, OCF, segments, liquidity). Output: three sections — quarterly results, liquidity, key risks.

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
| [xbrl_helpers.py](xbrl_helpers.py) | Label constants, XBRL traversal, text helpers |
| [scorer.py](scorer.py) | Knockout filters + 5 scoring blocks |
| [agent.py](agent.py) | DeepSeek LLM analyses |
| [get_data.py](get_data.py) | API calls, file I/O, lazy XbrlApi import |

---

## Running the Agent

```bash
# Activate virtual environment
source .venv/bin/activate

# Run
python main.py
# → Enter ticker symbol when prompted (e.g. TSLA, AAPL, MSFT)
# → If cached data exists, you will be asked whether to reuse it
```

Output sequence:
1. Cache check — reuse or re-fetch
2. Filing dates found (10-K, 10-Q, 8-K)
3. Download + conversion via sec-api.io (~30–90 s)
4. Score block breakdown
5. DeepSeek: overall assessment
6. DeepSeek: MD&A analysis
7. DeepSeek: implicit guidance
8. DeepSeek: anomaly explanation

JSON output files are saved to `output/<TICKER>_10k.json`, `_10q.json`, `_8k.json`, `_vantage.json`.

---

## Known Limitations

- **No narrative MD&A text**: XBRL JSON does not include the free-text sections of SEC filings. DeepSeek reconstructs the likely discussion from numbers.
- **`GrossProfit` not reported by all companies**: Some companies (e.g. Alphabet) only report `CostOfRevenue`. The extractor derives gross profit as `Revenue − CostOfRevenue` automatically.
- **QoQ change**: Only available if the prior quarter data is present in the same 10-Q filing (usually not).
- **Segment extraction**: Relies on the `StatementBusinessSegmentsAxis` XBRL dimension. Companies without XBRL segment tagging return empty segment data.
- **Probability range capped at 25%–75%**: By design — the model does not claim certainty.
- **Alpha Vantage free tier**: Limited to 25 API calls/day. `Forward P/E`, `PEG`, analyst ratings may be unavailable for smaller tickers.
- **Missing filings**: If a filing cannot be fetched (API error or not found), the corresponding extraction step is skipped gracefully.
