"""
Freitext- und Segment-Extraktion aus den primären SEC-Filing-Dokumenten (HTML).

companyfacts (get_data.py) liefert nur Zahlen. Alles, was Freitext ist
(Risk Factors, MD&A, Legal Proceedings) oder dimensionale XBRL-Daten
(Segmente) sind dort nicht enthalten. Diese Datei holt es direkt aus dem
primären Filing-Dokument bzw. den von SEC vorgerenderten R-Files —
beides kostenlos, kein API-Key nötig.
"""

import re
import warnings
from pathlib import Path

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def _sec_headers() -> dict:
    """
    SEC verlangt einen aussagekräftigen User-Agent (Name/App + Kontakt) für
    jeden Request an sec.gov/data.sec.gov — sonst 403. Kommt aus .env statt
    hartcodiert im Quellcode, damit kein persönlicher Kontakt öffentlich im
    Repo landet.
    """
    env_path = Path(__file__).parent / ".env"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() == "SEC_USER_AGENT":
            return {
                "User-Agent": value.strip().strip('"').strip("'"),
                "Accept-Encoding": "gzip, deflate",
            }
    raise RuntimeError("SEC_USER_AGENT fehlt in .env.")


# Abschnittsüberschriften ("Item 1A. Risk Factors") werden je nach Filer in
# GROSSBUCHSTABEN oder gemischter Schreibweise gerendert — die Konvention ist
# nicht einheitlich. Erkennung daher strukturell: eine Überschrift ist der
# EIGENE (nicht vererbte) Text eines kurzen Tags, der exakt mit "Item N." beginnt
# — das unterscheidet sie zuverlässig von Inhaltsverzeichnis-Verweisen und
# Fußnoten-Querverweisen ("...siehe Item 1A...", die mitten in Fließtext stehen).
_ITEM_HEADING_RE = re.compile(r"^item\s+(\d+[a-z]?)\.?\s+(.{5,140})$", re.I)

# 8-K-Items werden mit Dezimalnummer gerendert ("Item 2.02. Results of Operations ...").
_ITEM_8K_TEXT_RE = re.compile(r"Item\s+(\d+\.\d+)\.\s+")


def _archives_url(cik: str, accession: str, filename: str) -> str:
    cik_number = str(int(cik.replace("CIK", "")))
    accession_no_dashes = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_number}/{accession_no_dashes}/{filename}"


def fetch_filing_html(cik: str, filing: dict) -> str | None:
    """Lädt das primäre Filing-Dokument direkt von SEC EDGAR."""
    if filing is None:
        return None
    url = _archives_url(cik, filing["accession"], filing["primary_document"])
    response = requests.get(url, headers=_sec_headers(), timeout=30)
    if response.status_code != 200:
        return None
    return response.text


def _normalize(s: str) -> str:
    """Entfernt jegliche Whitespaces/Interpunktion — toleriert iXBRL-Wortsplits ('RIS K' statt 'RISK')."""
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def _structural_candidates(soup, heading_re=_ITEM_HEADING_RE, max_own_len=140):
    """
    Findet alle Tags, deren EIGENER Text (ohne Kind-Tags erneut mitzuzählen wäre
    nicht nötig, get_text() inkl. Kindern ist hier gewollt) exakt als
    Item-Überschrift beginnt und kurz genug ist, um eine echte Überschrift
    (statt Fließtext mit Querverweis) zu sein.
    """
    candidates = []
    for i, tag in enumerate(soup.find_all(["p", "div", "span", "td", "th"])):
        own = tag.get_text(" ", strip=True)
        if not own or len(own) > max_own_len:
            continue
        m = heading_re.match(own)
        if not m:
            continue
        candidates.append({
            "tag": tag, "item_no": m.group(1).upper(), "title": m.group(2),
            "text": own, "pos": i,
        })
    return candidates


def _best_candidate(candidates, keyword):
    """
    Bei mehreren Treffern (Inhaltsverzeichnis + echte Überschrift, oder
    doppelt gerenderte iXBRL-Fragmente) gewinnt der LÄNGSTE Tag-Text —
    bei Gleichstand der SPÄTERE (echte Überschriften stehen im Dokument
    nach dem Inhaltsverzeichnis).
    """
    keyword_norm = _normalize(keyword)
    matches = [c for c in candidates if keyword_norm in _normalize(c["title"])]
    if not matches:
        return None
    matches.sort(key=lambda c: (len(c["text"]), c["pos"]))
    return matches[-1]


def _strip_heading_prefix(text: str | None) -> str | None:
    if not text:
        return text
    return re.sub(r"^item\s+[\d.]+[a-z]?\.?\s*", "", text, flags=re.I).strip() or None


def _section_body(tag, max_chars=6000) -> str | None:
    """
    Läuft vom Überschrift-Tag aus im Dokument weiter und sammelt Text, bis eine
    neue, hinreichend lange Item-Überschrift auftaucht. Die ersten ~300 Zeichen
    sind von der Abbruchprüfung ausgenommen, weil manche Filer dieselbe
    Überschrift direkt danach nochmal in einem separaten (iXBRL-)Tag rendern.
    """
    parts = []
    total = 0
    for node in tag.find_all_next(string=True):
        s = str(node).strip()
        if not s:
            continue
        m = re.match(r"^item\s+[\d.]+[a-z]?\.?\s+([a-z].{9,140})", s, flags=re.I)
        if m and total > 300:
            break
        parts.append(s)
        total += len(s)
        if total >= max_chars:
            break
    text = re.sub(r"\s+", " ", " ".join(parts)).strip()
    return _strip_heading_prefix(text)


def _first_sentences(text, limit=3, min_len=40) -> list[str]:
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = []
    for s in sentences:
        s = s.strip()
        if len(s) >= min_len:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def get_10k_sections(html: str) -> dict:
    """Item 1A (Risk Factors), Item 7 (MD&A), Item 3 (Legal Proceedings)."""
    soup = BeautifulSoup(html, "lxml")
    candidates = _structural_candidates(soup)

    risk  = _best_candidate(candidates, "RISK FACTORS")
    mda   = _best_candidate(candidates, "DISCUSSION AND ANALYSIS")
    legal = _best_candidate(candidates, "LEGAL PROCEEDINGS")

    risk_text  = _section_body(risk["tag"], max_chars=6000) if risk else None
    mda_text   = _section_body(mda["tag"], max_chars=6000) if mda else None
    legal_text = _section_body(legal["tag"], max_chars=3000) if legal else None

    return {
        "risk_factors":              _first_sentences(risk_text, limit=5),
        "mda_highlights":            _first_sentences(mda_text, limit=3),
        "mda_text":                  mda_text,
        "legal_proceedings_summary": legal_text,
    }


def get_10q_sections(html: str) -> dict:
    """Item 2 (MD&A), Item 1A (Risk Factor Changes), Item 1 (Legal Proceedings)."""
    soup = BeautifulSoup(html, "lxml")
    candidates = _structural_candidates(soup)

    mda   = _best_candidate(candidates, "DISCUSSION AND ANALYSIS")
    risk  = _best_candidate(candidates, "RISK FACTORS")
    legal = _best_candidate(candidates, "LEGAL PROCEEDINGS")

    mda_text   = _section_body(mda["tag"], max_chars=4000) if mda else None
    risk_text  = _section_body(risk["tag"], max_chars=3000) if risk else None
    legal_text = _section_body(legal["tag"], max_chars=3000) if legal else None

    liquidity_text = None
    if mda_text:
        m = re.search(r"LIQUIDITY AND CAPITAL RESOURCES", mda_text, flags=re.I)
        if m:
            liquidity_text = mda_text[m.end():m.end() + 3000].strip()

    return {
        "highlights":                  _first_sentences(mda_text, limit=3),
        "results_of_operations":       mda_text,
        "liquidity_capital_resources": liquidity_text,
        "risk_factor_change_summary":  risk_text,
        "legal_proceedings_summary":   legal_text,
    }


def get_8k_items(html: str) -> dict:
    """
    {'2.02': 'Text...', '5.02': 'Text...', ...} — je gemeldetem Item.

    8-Ks sind strukturell viel einfacher als 10-K/10-Q — Überschrift und Text
    stehen oft im selben Tag, weshalb der tag-basierte Ansatz von
    get_10k_sections()/get_10q_sections() hier nicht greift. Stattdessen wird
    der Fließtext linear nach 'Item X.XX.' durchsucht — das Dezimalformat ist
    für 8-K-Items SEC-weit einheitlich vorgeschrieben und damit robuster als
    die freier gestalteten 10-K/10-Q-Abschnittstitel.
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n")
    text = re.sub(r"[\xa0\n]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    matches = list(_ITEM_8K_TEXT_RE.finditer(text))
    items = {}
    for i, m in enumerate(matches):
        item_no = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()[:3000]
        if body:
            items[item_no] = body
    return items


# ---------------------------------------------------------------------------
# Segmentdaten — aus SECs vorgerenderten R-Files (Filing Summary Index)
# ---------------------------------------------------------------------------

def _find_segment_report_file(cik: str, accession: str) -> str | None:
    """
    Sucht im FilingSummary.xml nach dem R-File mit der Segment-Umsatztabelle.
    Manche Filer (z.B. Microsoft) berichten Revenue+Cost+Operating Income
    kombiniert in einer Tabelle; andere (z.B. J&J) splitten Sales/Umsatz und
    Operating Profit in separate R-Files. Bevorzugt wird die kombinierte
    Tabelle; sonst die reine Umsatz/Sales-Tabelle (liefert dann Revenue, aber
    keine Gross-Margin — get_segment_data() behandelt das als None, kein Crash).
    """
    url = _archives_url(cik, accession, "FilingSummary.xml")
    response = requests.get(url, headers=_sec_headers(), timeout=20)
    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, "lxml-xml")
    revenue_only = None
    for report in soup.find_all("Report"):
        short = report.find("ShortName")
        html_file = report.find("HtmlFileName")
        if not short or not html_file:
            continue
        name = short.get_text(strip=True).lower()
        if "segment" not in name:
            continue

        has_revenue = "revenue" in name or "sales" in name
        if not has_revenue:
            continue

        # Manche Filer bündeln Segment- und Geographie-Aufschlüsselung unter
        # derselben Notiz (Präfix enthält "geographic areas" für beide
        # Sub-Reports) — "by segment"/"segment of business" grenzt die
        # tatsächliche Segmenttabelle davon ab.
        is_by_segment = any(k in name for k in ("by segment", "segment of business", "business segment"))
        if "geographic" in name and not is_by_segment:
            continue

        if any(k in name for k in ("cost", "operating", "income", "profit")):
            return html_file.get_text(strip=True)
        if revenue_only is None:
            revenue_only = html_file.get_text(strip=True)
    return revenue_only


def _to_number(raw: str) -> float | None:
    v = raw.replace("$", "").replace(",", "").strip()
    if not v or v in ("—", "-"):
        return None
    negative = v.startswith("(") and v.endswith(")")
    v = v.strip("()")
    try:
        n = float(v)
        return -n if negative else n
    except ValueError:
        return None


def _parse_segment_table(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        return {}
    rows = table.find_all("tr")
    if len(rows) < 3:
        return {}

    # R-Files geben die Skalierung im Titel an ("$ in Millions" / "in Thousands").
    # Der Rest der Pipeline (companyfacts) rechnet in rohen USD — hier normalisieren,
    # sonst stimmen Segmentwerte um den Skalierungsfaktor nicht mit core_metrics überein.
    title_text = rows[0].find_all(["td", "th"])[0].get_text(" ", strip=True).lower()
    if "in billions" in title_text:
        scale = 1_000_000_000
    elif "in millions" in title_text:
        scale = 1_000_000
    elif "in thousands" in title_text:
        scale = 1_000
    else:
        scale = 1

    duration_cells = rows[0].find_all(["td", "th"])[1:]
    durations = []
    for c in duration_cells:
        span = int(c.get("colspan") or 1)
        durations.extend([c.get_text(strip=True)] * span)

    dates = [c.get_text(strip=True) for c in rows[1].find_all(["td", "th"])]
    columns = list(zip(durations, dates))
    if not columns:
        return {}

    shortest = durations[0]
    period_dates = [d for dur, d in columns if dur == shortest]
    current_date = period_dates[0] if len(period_dates) > 0 else None
    prior_date   = period_dates[1] if len(period_dates) > 1 else None

    # Boilerplate-Zwischenüberschriften (z.B. MSFTs "Segment Reporting
    # Information [Line Items]" oder J&Js "Sales by segment of business")
    # wiederholen sich vor JEDEM Segment und sind daher an ihrer Häufigkeit
    # erkennbar — echte Segmentnamen tauchen dagegen je genau einmal auf.
    from collections import Counter
    empty_labels = []
    for tr in rows[2:]:
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        label = cells[0].get_text(strip=True)
        values = [c.get_text(strip=True) for c in cells[1:]]
        if label and all(not v for v in values):
            empty_labels.append(label)
    boilerplate = {lbl for lbl, count in Counter(empty_labels).items() if count > 1}

    segments = {}
    current_segment = None
    for tr in rows[2:]:
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        label = cells[0].get_text(strip=True)
        values = [c.get_text(strip=True) for c in cells[1:]]
        numeric = [_to_number(v) for v in values]
        numeric = [n * scale if n is not None else None for n in numeric]

        if all(n is None for n in numeric):
            if label and "line items" not in label.lower() and label not in boilerplate:
                current_segment = label
            continue

        seg_name = current_segment or "Total"
        key = label.lower().replace(" ", "_")
        by_date = {}
        for (duration, date), n in zip(columns, numeric):
            # Nur die kürzeste Periodenlänge behalten — bei mehreren Spalten
            # (z.B. "3 Months Ended" UND "9 Months Ended") teilen sich Q1-Spalten
            # oft dasselbe Enddatum, würden sich also sonst gegenseitig überschreiben.
            if duration != shortest:
                continue
            if date and n is not None:
                by_date[date] = n
        segments.setdefault(seg_name, {})[key] = by_date

    return {
        "current_period_date": current_date,
        "prior_year_period_date": prior_date,
        "segments": segments,
    }


def get_segment_data(cik: str, accession: str) -> dict:
    """
    Segment-Umsatz/Gross-Margin aus SECs vorgerenderten R-Files.
    Best-effort: liefert {} wenn das Filing keine passende Segment-Tabelle hat
    oder die Struktur vom erwarteten Layout abweicht.
    """
    try:
        r_file = _find_segment_report_file(cik, accession)
        if not r_file:
            return {}
        html_response = requests.get(
            _archives_url(cik, accession, r_file), headers=_sec_headers(), timeout=20
        )
        if html_response.status_code != 200:
            return {}
        raw = _parse_segment_table(html_response.text)
    except Exception:
        return {}

    if not raw.get("segments"):
        return {}

    current_date = raw["current_period_date"]
    prior_date   = raw["prior_year_period_date"]

    # Filer benennen die Umsatzzeile unterschiedlich ("Revenue", "Sales to
    # customers", "Net sales" ...) — erster Treffer aus der Alias-Liste gewinnt.
    revenue_keys = ("revenue", "sales_to_customers", "net_sales", "total_revenue", "sales", "net_revenue")
    cor_keys     = ("cost_of_revenue", "cost_of_products_sold", "cost_of_goods_sold", "cost_of_sales")

    def _by_key(metrics, keys):
        for k in keys:
            if k in metrics:
                return metrics[k]
        return {}

    result = {}
    for seg_name, metrics in raw["segments"].items():
        rev_by_date = _by_key(metrics, revenue_keys)
        cor_by_date = _by_key(metrics, cor_keys)

        revenue       = rev_by_date.get(current_date)
        revenue_prior = rev_by_date.get(prior_date) if prior_date else None
        cor           = cor_by_date.get(current_date)
        cor_prior     = cor_by_date.get(prior_date) if prior_date else None

        gross_profit = revenue - cor if revenue is not None and cor is not None else None
        gross_margin_pct = gross_profit / revenue if gross_profit is not None and revenue else None

        gross_profit_prior = (
            revenue_prior - cor_prior if revenue_prior is not None and cor_prior is not None else None
        )
        gross_margin_pct_prior = (
            gross_profit_prior / revenue_prior if gross_profit_prior is not None and revenue_prior else None
        )

        revenue_yoy_change = (
            (revenue - revenue_prior) / revenue_prior
            if revenue is not None and revenue_prior else None
        )

        result[seg_name] = {
            "revenue":                    revenue,
            "gross_profit":               gross_profit,
            "gross_margin_pct":           round(gross_margin_pct, 4) if gross_margin_pct is not None else None,
            "revenue_yoy_change":         round(revenue_yoy_change, 4) if revenue_yoy_change is not None else None,
            "gross_margin_pct_prior_year": round(gross_margin_pct_prior, 4) if gross_margin_pct_prior is not None else None,
        }

    # Manche Filer (z.B. J&J) berichten tief verschachtelte Aufschlüsselungen
    # (Geografie x Therapiebereich x Produktlinie) in derselben Tabelle statt
    # nur der Top-Level-Segmente wie MSFT — auf die größten begrenzen, damit
    # der LLM-Prompt später nicht mit Dutzenden Zeilen aufgebläht wird.
    if len(result) > 10:
        ranked = sorted(result.items(), key=lambda kv: abs(kv[1]["revenue"] or 0), reverse=True)
        result = dict(ranked[:10])

    return {
        "period": {"end": current_date},
        "segments": result,
    }
