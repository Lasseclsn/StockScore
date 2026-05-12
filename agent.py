"""
DeepSeek-Agent für Finanzanalyse.

Nimmt den Scoring-Output und die extrahierten Finanzdaten entgegen
und liefert eine strukturierte Einschätzung zur Kursrichtung.
"""

import json
import requests
from pathlib import Path


BASE_DIR = Path(__file__).parent
_DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
_MODEL = "deepseek-chat"

SYSTEM_PROMPT = """Du bist ein erfahrener Finanzanalyst. Du bekommst strukturierte
Finanzdaten und einen regelbasierten Score (0–100) für eine Aktie.

Deine Aufgabe:
1. Erkläre die wichtigsten Treiber des Scores (bullish UND bearish).
2. Bewerte ob der Score die tatsächliche Situation korrekt widerspiegelt
   oder ob es Faktoren gibt, die das Modell nicht erfasst.
3. Gib eine klare Einschätzung: Steigt die Aktie im nächsten Quartal
   wahrscheinlich oder nicht?

Antworte präzise, auf Deutsch, maximal 300 Wörter.
Keine Haftungsausschlüsse oder allgemeine Warnungen."""


def _load_api_key(key_name: str) -> str:
    env_path = BASE_DIR / ".env"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() == key_name:
            return value.strip().strip('"').strip("'")
    raise RuntimeError(f"API-Key '{key_name}' nicht in .env gefunden.")


def _build_prompt(ticker: str, score_result: dict, data_10q: dict, data_10k: dict, data_vantage: dict) -> str:
    cm      = data_10q.get("core_metrics", {})
    trends  = data_10k.get("trends", {})
    growth  = data_vantage.get("growth", {})
    val     = data_vantage.get("valuation", {})
    analyst = data_vantage.get("analyst_consensus", {})
    segs    = data_10q.get("segments", {}).get("segments", {})

    block_summary = "\n".join(
        f"  {name}: {info['score']:.1f}/{info['max']}"
        for name, info in score_result.get("blocks", {}).items()
    )

    seg_lines = "\n".join(
        f"  {seg}: Revenue {info.get('revenue', 0)/1e9:.1f}B, "
        f"Gross Margin {info.get('gross_margin_pct', 0)*100:.1f}%, "
        f"Revenue YoY {(info.get('revenue_yoy_change') or 0)*100:.1f}%"
        for seg, info in segs.items()
    ) or "  Keine Segmentdaten"

    ni_trend = trends.get("net_income", {})
    ni_str = ", ".join(f"{d[:4]}: {v/1e9:.2f}B" for d, v in sorted(ni_trend.items()))

    prompt = f"""Ticker: {ticker}

SCORING-ERGEBNIS:
  Gesamtscore: {score_result.get('score')}/100
  Signal: {score_result.get('signal')}
  Wahrscheinlichkeit Kursanstieg: {(score_result.get('probability_up') or 0)*100:.1f}%
  Aktive Penalty-Flags: {score_result.get('flags') or 'keine'}

BLOCK-BREAKDOWN:
{block_summary}

KERNKENNZAHLEN (aktuelles Quartal):
  Revenue:           {(cm.get('revenue') or 0)/1e9:.2f}B
  Gross Margin:      {(cm.get('gross_margin_pct') or 0)*100:.1f}%
  Operating Margin:  {(cm.get('operating_margin_pct') or 0)*100:.1f}%
  Net Margin:        {(cm.get('net_margin_pct') or 0)*100:.1f}%
  Free Cash Flow:    {(cm.get('free_cash_flow') or 0)/1e9:.2f}B
  Total Debt:        {(cm.get('total_debt') or 0)/1e9:.2f}B
  Cash:              {(cm.get('cash') or 0)/1e9:.2f}B

NET INCOME TREND (3 Jahre): {ni_str}

SEGMENTE:
{seg_lines}

WACHSTUM (YoY):
  Revenue:  {(growth.get('revenue_growth_yoy') or 0)*100:.1f}%
  Earnings: {(growth.get('earnings_growth_yoy') or 0)*100:.1f}%

BEWERTUNG:
  Forward P/E:  {val.get('forward_pe')}
  PEG:          {val.get('peg_ratio')}
  EV/EBITDA:    {val.get('ev_to_ebitda')}

ANALYSTEN:
  Bullish: {analyst.get('bullish_pct', 0)*100:.0f}%  |  Bearish: {analyst.get('bearish_pct', 0)*100:.0f}%
  Kursziel: {analyst.get('target_price')} USD"""

    return prompt


def _call_deepseek(system: str, user: str, max_tokens: int = 600) -> str:
    """Gemeinsamer API-Call für alle Agent-Funktionen."""
    api_key = _load_api_key("DeepSeek_API_KEY")
    response = requests.post(
        _DEEPSEEK_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        },
        json={
            "model":       _MODEL,
            "messages":    [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "temperature": 0.3,
            "max_tokens":  max_tokens,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def analyze(ticker: str, score_result: dict, data_10k: dict, data_10q: dict, data_vantage: dict) -> str:
    """Gesamteinschätzung: Score-Treiber + Kursrichtung."""
    prompt = _build_prompt(ticker, score_result, data_10q, data_10k, data_vantage)
    return _call_deepseek(SYSTEM_PROMPT, prompt, max_tokens=600)


def analyze_mda(ticker: str, data_10k: dict, data_10q: dict, data_vantage: dict) -> str:
    """
    MD&A-Analyse aus numerischen Trends.
    Da XBRL keinen Narrativtext liefert, rekonstruiert DeepSeek
    die wahrscheinliche Management-Diskussion aus den Zahlen.
    """
    cm     = data_10q.get("core_metrics", {})
    trends = data_10k.get("trends", {})
    segs   = data_10q.get("segments", {}).get("segments", {})

    def _fmt_trend(key, divisor=1e9, suffix="B"):
        d = trends.get(key, {})
        return ", ".join(f"{k[:4]}: {v/divisor:.2f}{suffix}" for k, v in sorted(d.items()))

    def _fmt_margin_trend(key):
        d = trends.get(key, {})
        return ", ".join(f"{k[:4]}: {v*100:.1f}%" for k, v in sorted(d.items()))

    risk_text = "\n".join(f"- {s}" for s in (data_10k.get("risk_factors") or [])[:3])

    seg_lines = "\n".join(
        f"  {seg}: Revenue {info.get('revenue', 0)/1e9:.1f}B "
        f"(YoY {(info.get('revenue_yoy_change') or 0)*100:+.1f}%), "
        f"Gross Margin {info.get('gross_margin_pct', 0)*100:.1f}% "
        f"(Vj. {info.get('gross_margin_pct_prior_year', 0)*100:.1f}%)"
        for seg, info in segs.items()
    ) or "  Keine Segmentdaten verfügbar"

    prompt = f"""Ticker: {ticker} — MD&A-Rekonstruktion aus Finanzdaten

HINWEIS: Der Narrativtext aus dem SEC-Filing ist nicht verfügbar (XBRL-Limitation).
Analysiere stattdessen die folgenden Kennzahlen und erkläre, was das Management
wahrscheinlich in der MD&A diskutiert hat.

UMSATZ-TREND:         {_fmt_trend('revenue')}
ROHERTRAG-TREND:      {_fmt_trend('gross_profit')}
OPERATING INCOME:     {_fmt_trend('operating_income')}
NET INCOME:           {_fmt_trend('net_income')}
OPERATING CASHFLOW:   {_fmt_trend('operating_cash_flow')}

MARGEN-ENTWICKLUNG:
  Gross Margin:       {_fmt_margin_trend('gross_margin_pct')}
  Operating Margin:   {_fmt_margin_trend('operating_margin_pct')}
  Net Margin:         {_fmt_margin_trend('net_margin_pct')}

SEGMENTE (aktuelles Quartal):
{seg_lines}

LIQUIDITÄT:
  Cash:               {(cm.get('cash') or 0)/1e9:.2f}B
  Free Cash Flow:     {(cm.get('free_cash_flow') or 0)/1e9:.2f}B
  Total Debt:         {(cm.get('total_debt') or 0)/1e9:.2f}B
  Current Ratio:      {cm.get('current_ratio')}

RISIKOFAKTOREN (aus 10-K):
{risk_text or '  Keine extrahiert'}

Aufgabe: Schreibe eine prägnante MD&A-Analyse (max. 250 Wörter) mit den Abschnitten:
1. Ergebnisse des Quartals
2. Liquidität & Kapitalressourcen
3. Wesentliche Risiken"""

    system = """Du bist ein erfahrener Finanzanalyst der SEC-Filings auswertet.
Analysiere die gegebenen Finanzdaten und formuliere eine strukturierte MD&A-Einschätzung.
Bleib faktenbasiert, präzise und auf Deutsch."""

    return _call_deepseek(system, prompt, max_tokens=700)


def extract_guidance(ticker: str, data_10k: dict, data_10q: dict, data_vantage: dict) -> str:
    """
    Guidance-Extraktion aus impliziten Signalen.
    Da kein Earnings-Call-Transkript verfügbar ist, liest DeepSeek
    Forward-Looking-Signale aus Kapitalallokation und Bewertungsmetriken.
    """
    cm     = data_10q.get("core_metrics", {})
    trends = data_10k.get("trends", {})
    val    = data_vantage.get("valuation", {})
    growth = data_vantage.get("growth", {})
    analyst = data_vantage.get("analyst_consensus", {})
    md     = data_vantage.get("market_data", {})

    def _fmt_trend(key, divisor=1e9, suffix="B"):
        d = trends.get(key, {})
        return ", ".join(f"{k[:4]}: {v/divisor:.2f}{suffix}" for k, v in sorted(d.items()))

    capex_trend = _fmt_trend("operating_cash_flow")
    at_trend = trends.get("asset_turnover", {})
    at_str = ", ".join(f"{k[:4]}: {v:.3f}" for k, v in sorted(at_trend.items()))

    prompt = f"""Ticker: {ticker} — Implizite Guidance-Extraktion

KAPITALALLOKATION (Forward-Signale):
  CapEx (absolut):         {(cm.get('capex') or 0)/1e9:.2f}B
  Free Cash Flow:          {(cm.get('free_cash_flow') or 0)/1e9:.2f}B
  FCF / CapEx-Verhältnis:  {abs((cm.get('free_cash_flow') or 0) / (cm.get('capex') or 1)):.2f}x
  R&D Expense (letztes FJ):{(data_10k.get('metrics', {}).get('rd_expense') or 0)/1e9:.2f}B
  Inventory:               {(cm.get('inventory') or 0)/1e9:.2f}B
  Asset Turnover-Trend:    {at_str}

BEWERTUNGS-SIGNALE:
  Trailing P/E:            {val.get('pe_ratio')}
  Forward P/E:             {val.get('forward_pe')}
  PEG Ratio:               {val.get('peg_ratio')}
  Forward < Trailing P/E:  {'Ja (Gewinnwachstum erwartet)' if (val.get('forward_pe') or 999) < (val.get('pe_ratio') or 0) else 'Nein'}

WACHSTUMS-MOMENTUM:
  Revenue YoY:             {(growth.get('revenue_growth_yoy') or 0)*100:+.1f}%
  Earnings YoY:            {(growth.get('earnings_growth_yoy') or 0)*100:+.1f}%

ANALYSTEN-KONSENSUS:
  Kursziel:                {analyst.get('target_price')} USD
  Aktueller Kurs (est.):   {md.get('current_price_derived')} USD
  Upside zum Kursziel:     {((analyst.get('target_price') or 0) / (md.get('current_price_derived') or 1) - 1)*100:.1f}%
  Bullish/Bearish:         {analyst.get('bullish_pct', 0)*100:.0f}% / {analyst.get('bearish_pct', 0)*100:.0f}%

Aufgabe: Extrahiere die impliziten Forward-Looking-Signale und formuliere max. 200 Wörter:
1. Was signalisiert die Kapitalallokation über zukünftiges Wachstum?
2. Was impliziert die Differenz Forward vs. Trailing P/E?
3. Wo liegt der Konsens für das nächste Quartal?"""

    system = """Du bist ein Buy-Side-Analyst der implizite Guidance-Signale aus Finanzdaten liest.
Kein Earnings-Call ist verfügbar — extrahiere Zukunftssignale ausschließlich aus den Zahlen.
Antworte auf Deutsch, präzise und strukturiert."""

    return _call_deepseek(system, prompt, max_tokens=500)


def explain_anomalies(ticker: str, score_result: dict, data_10k: dict, data_10q: dict, data_vantage: dict) -> str:
    """
    Anomalie-Erklärung: Identifiziert Blöcke und Metriken die auffällig
    vom erwarteten Muster abweichen und erklärt die Ursachen.
    """
    cm     = data_10q.get("core_metrics", {})
    blocks = score_result.get("blocks", {})
    flags  = score_result.get("flags", [])

    # Blöcke nach Ausschöpfungsgrad sortieren
    block_performance = sorted(
        [(name, info["score"], info["max"], info["score"] / info["max"])
         for name, info in blocks.items()],
        key=lambda x: x[3]
    )

    block_lines = "\n".join(
        f"  {name:<22} {score:>5.1f}/{max_:>2} ({pct*100:.0f}%)  "
        f"{'⚠ SCHWACH' if pct < 0.35 else '✓ OK' if pct > 0.65 else '~'}"
        for name, score, max_, pct in block_performance
    )

    # Einzelne Nullwerte in den Details identifizieren
    zero_signals = []
    for block_name, info in blocks.items():
        for metric, val in info.get("details", {}).items():
            if val == 0 and not metric.endswith("penalty"):
                zero_signals.append(f"{block_name}.{metric}")

    # Auffällige Diskrepanzen
    val    = data_vantage.get("valuation", {})
    growth = data_vantage.get("growth", {})

    discrepancies = []
    if (growth.get("revenue_growth_yoy") or 0) > 0.10 and (val.get("pe_ratio") or 0) > 100:
        discrepancies.append("Hohes Umsatzwachstum bei extremem P/E → Bewertungsprämie oder Blase?")
    if (cm.get("free_cash_flow") or 0) > 0 and (growth.get("earnings_growth_yoy") or 0) < 0:
        discrepancies.append("Positiver FCF trotz negativem EPS-Wachstum → Accrual-Divergenz")
    if (cm.get("cash") or 0) > (cm.get("total_debt") or 0) * 2:
        discrepancies.append("Cash > 2x Total Debt → Kapital wird nicht effizient eingesetzt?")

    prompt = f"""Ticker: {ticker} — Score-Anomalie-Analyse

GESAMTSCORE: {score_result.get('score')}/100 ({score_result.get('signal')})

BLOCK-PERFORMANCE (aufsteigend nach Ausschöpfungsgrad):
{block_lines}

METRIKEN MIT 0 PUNKTEN:
{chr(10).join('  - ' + s for s in zero_signals[:10]) or '  Keine'}

AKTIVE PENALTY-FLAGS:
{chr(10).join('  - ' + f for f in flags) or '  Keine'}

IDENTIFIZIERTE DISKREPANZEN:
{chr(10).join('  - ' + d for d in discrepancies) or '  Keine offensichtlichen Diskrepanzen'}

KONTEXT:
  Earnings Growth YoY:   {(growth.get('earnings_growth_yoy') or 0)*100:+.1f}%
  Forward P/E:           {val.get('forward_pe')}
  OCF / Net Income:      {((cm.get('operating_cash_flow') or 0) / (cm.get('net_income') or 1)):.2f}x

Aufgabe: Erkläre in max. 200 Wörter:
1. Welcher Block zieht den Score am stärksten nach unten und warum?
2. Sind die schwachen Signale strukturell (dauerhaft) oder zyklisch (temporär)?
3. Gibt es eine auffällige Inkonsistenz zwischen zwei Blöcken?"""

    system = """Du bist ein quantitativer Analyst der Scoring-Anomalien in Finanzdaten erklärt.
Identifiziere Ursachen für unerwartete Score-Muster und ordne sie ein.
Antworte auf Deutsch, analytisch und präzise."""

    return _call_deepseek(system, prompt, max_tokens=500)
