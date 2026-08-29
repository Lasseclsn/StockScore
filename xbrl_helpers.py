import re

# ---------------------------------------------------------------------------
# XBRL concept name mappings (fallback chains per metric)
# ---------------------------------------------------------------------------

LABELS_10k = {
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
    "cost_of_revenue": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
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
    "rd_expense": [
        "ResearchAndDevelopmentExpense",
    ],
    "sga_expense": [
        "SellingGeneralAndAdministrativeExpense",
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
        "cost_of_revenue": [
            "CostOfRevenue",
            "CostOfGoodsAndServicesSold",
            "CostOfGoodsSold",
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
        "inventory": [
            "InventoryNet",
            "Inventories",
        ],
        "accounts_receivable": [
            "AccountsReceivableNetCurrent",
            "ReceivablesNetCurrent",
        ],
        "debt_current": [
            "LongTermDebtAndFinanceLeasesCurrent",
            "LongTermDebtCurrent",
            "DebtCurrent",
        ],
        "debt_noncurrent": [
            "LongTermDebtAndFinanceLeasesNoncurrent",
            "LongTermDebtNoncurrent",
            "LongTermDebt",
        ],
        "current_assets": [
            "AssetsCurrent",
        ],
        "current_liabilities": [
            "LiabilitiesCurrent",
        ],
        "retained_earnings": [
            "RetainedEarningsAccumulatedDeficit",
            "RetainedEarnings",
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


# ---------------------------------------------------------------------------
# Low-level value helpers
# ---------------------------------------------------------------------------

def _clean(s):
    if s is None:
        return None
    s = str(s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _period_end(item):
    period = item.get("period", {})
    return period.get("endDate") or period.get("instant") or ""


def _value(item):
    try:
        return float(item["value"])
    except Exception:
        return None


def _safe_change(current, previous):
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / previous


# ---------------------------------------------------------------------------
# JSON traversal
# ---------------------------------------------------------------------------

def _walk(obj, path=""):
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
    for path, k, v in _walk(obj):
        if k == key:
            return v
    return None


def _find_key_contains(obj, keywords):
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
    if not path or str(path).startswith("__derived__"):
        return None
    cur = obj
    for part in str(path).split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


# ---------------------------------------------------------------------------
# Value serialization
# ---------------------------------------------------------------------------

def _stringify_value(v):
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


# ---------------------------------------------------------------------------
# Fact pickers
# ---------------------------------------------------------------------------

def _pick_any(data, names):
    for name in names:
        if not name or str(name).startswith("__derived__"):
            continue
        v = _get_by_path(data, name)
        if v is not None:
            return _stringify_value(v)
        last_key = str(name).split(".")[-1]
        v = _find_key(data, last_key)
        if v is not None:
            return _stringify_value(v)
        key_hits = _find_key_contains(data, [name, last_key])
        for path, val in key_hits:
            if val is not None:
                return _stringify_value(val)
    return None


def _duration_days(start, end):
    try:
        from datetime import date as dt
        return (dt.fromisoformat(end) - dt.fromisoformat(start)).days
    except Exception:
        return None


def _pick(data, names):
    best = None
    best_date = ""
    best_duration = None
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
            val = _value(item)
            date = _period_end(item)
            if val is None or not date:
                continue
            period = item.get("period", {})
            duration = _duration_days(period.get("startDate"), date) if period.get("startDate") else None
            if date > best_date:
                best_date = date
                best = val
                best_duration = duration
            elif date == best_date and duration is not None and (best_duration is None or duration < best_duration):
                best = val
                best_duration = duration
    return best


def _pick_for_period(data, names, start_date=None, end_date=None):
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
                best = {"value": val, "start": start, "end": end}
    return best


def _pick_all_periods(data, names):
    result = {}
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
            val = _value(item)
            date = _period_end(item)
            if val is None or not date:
                continue
            if date not in result:
                result[date] = val
    return result


def _pick_prior_instant(data, names):
    seen = {}
    for name in names:
        facts = _find_key(data, name)
        if not isinstance(facts, list):
            continue
        for item in facts:
            if not isinstance(item, dict):
                continue
            if "segment" in item:
                continue
            period = item.get("period", {})
            if "instant" not in period:
                continue
            val = _value(item)
            date = period.get("instant", "")
            if val is not None and date and date not in seen:
                seen[date] = val
    sorted_dates = sorted(seen.keys(), reverse=True)
    if len(sorted_dates) < 2:
        return None
    return seen[sorted_dates[1]]


# ---------------------------------------------------------------------------
# YoY / QoQ derivations
# ---------------------------------------------------------------------------

def _derive_yoy_change(data):
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
    previous = _pick_for_period(data, revenue_names, start_date=prev_start, end_date=prev_end)
    return _safe_change(latest["value"], previous)


def _derive_qoq_change(data):
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
    previous = _pick_for_period(data, revenue_names, start_date=prev_start, end_date=prev_end)
    return _safe_change(latest["value"], previous)


