import get_data
import extract_data
import requests
import re
import json

from sec_api import XbrlApi
from pathlib import Path


MODEL = "gemini-2.5-flash"
BASE_DIR = Path(__file__).parent
SYSTEM_INSTRUCTION_PATH = BASE_DIR / "system_instruction.json"

import json
import re
from pathlib import Path


LABELS_10k = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "Revenue",
        "Revenues",
        "TotalRevenue",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
        "IncomeFromOperations",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncome",
    ],
    "diluted_eps": [
        "EarningsPerShareDiluted",
        "DilutedEarningsPerShare",
        "DilutedEPS",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
    ],
    "total_assets": [
        "Assets",
    ],
    "total_liabilities": [
        "Liabilities",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByOperatingActivities",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "CapitalExpenditures",
        "PurchasesOfPropertyAndEquipment",
    ],
}

LABELS_10Q = {
    "core_metrics": {
        "revenue": [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "Revenue",
            "Revenues",
            "TotalRevenue",
        ],
        "gross_profit": [
            "GrossProfit",
        ],
        "operating_income": [
            "OperatingIncomeLoss",
            "IncomeFromOperations",
        ],
        "net_income": [
            "NetIncomeLoss",
            "ProfitLoss",
            "NetIncome",
        ],
        "eps_diluted": [
            "EarningsPerShareDiluted",
            "DilutedEarningsPerShare",
        ],
        "cash": [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ],
        "total_assets": [
            "Assets",
            "TotalAssets",
        ],
        "total_liabilities": [
            "Liabilities",
            "TotalLiabilities",
        ],
        "stockholders_equity": [
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            "Equity",
        ],
        "operating_cash_flow": [
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivities",
        ],
        "capex": [
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
        ],
        "shares_outstanding": [
            "EntityCommonStockSharesOutstanding",
            "CommonStockSharesOutstanding",
        ],
    },
    "comparisons": {
        "qoq_change": [
            "__derived__.qoq_change",
        ],
        "yoy_change": [
            "__derived__.yoy_change",
        ],
        "current_quarter": [
            "CoverPage.DocumentFiscalPeriodFocus",
        ],
        "current_fiscal_year": [
            "CoverPage.DocumentFiscalYearFocus",
        ],
        "document_period_end": [
            "CoverPage.DocumentPeriodEndDate",
        ],
    },
    "mda_updates": {
        "liquidity_capital_resources": [
            "ManagementDiscussionAndAnalysis.LiquidityAndCapitalResources",
            "Item2.ManagementsDiscussionAndAnalysis.LiquidityAndCapitalResources",
            "Item2.LiquidityAndCapitalResources",
            "MDA.liquidity",
            "MDA.capital_resources",
        ],
        "results_of_operations": [
            "ManagementDiscussionAndAnalysis.ResultsOfOperations",
            "Item2.ManagementsDiscussionAndAnalysis.ResultsOfOperations",
            "Item2.ResultsOfOperations",
            "MDA.results_of_operations",
        ],
    },
    "risk_factor_changes": {
        "risk_factor_changes_flag": [
            "__derived__.risk_factor_changes_flag",
        ],
        "risk_factor_change_summary": [
            "__derived__.risk_factor_change_summary",
            "PartIIItem1A.RiskFactors",
            "RiskFactors",
        ],
    },
    "legal_proceedings": {
        "legal_proceedings_update_flag": [
            "__derived__.legal_proceedings_update_flag",
        ],
        "legal_proceedings_summary": [
            "__derived__.legal_proceedings_summary",
            "PartIIItem1.LegalProceedings",
            "LegalProceedings",
        ],
    },
}

LABELS_8K = {
    "item_number": [
        "Items",
        "Item",
        "ItemNumber",
        "item_number",
        "itemNumber",
        "itemNo",
        "sections.item",
    ],
    "event_date": [
        "EventDate",
        "event_date",
        "eventDate",
        "DateOfReport",
        "date_of_report",
        "DateOfEarliestEventReported",
    ],
    "short_summary": [
        "Summary",
        "summary",
        "ShortSummary",
        "short_summary",
        "Description",
        "description",
        "short_summary",
    ],
    "flags": {
        "earnings": [
            "flags.earnings",
            "flags.earnings",
            "is_earnings",
        ],
        "management": [
            "__derived__.flags.management",
            "flags.management",
            "is_management",
        ],
        "debt": [
            "flags.debt",
            "flags.debt",
            "is_debt",
        ],
        "m_and_a": [
            "flags.m_and_a",
            "flags.m_and_a",
            "flags.ma",
            "is_ma",
            "is_m_and_a",
        ],
        "impairment": [
            "_flags.impairment",
            "flags.impairment",
            "is_impairment",
        ],
        "auditor": [
            "flags.auditor",
            "flags.auditor",
            "is_auditor",
        ],
        "restatement": [
            "flags.restatement",
            "flags.restatement",
            "is_restatement",
        ],
        "delisting": [
            "__derived__.flags.delisting",
            "flags.delisting",
            "is_delisting",
        ],
    },
    "item_to_flag_rules": {
        "2.02": ["earnings"],
        "5.02": ["management"],
        "2.03": ["debt"],
        "2.06": ["impairment"],
        "4.01": ["auditor"],
        "4.02": ["restatement"],
        "3.01": ["delisting"],
        "1.01": ["m_and_a"],
        "1.02": ["m_and_a"],
    },
}


def _clean(s):
    if s is None:
        return None
    s = str(s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _year(item):
    period = item.get("period", {})
    s = period.get("endDate") or period.get("instant")
    return int(s[:4]) if s else -1


def _period_end(item):
    period = item.get("period", {})
    return period.get("endDate") or period.get("instant") or ""


def _value(item):
    try:
        return float(item["value"])
    except Exception:
        return None


def _walk(obj, path=""):
    """
    Rekursiver Generator über das komplette JSON.
    Gibt zurück: (path, key, value)
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f"{path}.{k}" if path else k
            yield new_path, k, v
            yield from _walk(v, new_path)

    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            new_path = f"{path}[{i}]"
            yield new_path, str(i), v
            yield from _walk(v, new_path)


def _find_key(obj, key):
    """
    Kompatibel zu deiner alten Funktion:
    rekursive exakte Key-Suche.
    """
    for path, k, v in _walk(obj):
        if k == key:
            return v
    return None


def _find_key_contains(obj, keywords):
    """
    Rekursive Suche nach Keys/Pfaden, die Keywords enthalten.
    """
    if isinstance(keywords, str):
        keywords = [keywords]

    keywords = [str(x).lower() for x in keywords if x]
    hits = []

    for path, k, v in _walk(obj):
        haystack = f"{path} {k}".lower()
        if any(kw in haystack for kw in keywords):
            hits.append((path, v))

    return hits


def _get_by_path(obj, path):
    """
    Liest z.B. 'CoverPage.DocumentFiscalPeriodFocus'
    aus verschachtelten Dicts.
    """
    if not path or str(path).startswith("__derived__"):
        return None

    cur = obj

    for part in str(path).split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None

    return cur


def _collect_text(obj):
    """
    Sammelt alle Strings im JSON rekursiv.
    Wird von extract_10k benutzt.
    """
    parts = []

    for path, k, v in _walk(obj):
        if isinstance(v, str):
            cleaned = _clean(v)
            if cleaned:
                parts.append(cleaned)

    return parts


def _stringify_value(v):
    """
    Macht aus gefundenen Dict/List/String-Werten brauchbare Werte.
    """
    if v is None:
        return None

    if isinstance(v, str):
        return _clean(v)

    if isinstance(v, (int, float, bool)):
        return v

    if isinstance(v, list):
        texts = []

        for item in v:
            if isinstance(item, dict) and "value" in item:
                val = item.get("value")
                if val is not None:
                    texts.append(str(val))
            elif isinstance(item, str):
                cleaned = _clean(item)
                if cleaned:
                    texts.append(cleaned)

        return " ".join(texts).strip() if texts else v

    if isinstance(v, dict):
        if "value" in v:
            return v.get("value")

        texts = []

        for _, _, sub_v in _walk(v):
            if isinstance(sub_v, str):
                cleaned = _clean(sub_v)
                if cleaned:
                    texts.append(cleaned)

        return " ".join(texts).strip() if texts else v

    return v


def _pick_any(data, names):
    """
    Für einfache Text/Bool/Metadata-Felder.

    Wichtig:
    Diese Funktion sucht NICHT mehr aggressiv im gesamten Textinhalt.
    Dadurch verhindert sie falsche Treffer bei MD&A/Risk/Legal.
    """
    for name in names:
        if not name or str(name).startswith("__derived__"):
            continue

        # 1. Dot-Path exakt
        v = _get_by_path(data, name)
        if v is not None:
            return _stringify_value(v)

        last_key = str(name).split(".")[-1]

        # 2. Exakter Key rekursiv
        v = _find_key(data, last_key)
        if v is not None:
            return _stringify_value(v)

        # 3. Nur Key/Pfad enthält Suchbegriff
        key_hits = _find_key_contains(data, [name, last_key])
        for path, val in key_hits:
            if val is not None:
                return _stringify_value(val)

    return None


def _pick(data, names):
    """
    Für numerische XBRL-Facts.

    Sucht rekursiv nach Fact-Listen und nimmt den neuesten
    unsegmentierten Wert.
    """
    best = None
    best_date = ""

    for name in names:
        facts = _find_key(data, name)

        if not isinstance(facts, list):
            continue

        for item in facts:
            if not isinstance(item, dict):
                continue

            if "value" not in item or "period" not in item:
                continue

            # Segmentierte Werte überspringen,
            # damit möglichst konsolidierte Werte genutzt werden.
            if "segment" in item:
                continue

            val = _value(item)
            date = _period_end(item)

            if val is None:
                continue

            if date > best_date:
                best_date = date
                best = val

    return best


def _pick_for_period(data, names, start_date=None, end_date=None):
    """
    Holt einen numerischen Fact für einen konkreten Zeitraum.
    Nützlich für YoY/QoQ.
    """
    for name in names:
        facts = _find_key(data, name)

        if not isinstance(facts, list):
            continue

        for item in facts:
            if not isinstance(item, dict):
                continue

            if "value" not in item or "period" not in item:
                continue

            if "segment" in item:
                continue

            period = item.get("period", {})
            item_start = period.get("startDate")
            item_end = period.get("endDate") or period.get("instant")

            if start_date is not None and item_start != start_date:
                continue

            if end_date is not None and item_end != end_date:
                continue

            val = _value(item)
            if val is not None:
                return val

    return None


def _latest_duration_fact(data, names):
    """
    Findet den neuesten Duration-Fact mit startDate und endDate.
    """
    best = None
    best_end = ""

    for name in names:
        facts = _find_key(data, name)

        if not isinstance(facts, list):
            continue

        for item in facts:
            if not isinstance(item, dict):
                continue

            if "value" not in item or "period" not in item:
                continue

            if "segment" in item:
                continue

            period = item.get("period", {})
            start = period.get("startDate")
            end = period.get("endDate")

            if not start or not end:
                continue

            val = _value(item)
            if val is None:
                continue

            if end > best_end:
                best_end = end
                best = {
                    "value": val,
                    "start": start,
                    "end": end,
                }

    return best


def _safe_change(current, previous):
    if current is None or previous in (None, 0):
        return None

    return (current - previous) / previous


def _derive_yoy_change(data):
    """
    Berechnet YoY für Revenue des aktuellen Quartals,
    wenn das Vorjahresquartal im Filing vorhanden ist.
    """
    revenue_names = LABELS_10Q["core_metrics"]["revenue"]
    latest = _latest_duration_fact(data, revenue_names)

    if not latest:
        return None

    start = latest["start"]
    end = latest["end"]

    try:
        prev_start = f"{int(start[:4]) - 1}{start[4:]}"
        prev_end = f"{int(end[:4]) - 1}{end[4:]}"
    except Exception:
        return None

    previous = _pick_for_period(
        data,
        revenue_names,
        start_date=prev_start,
        end_date=prev_end,
    )

    return _safe_change(latest["value"], previous)


def _derive_qoq_change(data):
    """
    QoQ ist aus einem einzelnen 10-Q oft nicht vorhanden.
    Diese Funktion gibt None zurück, wenn das direkte Vorquartal
    nicht im gleichen JSON steht.
    """
    revenue_names = LABELS_10Q["core_metrics"]["revenue"]
    latest = _latest_duration_fact(data, revenue_names)

    if not latest:
        return None

    start = latest["start"]

    quarter_map = {
        "01-01": None,
        "04-01": ("01-01", "03-31"),
        "07-01": ("04-01", "06-30"),
        "10-01": ("07-01", "09-30"),
    }

    year = start[:4]
    md = start[5:10]

    if md not in quarter_map or quarter_map[md] is None:
        return None

    prev_start_md, prev_end_md = quarter_map[md]
    prev_start = f"{year}-{prev_start_md}"
    prev_end = f"{year}-{prev_end_md}"

    previous = _pick_for_period(
        data,
        revenue_names,
        start_date=prev_start,
        end_date=prev_end,
    )

    return _safe_change(latest["value"], previous)


def _find_text_blocks_by_path(data, keywords, min_len=30):
    """
    Sucht Textblöcke NUR über Key/Pfad.
    Das verhindert False Positives wie Revenue Recognition bei Risk Factors.
    """
    if isinstance(keywords, str):
        keywords = [keywords]

    keywords = [str(kw).lower() for kw in keywords if kw]
    hits = []

    for path, k, v in _walk(data):
        if not isinstance(v, str):
            continue

        cleaned = _clean(v)
        if not cleaned or len(cleaned) < min_len:
            continue

        haystack_path = f"{path} {k}".lower()

        if any(kw in haystack_path for kw in keywords):
            hits.append(
                {
                    "path": path,
                    "text": cleaned,
                }
            )

    return hits


def _find_text_blocks_by_heading(data, headings, min_len=30):
    """
    Sucht Textblöcke über echte Überschriften im Text.
    Nur vorsichtig als Fallback benutzen.
    """
    if isinstance(headings, str):
        headings = [headings]

    headings = [str(h).lower() for h in headings if h]
    hits = []

    for path, k, v in _walk(data):
        if not isinstance(v, str):
            continue

        cleaned = _clean(v)
        if not cleaned or len(cleaned) < min_len:
            continue

        text_l = cleaned.lower()

        for heading in headings:
            if heading in text_l[:1500]:
                hits.append(
                    {
                        "path": path,
                        "text": cleaned,
                    }
                )
                break

    return hits


def _get_section_text_by_path(data, section_names, limit_chars=None):
    hits = _find_text_blocks_by_path(data, section_names)

    seen = set()
    parts = []

    for hit in hits:
        text = hit["text"]
        if text and text not in seen:
            seen.add(text)
            parts.append(text)

    result = " ".join(parts).strip()

    if limit_chars and result:
        return result[:limit_chars]

    return result or None


def _get_section_text_by_heading(data, headings, limit_chars=None):
    hits = _find_text_blocks_by_heading(data, headings)

    seen = set()
    parts = []

    for hit in hits:
        text = hit["text"]
        if text and text not in seen:
            seen.add(text)
            parts.append(text)

    result = " ".join(parts).strip()

    if limit_chars and result:
        return result[:limit_chars]

    return result or None


def _mda_highlights(data, limit=3):
    text = _get_section_text_by_path(
        data,
        [
            "ManagementDiscussionAndAnalysis",
            "ManagementsDiscussionAndAnalysis",
            "ResultsOfOperations",
            "LiquidityAndCapitalResources",
        ],
        limit_chars=12000,
    )

    if not text:
        return []

    sents = re.split(r"(?<=[.!?])\s+", text)
    out = []

    for s in sents:
        ls = s.lower()

        if any(
            x in ls
            for x in [
                "results of operations",
                "liquidity",
                "capital resources",
                "cash",
                "gross profit",
                "operating income",
                "revenue",
            ]
        ):
            cleaned = s.strip()
            if cleaned and cleaned not in out:
                out.append(cleaned)

        if len(out) == limit:
            break

    return out


def _liquidity_text(data, limit_chars=3000):
    return _get_section_text_by_path(
        data,
        [
            "LiquidityAndCapitalResources",
            "LiquidityCapitalResources",
            "CapitalResources",
        ],
        limit_chars=limit_chars,
    )


def _results_text(data, limit_chars=3000):
    return _get_section_text_by_path(
        data,
        [
            "ResultsOfOperations",
            "ManagementDiscussionAndAnalysis",
            "ManagementsDiscussionAndAnalysis",
        ],
        limit_chars=limit_chars,
    )


def _risk_factor_summary(data, limit_chars=3000):
    text = _get_section_text_by_path(
        data,
        [
            "RiskFactors",
            "RiskFactor",
            "PartIIItem1A",
        ],
        limit_chars=limit_chars,
    )

    if text:
        return text

    return _get_section_text_by_heading(
        data,
        [
            "risk factors",
            "item 1a",
        ],
        limit_chars=limit_chars,
    )


def _legal_summary(data, limit_chars=3000):
    text = _get_section_text_by_path(
        data,
        [
            "LegalProceedings",
            "PartIIItem1",
        ],
        limit_chars=limit_chars,
    )

    if text:
        return text

    commitments = _get_section_text_by_path(
        data,
        [
            "CommitmentsAndContingencies",
            "CommitmentsandContingencies",
            "CommitmentsContingencies",
        ],
        limit_chars=12000,
    )

    if commitments and "legal proceedings" in commitments.lower():
        idx = commitments.lower().find("legal proceedings")
        return commitments[idx : idx + limit_chars]

    return _get_section_text_by_heading(
        data,
        [
            "legal proceedings",
            "litigation",
        ],
        limit_chars=limit_chars,
    )


def extract_10k(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    metrics = {k: _pick(data, v) for k, v in LABELS_10k.items()}

    ocf = metrics.get("operating_cash_flow")
    capex = metrics.get("capex")

    metrics["free_cash_flow"] = (
        ocf - abs(capex) if ocf is not None and capex is not None else None
    )

    text = re.sub(r"\s+", " ", " ".join(_collect_text(data)))
    risk_sents = re.findall(r"[^.]*risk[^.]*\.", text, flags=re.I)[:5]

    return {
        "metrics": metrics,
        "risk_factors": [s.strip() for s in risk_sents],
        "mda_highlights": _mda_highlights(data),
    }


def extract_10q(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    out = {
        "core_metrics": {},
        "comparisons": {},
        "mda_updates": {},
        "risk_factor_changes": {},
        "legal_proceedings": {},
    }

    # 1) Numerische Facts
    for metric, names in LABELS_10Q["core_metrics"].items():
        out["core_metrics"][metric] = _pick(data, names)

    # 2) Free Cash Flow
    ocf = out["core_metrics"].get("operating_cash_flow")
    capex = out["core_metrics"].get("capex")

    out["core_metrics"]["free_cash_flow"] = (
        ocf - abs(capex) if ocf is not None and capex is not None else None
    )

    # 3) Comparisons
    for key, names in LABELS_10Q["comparisons"].items():
        out["comparisons"][key] = _pick_any(data, names)

    out["comparisons"]["yoy_change"] = _derive_yoy_change(data)
    out["comparisons"]["qoq_change"] = _derive_qoq_change(data)

    out["comparisons"]["current_quarter"] = _get_by_path(
        data, "CoverPage.DocumentFiscalPeriodFocus"
    ) or out["comparisons"].get("current_quarter")

    out["comparisons"]["current_fiscal_year"] = _get_by_path(
        data, "CoverPage.DocumentFiscalYearFocus"
    ) or out["comparisons"].get("current_fiscal_year")

    out["comparisons"]["document_period_end"] = _get_by_path(
        data, "CoverPage.DocumentPeriodEndDate"
    ) or out["comparisons"].get("document_period_end")

    # 4) MD&A Updates
    out["mda_updates"]["liquidity_capital_resources"] = _liquidity_text(data)

    out["mda_updates"]["results_of_operations"] = _results_text(data)

    out["mda_updates"]["highlights"] = _mda_highlights(data)

    # 5) Risk Factors
    risk_text = _risk_factor_summary(data)

    out["risk_factor_changes"]["risk_factor_change_summary"] = risk_text
    out["risk_factor_changes"]["risk_factor_changes_flag"] = bool(risk_text)

    # 6) Legal Proceedings
    legal_text = _legal_summary(data)

    out["legal_proceedings"]["legal_proceedings_summary"] = legal_text
    out["legal_proceedings"]["legal_proceedings_update_flag"] = bool(legal_text)

    return out


def main() -> None:
    ticker_symbol = input("Geben Sie Ihr Ticker-Symbol ein: ")
    ticker_symbol = ticker_symbol.upper()

    # cik = get_data.getCik(ticker_symbol)
    # submission_data = get_data.getSubmissionData(cik)

    # xbrl_api = XbrlApi(api_key=get_data.load_api_key("SEC_API_KEY"))

    # latest_10k = get_data.get_latest_filing_by_form(submission_data, "10-K")
    # latest_10q = get_data.get_latest_filing_by_form(submission_data, "10-Q")
    # latest_8k = get_data.get_latest_filing_by_form(submission_data, "8-K")

    # get_data.fetch_and_save_filing(latest_10k, cik, ticker_symbol, "10K", xbrl_api)
    # get_data.fetch_and_save_filing(latest_10q, cik, ticker_symbol, "10Q", xbrl_api)
    # get_data.fetch_and_save_filing(latest_8k, cik, ticker_symbol, "8K", xbrl_api)

    # get_data.fetch_and_save_overview(ticker_symbol)

    # values_10k = extract_10k(BASE_DIR / "output" / f"{ticker_symbol}_10k.json")

    # print(values_10k)

    values_10q = extract_10q(BASE_DIR / "output" / f"{ticker_symbol}_10q.json")

    print(values_10q)

if __name__ == "__main__":
    main()
