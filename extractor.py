import json
from pathlib import Path

from xbrl_helpers import (
    LABELS_10k,
    LABELS_10Q,
    _pick,
    _pick_any,
    _pick_prior_instant,
    _pick_all_periods,
    _pick_for_period,
    _get_by_path,
    _derive_yoy_change,
    _derive_qoq_change,
    _safe_change,
)


def _load_text_companion(path) -> dict:
    """Lädt die von filing_text.py erzeugte {TICKER}_{suffix}_text.json, falls vorhanden."""
    text_path = Path(str(path).replace(".json", "_text.json"))
    if not text_path.exists():
        return {}
    try:
        return json.loads(text_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def extract_vantage(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    def _f(key):
        v = data.get(key)
        if v in (None, "None", ""):
            return None
        try:
            return float(v)
        except Exception:
            return v

    def _i(key):
        v = _f(key)
        return int(v) if isinstance(v, float) else None

    strong_buy  = _i("AnalystRatingStrongBuy")  or 0
    buy         = _i("AnalystRatingBuy")         or 0
    hold        = _i("AnalystRatingHold")        or 0
    sell        = _i("AnalystRatingSell")        or 0
    strong_sell = _i("AnalystRatingStrongSell")  or 0
    total = strong_buy + buy + hold + sell + strong_sell

    return {
        "valuation": {
            "market_cap":         _f("MarketCapitalization"),
            "pe_ratio":           _f("PERatio"),
            "forward_pe":         _f("ForwardPE"),
            "peg_ratio":          _f("PEGRatio"),
            "price_to_book":      _f("PriceToBookRatio"),
            "price_to_sales_ttm": _f("PriceToSalesRatioTTM"),
            "ev_to_revenue":      _f("EVToRevenue"),
            "ev_to_ebitda":       _f("EVToEBITDA"),
        },
        "profitability": {
            "profit_margin":       _f("ProfitMargin"),
            "operating_margin_ttm":_f("OperatingMarginTTM"),
            "roa":                 _f("ReturnOnAssetsTTM"),
            "roe":                 _f("ReturnOnEquityTTM"),
            "ebitda":              _f("EBITDA"),
            "eps_ttm":             _f("DilutedEPSTTM"),
            "gross_profit_ttm":    _f("GrossProfitTTM"),
            "revenue_ttm":         _f("RevenueTTM"),
        },
        "growth": {
            "earnings_growth_yoy": _f("QuarterlyEarningsGrowthYOY"),
            "revenue_growth_yoy":  _f("QuarterlyRevenueGrowthYOY"),
        },
        "analyst_consensus": {
            "target_price":   _f("AnalystTargetPrice"),
            "strong_buy":     strong_buy,
            "buy":            buy,
            "hold":           hold,
            "sell":           sell,
            "strong_sell":    strong_sell,
            "total_analysts": total,
            "bullish_pct":    round((strong_buy + buy) / total, 4) if total else None,
            "bearish_pct":    round((sell + strong_sell) / total, 4) if total else None,
        },
        "metadata": {
            "sector":         data.get("Sector"),
            "industry":       data.get("Industry"),
            "asset_type":     data.get("AssetType"),
            "latest_quarter": data.get("LatestQuarter"),
        },
        "market_data": {
            "beta":                  _f("Beta"),
            "week_52_high":          _f("52WeekHigh"),
            "week_52_low":           _f("52WeekLow"),
            "ma_50_day":             _f("50DayMovingAverage"),
            "ma_200_day":            _f("200DayMovingAverage"),
            "book_value_per_share":  _f("BookValue"),
            "shares_outstanding":    _f("SharesOutstanding"),
            "current_price_derived": round(_f("MarketCapitalization") / _f("SharesOutstanding"), 2)
            if _f("MarketCapitalization") and _f("SharesOutstanding")
            else None,
        },
    }


def extract_10k(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    text = _load_text_companion(path)

    metrics = {k: _pick(data, v) for k, v in LABELS_10k.items()}

    ocf   = metrics.get("operating_cash_flow")
    capex = metrics.get("capex")
    metrics["free_cash_flow"] = (
        ocf - abs(capex) if ocf is not None and capex is not None else None
    )

    revenue          = metrics.get("revenue")
    gross_profit     = metrics.get("gross_profit")
    # Fallback: Revenue - CostOfRevenue (z.B. Alphabet reportet kein GrossProfit)
    if gross_profit is None and revenue is not None:
        cor = metrics.get("cost_of_revenue")
        if cor is not None:
            gross_profit = revenue - cor
            metrics["gross_profit"] = gross_profit
    operating_income = metrics.get("operating_income")
    net_income       = metrics.get("net_income")
    metrics["gross_margin_pct"]     = round(gross_profit / revenue, 4)     if revenue and gross_profit     else None
    metrics["operating_margin_pct"] = round(operating_income / revenue, 4) if revenue and operating_income else None
    metrics["net_margin_pct"]       = round(net_income / revenue, 4)       if revenue and net_income       else None

    rev_periods   = _pick_all_periods(data, LABELS_10k["revenue"])
    cor_periods   = _pick_all_periods(data, LABELS_10k["cost_of_revenue"])
    gp_periods    = _pick_all_periods(data, LABELS_10k["gross_profit"])
    # Fallback Trend: Revenue - CostOfRevenue pro Jahr
    if not gp_periods and cor_periods:
        gp_periods = {
            date: rev_periods[date] - cor_periods[date]
            for date in rev_periods
            if date in cor_periods
        }
    oi_periods    = _pick_all_periods(data, LABELS_10k["operating_income"])
    ni_periods    = _pick_all_periods(data, LABELS_10k["net_income"])
    asset_periods = _pick_all_periods(data, LABELS_10k["total_assets"])
    ocf_periods   = _pick_all_periods(data, LABELS_10k["operating_cash_flow"])
    shares_periods = _pick_all_periods(data, ["WeightedAverageNumberOfDilutedSharesOutstanding"])

    def _sorted(d):
        return {k: d[k] for k in sorted(d)}

    def _margin_trend(num_d, den_d):
        return {
            date: round(num_d[date] / den_d[date], 4)
            for date in num_d
            if date in den_d and den_d[date]
        }

    asset_turnover = {
        date: round(rev_periods[date] / asset_periods[date], 4)
        for date in rev_periods
        if date in asset_periods and asset_periods[date]
    }

    trends = {
        "revenue":             _sorted(rev_periods),
        "gross_profit":        _sorted(gp_periods),
        "operating_income":    _sorted(oi_periods),
        "net_income":          _sorted(ni_periods),
        "total_assets":        _sorted(asset_periods),
        "operating_cash_flow": _sorted(ocf_periods),
        "shares_diluted":      _sorted(shares_periods),
        "asset_turnover":      _sorted(asset_turnover),
        "gross_margin_pct":    _sorted(_margin_trend(gp_periods, rev_periods)),
        "operating_margin_pct":_sorted(_margin_trend(oi_periods, rev_periods)),
        "net_margin_pct":      _sorted(_margin_trend(ni_periods, rev_periods)),
    }

    return {
        "metrics":        metrics,
        "trends":         trends,
        "risk_factors":   text.get("risk_factors", []),
        "mda_highlights": text.get("mda_highlights", []),
    }


def extract_10q(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    text = _load_text_companion(path)

    out = {
        "core_metrics":       {},
        "comparisons":        {},
        "mda_updates":        {},
        "risk_factor_changes":{},
        "legal_proceedings":  {},
        "segments":           {},
    }

    for metric, names in LABELS_10Q["core_metrics"].items():
        out["core_metrics"][metric] = _pick(data, names)

    ocf   = out["core_metrics"].get("operating_cash_flow")
    capex = out["core_metrics"].get("capex")
    out["core_metrics"]["free_cash_flow"] = (
        ocf - abs(capex) if ocf is not None and capex is not None else None
    )

    debt_c  = out["core_metrics"].get("debt_current")
    debt_nc = out["core_metrics"].get("debt_noncurrent")
    out["core_metrics"]["total_debt"] = (
        (debt_c or 0) + (debt_nc or 0)
        if debt_c is not None or debt_nc is not None
        else None
    )

    revenue          = out["core_metrics"].get("revenue")
    gross_profit     = out["core_metrics"].get("gross_profit")
    # Fallback: Revenue - CostOfRevenue (z.B. Alphabet reportet kein GrossProfit)
    if gross_profit is None and revenue is not None:
        cor = out["core_metrics"].get("cost_of_revenue")
        if cor is not None:
            gross_profit = revenue - cor
            out["core_metrics"]["gross_profit"] = gross_profit
    operating_income = out["core_metrics"].get("operating_income")
    net_income       = out["core_metrics"].get("net_income")
    out["core_metrics"]["gross_margin_pct"]     = round(gross_profit / revenue, 4)     if revenue and gross_profit     else None
    out["core_metrics"]["operating_margin_pct"] = round(operating_income / revenue, 4) if revenue and operating_income else None
    out["core_metrics"]["net_margin_pct"]       = round(net_income / revenue, 4)       if revenue and net_income       else None

    ca = out["core_metrics"].get("current_assets")
    cl = out["core_metrics"].get("current_liabilities")
    out["core_metrics"]["current_ratio"] = round(ca / cl, 4) if ca and cl else None

    ca_prior = _pick_prior_instant(data, LABELS_10Q["core_metrics"]["current_assets"])
    cl_prior = _pick_prior_instant(data, LABELS_10Q["core_metrics"]["current_liabilities"])
    out["core_metrics"]["current_ratio_prior"] = round(ca_prior / cl_prior, 4) if ca_prior and cl_prior else None

    ta = out["core_metrics"].get("total_assets")
    td = out["core_metrics"].get("total_debt")
    out["core_metrics"]["leverage_ratio"] = round(td / ta, 4) if td and ta else None

    dc_prior  = _pick_prior_instant(data, LABELS_10Q["core_metrics"]["debt_current"])
    dnc_prior = _pick_prior_instant(data, LABELS_10Q["core_metrics"]["debt_noncurrent"])
    ta_prior  = _pick_prior_instant(data, LABELS_10Q["core_metrics"]["total_assets"])
    td_prior  = (
        (dc_prior or 0) + (dnc_prior or 0)
        if dc_prior is not None or dnc_prior is not None
        else None
    )
    out["core_metrics"]["total_debt_prior"]    = td_prior
    out["core_metrics"]["total_assets_prior"]  = ta_prior
    out["core_metrics"]["leverage_ratio_prior"] = round(td_prior / ta_prior, 4) if td_prior and ta_prior else None

    out["segments"] = text.get("segments", {})

    for key, names in LABELS_10Q["comparisons"].items():
        out["comparisons"][key] = _pick_any(data, names)

    out["comparisons"]["yoy_change"] = _derive_yoy_change(data)
    out["comparisons"]["qoq_change"] = _derive_qoq_change(data)

    out["comparisons"]["current_quarter"] = (
        _get_by_path(data, "CoverPage.DocumentFiscalPeriodFocus")
        or out["comparisons"].get("current_quarter")
    )
    out["comparisons"]["current_fiscal_year"] = (
        _get_by_path(data, "CoverPage.DocumentFiscalYearFocus")
        or out["comparisons"].get("current_fiscal_year")
    )
    out["comparisons"]["document_period_end"] = (
        _get_by_path(data, "CoverPage.DocumentPeriodEndDate")
        or out["comparisons"].get("document_period_end")
    )

    out["mda_updates"]["liquidity_capital_resources"] = text.get("liquidity_capital_resources")
    out["mda_updates"]["results_of_operations"]       = text.get("results_of_operations")
    out["mda_updates"]["highlights"]                  = text.get("highlights", [])

    risk_text = text.get("risk_factor_change_summary")
    out["risk_factor_changes"]["risk_factor_change_summary"] = risk_text
    out["risk_factor_changes"]["risk_factor_changes_flag"]   = bool(risk_text)

    legal_text = text.get("legal_proceedings_summary")
    out["legal_proceedings"]["legal_proceedings_summary"]    = legal_text
    out["legal_proceedings"]["legal_proceedings_update_flag"] = bool(legal_text)

    return out
