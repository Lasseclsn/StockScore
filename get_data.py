import logging
import os
import json
from pathlib import Path
import pandas as pd
from google import genai
import requests

BASE_DIR = Path(__file__).parent
SYSTEM_INSTRUCTION_PATH = BASE_DIR / "system_instruction.json"


def load_api_key(key_name: str) -> str:
    env_path = Path(__file__).parent / ".env"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        key, value = line.split(":", 1)

        if key_name == key.strip():
            return value.strip().strip('"').strip("'")

    raise RuntimeError("Kein API Key gefunden.")


def create_agent() -> genai.Client:
    """Create a Google GenAI client authenticated with an API key."""
    return genai.Client(api_key=load_api_key("Gemini_API_KEY"))


def load_system_instruction() -> str:
    instruction = json.loads(SYSTEM_INSTRUCTION_PATH.read_text(encoding="utf-8"))
    return json.dumps(instruction, ensure_ascii=False, indent=2)


def getCik(ticker_symbol) -> str | None:
    company_url = (
        "https://api.sec-api.io/mapping/ticker/"
        + ticker_symbol
        + "?token="
        + load_api_key("SEC_API_KEY")
    )
    company_data = requests.get(company_url, timeout=20).json()
    if company_data is None:
        print("No data was found, please check the ticker symbol and try again.")
        return None
    else:
        cik = company_data[0]["cik"]
        cik = "CIK" + str(int(cik)).zfill(10)
        return cik


def getSubmissionData(cik: str) -> dict | None:
    submission_url = f"https://data.sec.gov/submissions/{cik}.json"

    headers = {
        "User-Agent": "finance-agent lasse.clausen@gmx.com",
        "Accept-Encoding": "gzip, deflate",
        "Host": "data.sec.gov",
    }

    submission_data = requests.get(submission_url, headers=headers, timeout=20).json()
    if submission_data is None:
        print("No data was found, please check the CIK and try again.")
        return None
    else:
        return submission_data


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


def fetch_and_save_filing(filing, cik, ticker_symbol, suffix, xbrl_api):
    if filing is None:
        print(f"Keine {suffix} Einreichung gefunden.")
        return

    url = (
        "https://www.sec.gov/Archives/edgar/data/"
        + cik[6:]
        + "/"
        + filing["accession"].replace("-", "")
        + "/"
        + filing["primary_document"]
    )

    xbrl_json = xbrl_api.xbrl_to_json(htm_url=url)
    save_json(xbrl_json, f"{ticker_symbol}_{suffix.lower()}.json")


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
