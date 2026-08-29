import json
from pathlib import Path
import requests

import filing_text

BASE_DIR = Path(__file__).parent


def load_api_key(key_name: str) -> str:
    env_path = Path(__file__).parent / ".env"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)

        if key_name == key.strip():
            return value.strip().strip('"').strip("'")

    raise RuntimeError("Kein API Key gefunden.")


def _sec_headers() -> dict:
    """
    SEC verlangt einen aussagekräftigen User-Agent (Name/App + Kontakt) für
    jeden Request an sec.gov/data.sec.gov — sonst 403. Kommt aus .env statt
    hartcodiert im Quellcode, damit kein persönlicher Kontakt öffentlich im
    Repo landet.
    """
    return {
        "User-Agent": load_api_key("SEC_USER_AGENT"),
        "Accept-Encoding": "gzip, deflate",
    }


def getCik(ticker_symbol: str) -> str | None:
    """Ticker -> CIK über SECs freie Ticker-Zuordnungsdatei (kein API-Key nötig)."""
    response = requests.get(
        "https://www.sec.gov/files/company_tickers.json",
        headers=_sec_headers(),
        timeout=20,
    )
    if response.status_code != 200:
        print("Fehler beim Abrufen der SEC-Ticker-Liste.")
        return None

    ticker_symbol = ticker_symbol.upper()
    for entry in response.json().values():
        if entry.get("ticker", "").upper() == ticker_symbol:
            return "CIK" + str(entry["cik_str"]).zfill(10)

    print("No data was found, please check the ticker symbol and try again.")
    return None


def getSubmissionData(cik: str) -> dict | None:
    submission_url = f"https://data.sec.gov/submissions/{cik}.json"

    response = requests.get(submission_url, headers=_sec_headers(), timeout=20)
    if response.status_code != 200:
        print("No data was found, please check the CIK and try again.")
        return None
    return response.json()


def get_latest_filing_by_form(submission_data, target_form: str):
    recent = submission_data["filings"]["recent"]

    for form, filing_date, accession, primary_doc in zip(
        recent["form"],
        recent["filingDate"],
        recent["accessionNumber"],
        recent["primaryDocument"],
    ):
        if form == target_form:
            return {
                "form": form,
                "filing_date": filing_date,
                "accession": accession,
                "primary_document": primary_doc,
            }
    return None


def fetch_company_facts(cik: str) -> dict | None:
    """
    Alle strukturierten XBRL-Fakten des Unternehmens über alle Filings hinweg —
    SECs freie companyfacts-API, kein API-Key nötig. Ein Aufruf pro Ticker,
    die einzelnen Filings werden anschließend per Accession-Nummer herausgefiltert.
    """
    url = f"https://data.sec.gov/api/xbrl/companyfacts/{cik}.json"
    response = requests.get(url, headers=_sec_headers(), timeout=30)
    if response.status_code != 200:
        print("Fehler beim Abrufen der SEC Company Facts.")
        return None
    return response.json()


def _to_period_item(item: dict) -> dict:
    """Wandelt einen rohen SEC-XBRL-Fact ({val, start, end, ...}) ins intern erwartete {value, period} Format um."""
    if item.get("start"):
        period = {"startDate": item["start"], "endDate": item["end"]}
    else:
        period = {"instant": item["end"]}
    return {"value": item["val"], "period": period}


def _facts_for_filing(company_facts: dict, accession: str) -> dict:
    """Filtert companyfacts auf die Fakten, die genau in diesem Filing (per Accession-Nummer) berichtet wurden."""
    result = {}
    facts = company_facts.get("facts", {})
    for taxonomy in ("us-gaap", "dei"):
        for concept, entry in facts.get(taxonomy, {}).items():
            matched = [
                _to_period_item(item)
                for unit_facts in entry.get("units", {}).values()
                for item in unit_facts
                if item.get("accn") == accession
            ]
            if matched:
                result[concept] = matched
    return result


def fetch_and_save_filing(filing, cik, ticker_symbol, suffix, company_facts):
    if filing is None:
        print(f"Keine {suffix} Einreichung gefunden.")
        return
    if company_facts is None:
        print(f"Keine Company-Facts verfügbar, {suffix} wird übersprungen.")
        return

    facts = _facts_for_filing(company_facts, filing["accession"])
    save_json(facts, f"{ticker_symbol}_{suffix.lower()}.json")


def fetch_and_save_filing_text(filing, cik, ticker_symbol, suffix):
    """
    Holt Freitext-Abschnitte (Risk Factors, MD&A, Legal Proceedings) bzw.
    bei 10-Q zusätzlich Segmentdaten direkt aus dem primären Filing-Dokument.
    companyfacts liefert nur Zahlen — das hier deckt den Rest kostenlos ab.
    """
    if filing is None:
        return

    html = filing_text.fetch_filing_html(cik, filing)
    if html is None:
        print(f"Konnte {suffix}-Dokument nicht laden, Freitext wird übersprungen.")
        return

    suffix = suffix.lower()
    if suffix == "10k":
        data = filing_text.get_10k_sections(html)
    elif suffix == "10q":
        data = filing_text.get_10q_sections(html)
        data["segments"] = filing_text.get_segment_data(cik, filing["accession"])
    elif suffix == "8k":
        data = filing_text.get_8k_items(html)
    else:
        return

    save_json(data, f"{ticker_symbol}_{suffix}_text.json")


def fetch_and_save_overview(ticker_symbol):
    url = (
        "https://www.alphavantage.co/query?function=OVERVIEW&symbol="
        + ticker_symbol
        + "&apikey="
        + load_api_key("Alpha_Vantage_API_KEY")
    )

    response = requests.get(url)
    if response.status_code != 200:
        print("Fehler beim Abrufen der Alpha Vantage-Daten.")
        return

    data = response.json()
    save_json(data, f"{ticker_symbol}_vantage.json")


def save_json(data: dict, filename: str) -> None:
    out_dir = BASE_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
