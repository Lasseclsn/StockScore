from pathlib import Path
import scorer
import agent
import get_data
from extractor import extract_10k, extract_10q, extract_vantage

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"


def _cache_exists(ticker: str) -> bool:
    return all(
        (OUTPUT_DIR / f"{ticker}_{s}.json").exists()
        for s in ("10k", "10q", "8k", "vantage")
    )


def main() -> None:
    ticker_symbol = input("Ticker-Symbol: ").upper()

    if _cache_exists(ticker_symbol):
        answer = input(f"  Vorhandene Daten für {ticker_symbol} gefunden. Benutzen? [j/n]: ").strip().lower()
        use_cache = answer in ("j", "ja", "y", "yes")
    else:
        use_cache = False

    if not use_cache:
        print(f"Lade Daten für {ticker_symbol}...")

        cik = get_data.getCik(ticker_symbol)
        if not cik:
            print("Fehler: Ticker nicht gefunden.")
            return

        submission_data = get_data.getSubmissionData(cik)
        if not submission_data:
            print("Fehler: Keine Submission-Daten gefunden.")
            return

        latest_10k = get_data.get_latest_filing_by_form(submission_data, "10-K")
        latest_10q = get_data.get_latest_filing_by_form(submission_data, "10-Q")
        latest_8k  = get_data.get_latest_filing_by_form(submission_data, "8-K")

        print(f"  10-K: {latest_10k['filing_date'] if latest_10k else 'nicht gefunden'}")
        print(f"  10-Q: {latest_10q['filing_date'] if latest_10q else 'nicht gefunden'}")
        print(f"  8-K:  {latest_8k['filing_date']  if latest_8k  else 'nicht gefunden'}")

        print("Lade Company Facts von SEC...")
        company_facts = get_data.fetch_company_facts(cik)

        print("Lade Filings von SEC...")
        get_data.fetch_and_save_filing(latest_10k, cik, ticker_symbol, "10k", company_facts)
        get_data.fetch_and_save_filing(latest_10q, cik, ticker_symbol, "10q", company_facts)
        get_data.fetch_and_save_filing(latest_8k,  cik, ticker_symbol, "8k", company_facts)

        print("Lade Freitext-Abschnitte (Risk Factors, MD&A, Segmente) von SEC...")
        get_data.fetch_and_save_filing_text(latest_10k, cik, ticker_symbol, "10k")
        get_data.fetch_and_save_filing_text(latest_10q, cik, ticker_symbol, "10q")
        get_data.fetch_and_save_filing_text(latest_8k,  cik, ticker_symbol, "8k")

        print("Lade Alpha Vantage Overview...")
        get_data.fetch_and_save_overview(ticker_symbol)
    else:
        print(f"Nutze vorhandene Daten für {ticker_symbol}.")

    print("Extrahiere Kennzahlen...")

    values_10k = {}
    k10_path = BASE_DIR / "output" / f"{ticker_symbol}_10k.json"
    if k10_path.exists():
        values_10k = extract_10k(k10_path)

    values_10q = {}
    q10_path = BASE_DIR / "output" / f"{ticker_symbol}_10q.json"
    if q10_path.exists():
        values_10q = extract_10q(q10_path)
    else:
        print(f"  10-Q nicht gefunden, wird übersprungen.")

    values_vantage = {}
    vantage_path = BASE_DIR / "output" / f"{ticker_symbol}_vantage.json"
    if vantage_path.exists():
        values_vantage = extract_vantage(vantage_path)

    if values_vantage and values_10k and values_10q:
        result = scorer.score(values_10k, values_10q, values_vantage)
        print("\n" + "=" * 60)
        print(f"  SCORE: {result['score']} / {result['max_score']}")
        print(f"  SIGNAL: {result['signal']}")
        print(f"  WAHRSCHEINLICHKEIT KURSANSTIEG: {result['probability_up']*100:.1f}%")
        print("=" * 60)

        if not result["passed_knockout"]:
            print("KNOCKOUT-GRÜNDE:")
            for r in result["knockout_reasons"]:
                print(f"  - {r}")
        else:
            print("\nSCORE-BREAKDOWN:")
            for block, data in result["blocks"].items():
                print(f"  {block:<20} {data['score']:>5.1f} / {data['max']}")

            print("\nDEEPSEEK — GESAMTEINSCHÄTZUNG:")
            print("-" * 60)
            print(agent.analyze(ticker_symbol, result, values_10k, values_10q, values_vantage))

            print("\nDEEPSEEK — MD&A-ANALYSE:")
            print("-" * 60)
            print(agent.analyze_mda(ticker_symbol, values_10k, values_10q, values_vantage))

            print("\nDEEPSEEK — IMPLIZITE GUIDANCE:")
            print("-" * 60)
            print(agent.extract_guidance(ticker_symbol, values_10k, values_10q, values_vantage))

            print("\nDEEPSEEK — ANOMALIE-ERKLÄRUNG:")
            print("-" * 60)
            print(agent.explain_anomalies(ticker_symbol, result, values_10k, values_10q, values_vantage))


if __name__ == "__main__":
    main()
