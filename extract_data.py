from pathlib import Path
import json, re

BASE_DIR = Path(__file__).parent

KEYS = {
    "revenue": ["revenue", "revenues", "totalrevenue", "totalrevenues"],
    "gross_profit": ["grossprofit", "gross_profit"],
    "operating_income": ["operatingincome", "incomefromoperations"],
    "net_income": ["netincome", "netearnings"],
    "diluted_eps": ["dilutedeps", "dilutedearningspershare"],
    "shares_diluted": ["weightedaveragesharesdiluted", "sharesdiluted"],
    "cash_and_equivalents": ["cashandcashequivalents", "cash"],
    "total_assets": ["totalassets", "assets"],
    "total_liabilities": ["totalliabilities", "liabilities"],
    "shareholders_equity": ["totalstockholdersequity", "shareholdersequity", "equity"],
    "total_debt": ["totaldebt", "longtermdebt", "debt"],
    "operating_cash_flow": ["netcashprovidedbyoperatingactivities", "operatingcashflow"],
    "capex": ["capitalexpenditures", "capex"],
}

_num_re = re.compile(r"-?\d[\d,\.]*")


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _parse_number(v):
    if v is None: return None
    if isinstance(v, (int, float)): return float(v)
    m = _num_re.search(str(v))
    if not m: return None
    s = m.group(0).replace(",", "")
    try:
        return float(s)
    except:
        return None


def _find_values(o, found):
    if isinstance(o, dict):
        for k, v in o.items():
            nk = _normalize(k)
            for key, candidates in KEYS.items():
                if found.get(key) is not None:
                    continue
                if any(c in nk for c in candidates):
                    val = _parse_number(v)
                    if val is not None:
                        found[key] = val
            _find_values(v, found)
    elif isinstance(o, list):
        for i in o:
            _find_values(i, found)


def extract_data_10k(ticker: str):
    path = BASE_DIR / "output" / f"{ticker}_10k.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    found = {k: None for k in KEYS}
    _find_values(data, found)
    # free cash flow if possible
    op = found.get("operating_cash_flow")
    cap = found.get("capex")
    found["free_cash_flow"] = (
        (op - cap) if (op is not None and cap is not None) else None
    )
    return {"file": str(path), "ticker": ticker.upper(), "financials": found}
