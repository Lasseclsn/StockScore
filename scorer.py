"""
Probabilistisches Scoring-Modell zur Kursrichtungsvorhersage.

Eingabe: extrahierte Dicts aus extract_10k(), extract_10q(), extract_vantage()
Ausgabe: Score 0-100, Wahrscheinlichkeit, Breakdown pro Block
"""

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

FINANCIAL_SECTORS = {"financial services", "banking", "insurance", "reit", "mortgage"}
FINANCIAL_INDUSTRIES = {"banks", "insurance", "reit", "asset management", "capital markets"}

ACCRUAL_PENALTY_1YR = -4   # OCF/NI < 0.5 in aktuellem Jahr
EQUITY_PENALTY_FINANCIAL = -6  # Negatives Eigenkapital bei Finanzunternehmen


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _linear(value, low, high, max_pts, invert=False):
    """
    Interpoliert value linear zwischen low (0 Punkte) und high (max_pts).
    Werte außerhalb werden geclampt. invert=True kehrt die Richtung um.
    """
    if value is None or high == low:
        return 0.0
    clamped = max(float(low), min(float(high), float(value)))
    ratio = (clamped - low) / (high - low)
    if invert:
        ratio = 1.0 - ratio
    return round(ratio * max_pts, 4)


def _b(condition, pts):
    """Binäres Signal: pts wenn True, sonst 0."""
    return pts if condition else 0


def _trend_sorted(d):
    """Gibt Werte eines Trend-Dicts in chronologischer Reihenfolge zurück."""
    return [d[k] for k in sorted(d.keys())] if d else []


def _is_financial(data_vantage):
    """Erkennt Finanzunternehmen (Banken, Versicherungen, REITs)."""
    meta = data_vantage.get("metadata", {})
    sector = (meta.get("sector") or "").lower()
    industry = (meta.get("industry") or "").lower()
    return (
        any(s in sector for s in FINANCIAL_SECTORS)
        or any(s in industry for s in FINANCIAL_INDUSTRIES)
    )


def _altman_z(cm, data_vantage):
    """
    Altman Z-Score (öffentliche Unternehmen):
    Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5

    X1 = Working Capital / Total Assets
    X2 = Retained Earnings / Total Assets
    X3 = EBIT (≈ Operating Income) / Total Assets
    X4 = Market Cap / Total Liabilities
    X5 = Revenue / Total Assets
    """
    ta   = cm.get("total_assets")
    ca   = cm.get("current_assets")
    cl   = cm.get("current_liabilities")
    re_  = cm.get("retained_earnings")
    ebit = cm.get("operating_income")
    tl   = cm.get("total_liabilities")
    rev  = cm.get("revenue")
    mc   = data_vantage.get("valuation", {}).get("market_cap")

    if None in (ta, ca, cl, re_, ebit, tl, rev, mc) or ta == 0 or tl == 0:
        return None

    x1 = (ca - cl) / ta
    x2 = re_ / ta
    x3 = ebit / ta
    x4 = mc / tl
    x5 = rev / ta

    return 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5


def _ocf_ni_ratios_from_10k(data_10k):
    """
    Berechnet OCF/Net Income für alle Jahre aus den 10-K Trends.
    Gibt sortierte Liste von (date, ratio) zurück, neuestes zuletzt.
    """
    ocf_trend = data_10k.get("trends", {}).get("operating_cash_flow", {})
    ni_trend  = data_10k.get("trends", {}).get("net_income", {})
    common    = sorted(set(ocf_trend) & set(ni_trend))

    result = []
    for d in common:
        ni = ni_trend[d]
        if ni and ni > 0:
            result.append((d, ocf_trend[d] / ni))

    return result  # [(date, ratio), ...]


# ---------------------------------------------------------------------------
# Schicht 1 – Knockout-Filter
# ---------------------------------------------------------------------------

def knockout_filters(data_10q, data_10k, data_vantage):
    """
    Gibt (passed: bool, reasons: list[str], flags: dict) zurück.

    flags enthält Signale, die keinen Knockout auslösen, aber
    in den Scoring-Blöcken als Penalty wirken:
      - negative_equity_penalty: negatives EK bei Finanzunternehmen
      - accrual_warning_1yr:     OCF/NI < 0.5 im letzten Jahr
    """
    cm = data_10q.get("core_metrics", {})
    is_financial = _is_financial(data_vantage)
    reasons = []
    flags = {
        "negative_equity_penalty": False,
        "accrual_warning_1yr":     False,
    }

    # --- 1. Negatives Eigenkapital ---
    equity = cm.get("stockholders_equity")
    if equity is not None and equity < 0:
        if is_financial:
            flags["negative_equity_penalty"] = True   # Penalty statt Knockout
        else:
            reasons.append("Negatives Eigenkapital (Non-Financial)")

    # --- 2. Operating Cashflow 2 aufeinanderfolgende Jahre negativ ---
    ocf_trend = _trend_sorted(data_10k.get("trends", {}).get("operating_cash_flow", {}))
    if len(ocf_trend) >= 2 and all(v < 0 for v in ocf_trend[-2:]):
        reasons.append("Operating Cashflow 2 Jahre in Folge negativ")

    # --- 3. Altman Z' < 1.1 (nur Non-Financial) ---
    if not is_financial:
        z = _altman_z(cm, data_vantage)
        if z is not None and z < 1.1:
            reasons.append(f"Altman Z-Score {z:.2f} < 1.1 (Distress Zone)")

    # --- 4. OCF / Net Income ---
    ratios = _ocf_ni_ratios_from_10k(data_10k)

    # 4a. 2 aufeinanderfolgende Jahre < 0.5 → Knockout
    if len(ratios) >= 2 and all(r < 0.5 for _, r in ratios[-2:]):
        reasons.append(
            f"OCF/Net Income < 0.5 in 2 aufeinanderfolgenden Jahren "
            f"({ratios[-2][0][:4]}: {ratios[-2][1]:.2f}, "
            f"{ratios[-1][0][:4]}: {ratios[-1][1]:.2f})"
        )
    # 4b. Nur letztes Jahr < 0.5 → Accrual-Penalty (kein Knockout)
    elif ratios and ratios[-1][1] < 0.5:
        flags["accrual_warning_1yr"] = True

    return len(reasons) == 0, reasons, flags


# ---------------------------------------------------------------------------
# Block 1 – Quality / Profitability (30 Punkte)
# ---------------------------------------------------------------------------

def score_quality(data_10q, data_10k, data_vantage, flags=None):
    cm     = data_10q.get("core_metrics", {})
    prof   = data_vantage.get("profitability", {})
    growth = data_vantage.get("growth", {})
    trends = data_10k.get("trends", {})
    flags  = flags or {}
    details = {}

    # ROA-Niveau: linear 0% → 10% = 4 Punkte
    details["roa_level"] = _linear(prof.get("roa"), 0, 0.10, 4)

    # ROA YoY: positiver Earnings Growth als Proxy = 3 Punkte
    details["roa_yoy"] = _b(
        (growth.get("earnings_growth_yoy") or 0) > 0, 3
    )

    # ROE-Niveau: linear 0% → 20% = 3 Punkte
    details["roe_level"] = _linear(prof.get("roe"), 0, 0.20, 3)

    # Gross Margin YoY-Delta: linear 0 → +5% = 3 Punkte
    gm = _trend_sorted(trends.get("gross_margin_pct", {}))
    gm_delta = (gm[-1] - gm[-2]) if len(gm) >= 2 else None
    details["gross_margin_yoy"] = _linear(
        max(0, gm_delta) if gm_delta is not None else None, 0, 0.05, 3
    )

    # Operating Margin YoY-Delta: linear 0 → +5% = 3 Punkte
    om = _trend_sorted(trends.get("operating_margin_pct", {}))
    om_delta = (om[-1] - om[-2]) if len(om) >= 2 else None
    details["operating_margin_yoy"] = _linear(
        max(0, om_delta) if om_delta is not None else None, 0, 0.05, 3
    )

    # Asset Turnover YoY positiv = 3 Punkte
    at = _trend_sorted(trends.get("asset_turnover", {}))
    details["asset_turnover_yoy"] = _b(len(at) >= 2 and at[-1] > at[-2], 3)

    # Net Income > 0: binär 3 Punkte
    details["net_income_positive"] = _b((cm.get("net_income") or 0) > 0, 3)

    # Operating Income > 0: binär 2 Punkte
    details["operating_income_positive"] = _b((cm.get("operating_income") or 0) > 0, 2)

    # FCF > 0: binär 3 Punkte
    details["fcf_positive"] = _b((cm.get("free_cash_flow") or 0) > 0, 3)

    # OCF > Net Income (Piotroski Quality of Earnings): binär 3 Punkte
    ocf = cm.get("operating_cash_flow") or 0
    ni  = cm.get("net_income") or 0
    details["ocf_gt_net_income"] = _b(ocf > ni, 3)

    # Accrual Penalty: OCF/NI < 0.5 im letzten Jahr = -4 Punkte
    if flags.get("accrual_warning_1yr"):
        details["accrual_penalty_1yr"] = ACCRUAL_PENALTY_1YR

    score = max(0.0, sum(details.values()))
    return {"score": round(score, 2), "max": 30, "details": details}


# ---------------------------------------------------------------------------
# Block 2 – Valuation (25 Punkte)
# ---------------------------------------------------------------------------

def score_valuation(data_10q, data_vantage):
    val = data_vantage.get("valuation", {})
    details = {}

    # Forward P/E: invers linear 10 → 40 = 6 Punkte
    details["forward_pe"] = _linear(val.get("forward_pe"), 10, 40, 6, invert=True)

    # PEG Ratio: invers linear 0.5 → 2.5 = 5 Punkte
    details["peg_ratio"] = _linear(val.get("peg_ratio"), 0.5, 2.5, 5, invert=True)

    # EV/EBITDA: invers linear 5 → 20 = 5 Punkte
    details["ev_ebitda"] = _linear(val.get("ev_to_ebitda"), 5, 20, 5, invert=True)

    # Price/Sales: invers linear 1 → 10 = 4 Punkte
    details["price_sales"] = _linear(val.get("price_to_sales_ttm"), 1, 10, 4, invert=True)

    # Price/Book: invers linear 1 → 5 = 3 Punkte
    details["price_book"] = _linear(val.get("price_to_book"), 1, 5, 3, invert=True)

    # Forward P/E < Trailing P/E (steigende Gewinne erwartet): binär 2 Punkte
    fpe = val.get("forward_pe")
    tpe = val.get("pe_ratio")
    details["forward_lt_trailing"] = _b(
        fpe is not None and tpe is not None and fpe < tpe, 2
    )

    score = sum(details.values())
    return {"score": round(score, 2), "max": 25, "details": details}


# ---------------------------------------------------------------------------
# Block 3 – Financial Strength / Risk (20 Punkte)
# ---------------------------------------------------------------------------

def score_financial_strength(data_10q, data_10k, data_vantage, flags=None):
    """
    Bei Finanzunternehmen: Altman wird übersprungen.
    Die verbleibenden 15 Punkte werden auf 20 normalisiert.
    Negatives Eigenkapital bei Finanzunternehmen erzeugt eine Penalty.
    """
    cm           = data_10q.get("core_metrics", {})
    is_financial = _is_financial(data_vantage)
    flags        = flags or {}
    details      = {}

    # Altman Z' graduell: linear 1.1 → 2.6 = 5 Punkte (nur Non-Financial)
    if not is_financial:
        z = _altman_z(cm, data_vantage)
        details["altman_z"] = _linear(z, 1.1, 2.6, 5)
        raw_max = 20
    else:
        raw_max = 15  # Altman-Block entfällt → später auf 20 normalisiert

    # Total Debt / Total Assets: invers linear 0.2 → 0.6 = 4 Punkte
    details["debt_to_assets"] = _linear(cm.get("leverage_ratio"), 0.2, 0.6, 4, invert=True)

    # Cash / Total Debt: linear 0.1 → 0.5 = 3 Punkte (≥ 0.5 = voll)
    cash  = cm.get("cash") or 0
    td    = cm.get("total_debt")
    c2d   = (cash / td) if td and td > 0 else None
    details["cash_to_debt"] = _linear(c2d, 0.1, 0.5, 3)

    # Leverage YoY sinkend: binär 3 Punkte
    lev       = cm.get("leverage_ratio")
    lev_prior = cm.get("leverage_ratio_prior")
    details["leverage_yoy"] = _b(
        lev is not None and lev_prior is not None and lev < lev_prior, 3
    )

    # Current Ratio YoY steigend: binär 2 Punkte
    cr       = cm.get("current_ratio")
    cr_prior = cm.get("current_ratio_prior")
    details["current_ratio_yoy"] = _b(
        cr is not None and cr_prior is not None and cr > cr_prior, 2
    )

    # OCF > Capex: binär 3 Punkte
    ocf   = cm.get("operating_cash_flow") or 0
    capex = abs(cm.get("capex") or 0)
    details["ocf_gt_capex"] = _b(ocf > capex, 3)

    # Negatives Eigenkapital bei Finanzunternehmen: Penalty
    if flags.get("negative_equity_penalty"):
        details["equity_penalty"] = EQUITY_PENALTY_FINANCIAL

    # Rohscore der positiven Metriken
    positive_score = sum(v for v in details.values() if v > 0)
    penalty_score  = sum(v for v in details.values() if v < 0)

    if is_financial:
        # Normalisierung: 15 verfügbare Punkte → auf 20 skalieren
        normalized = (positive_score / raw_max) * 20
        score = max(0.0, normalized + penalty_score)
    else:
        score = max(0.0, positive_score + penalty_score)

    return {"score": round(score, 2), "max": 20, "details": details}


# ---------------------------------------------------------------------------
# Block 4 – Growth (15 Punkte)
# ---------------------------------------------------------------------------

def score_growth(data_10q, data_10k, data_vantage):
    cm     = data_10q.get("core_metrics", {})
    growth = data_vantage.get("growth", {})
    trends = data_10k.get("trends", {})
    details = {}

    # Revenue Growth YoY: linear 0% → 20% = 4 Punkte
    rev_growth = (
        growth.get("revenue_growth_yoy")
        or data_10q.get("comparisons", {}).get("yoy_change")
    )
    details["revenue_growth"] = _linear(rev_growth, 0, 0.20, 4)

    # Earnings Growth YoY: linear 0% → 25% = 4 Punkte
    eg = growth.get("earnings_growth_yoy")
    details["earnings_growth"] = _linear(
        max(0, eg) if eg is not None else None, 0, 0.25, 4
    )

    # Net Income 3-Jahres-Trend positiv und steigend: binär 3 Punkte
    ni_vals = _trend_sorted(trends.get("net_income", {}))
    details["net_income_trend"] = _b(
        len(ni_vals) >= 2
        and all(v > 0 for v in ni_vals)
        and ni_vals[-1] >= ni_vals[-2],
        3
    )

    # Operating Income 3-Jahres-Trend positiv und steigend: binär 2 Punkte
    oi_vals = _trend_sorted(trends.get("operating_income", {}))
    details["operating_income_trend"] = _b(
        len(oi_vals) >= 2
        and all(v > 0 for v in oi_vals)
        and oi_vals[-1] >= oi_vals[-2],
        2
    )

    # Keine Verwässerung (Shares stabil oder fallend): binär 2 Punkte
    shares = _trend_sorted(trends.get("shares_diluted", {}))
    details["no_dilution"] = _b(len(shares) >= 2 and shares[-1] <= shares[-2], 2)

    score = sum(details.values())
    return {"score": round(score, 2), "max": 15, "details": details}


# ---------------------------------------------------------------------------
# Block 5 – Momentum (10 Punkte)
# ---------------------------------------------------------------------------

def score_momentum(data_vantage):
    md = data_vantage.get("market_data", {})
    details = {}

    price  = md.get("current_price_derived")
    ma_50  = md.get("ma_50_day")
    ma_200 = md.get("ma_200_day")
    h52w   = md.get("week_52_high")
    beta   = md.get("beta")

    # Current Price > 200-Tage-MA: binär 4 Punkte
    details["price_gt_ma200"] = _b(
        price is not None and ma_200 is not None and price > ma_200, 4
    )

    # Golden Cross (50-MA > 200-MA): binär 3 Punkte
    details["golden_cross"] = _b(
        ma_50 is not None and ma_200 is not None and ma_50 > ma_200, 3
    )

    # Abstand zum 52-Wochen-Hoch: ≤ 15% = voll, bis 40% linear fallend
    if price is not None and h52w and h52w > 0:
        dist = (h52w - price) / h52w
        if dist <= 0.15:
            details["distance_52w_high"] = 2.0
        else:
            details["distance_52w_high"] = _linear(dist, 0.15, 0.40, 2, invert=True)
    else:
        details["distance_52w_high"] = 0.0

    # Beta moderat (0.7 – 1.3): binär 1 Punkt
    details["beta_moderate"] = _b(beta is not None and 0.7 <= beta <= 1.3, 1)

    score = sum(details.values())
    return {"score": round(score, 2), "max": 10, "details": details}


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def score(data_10k, data_10q, data_vantage):
    """
    Berechnet Gesamt-Score und Kursrichtungs-Wahrscheinlichkeit.

    Returns:
        passed_knockout:  bool
        knockout_reasons: list[str]
        score:            float | None   (0–100)
        max_score:        100
        probability_up:   float | None   (0.25–0.75)
        signal:           str
        blocks:           dict mit Teilscores und Details
        flags:            dict mit aktiven Penalty-Flags
    """
    passed, reasons, flags = knockout_filters(data_10q, data_10k, data_vantage)

    if not passed:
        return {
            "passed_knockout":  False,
            "knockout_reasons": reasons,
            "score":            None,
            "max_score":        100,
            "probability_up":   None,
            "signal":           "Knockout – kein Score",
            "blocks":           {},
            "flags":            flags,
        }

    blocks = {
        "quality":            score_quality(data_10q, data_10k, data_vantage, flags),
        "valuation":          score_valuation(data_10q, data_vantage),
        "financial_strength": score_financial_strength(data_10q, data_10k, data_vantage, flags),
        "growth":             score_growth(data_10q, data_10k, data_vantage),
        "momentum":           score_momentum(data_vantage),
    }

    total = round(sum(b["score"] for b in blocks.values()), 2)

    # Score 0 → 25%, Score 50 → 50%, Score 100 → 75%
    prob = round(0.25 + (total / 100) * 0.50, 4)

    if total >= 75:
        signal = "Stark bullish"
    elif total >= 62:
        signal = "Bullish"
    elif total >= 50:
        signal = "Leicht bullish"
    elif total >= 38:
        signal = "Leicht bearish"
    elif total >= 25:
        signal = "Bearish"
    else:
        signal = "Stark bearish"

    active_flags = [k for k, v in flags.items() if v]

    return {
        "passed_knockout":  True,
        "knockout_reasons": [],
        "score":            total,
        "max_score":        100,
        "probability_up":   prob,
        "signal":           signal,
        "blocks":           blocks,
        "flags":            active_flags,
    }
