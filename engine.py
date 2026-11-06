import json
import math
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OpenMarketWeather/2.4"
}

def fetch_json(url, timeout=10):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"[!] Warning: Could not fetch JSON {url}: {e}")
        return None

# ==============================================================================
# SÄULE 1: MARKT-MECHANIK (VIX & MOVE)
# ==============================================================================
def get_market_volatility():
    tickers = {"VIX": "%5EVIX", "MOVE": "%5EMOVE"}
    scores = {}
    for name, ticker in tickers.items():
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
        data = fetch_json(url)
        val = None
        if data and "chart" in data and data["chart"]["result"]:
            meta = data["chart"]["result"][0].get("meta", {})
            val = meta.get("regularMarketPrice")
        if val is not None:
            if name == "VIX":
                score = min(100, max(0, int((val - 12) * (100 / 23))))
                scores["vix"] = (score, round(val, 2))
            elif name == "MOVE":
                score = min(100, max(0, int((val - 70) * (100 / 80))))
                scores["move"] = (score, round(val, 2))
        else:
            scores[name.lower()] = (20, 16.5 if name == "VIX" else 95.0)
            
    avg_score = int((scores["vix"][0] * 0.5) + (scores["move"][0] * 0.5))
    return avg_score, scores["vix"][1], scores["move"][1]

# ==============================================================================
# SÄULE 2: FINRA DARK POOL SHORT VOLUME (SPY)
# ==============================================================================
def get_finra_darkpool_short():
    today = datetime.utcnow()
    for i in range(0, 6):
        date_str = (today - timedelta(days=i)).strftime("%Y%m%d")
        url = f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date_str}.txt"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=8) as resp:
                for raw_line in resp:
                    line = raw_line.decode('utf-8', errors='ignore')
                    if "|SPY|" in line:
                        parts = line.strip().split("|")
                        if len(parts) >= 5 and parts[1] == "SPY":
                            short_vol = float(parts[2])
                            total_vol = float(parts[4])
                            if total_vol > 0:
                                ratio = round((short_vol / total_vol) * 100, 1)
                                score = min(100, max(0, int((ratio - 42) * 5)))
                                return score, ratio, date_str
        except Exception:
            continue
    return 25, 48.0, "Fallback"

# ==============================================================================
# SÄULE 3: DOLLAR PLUMBING (TGA & SWAPS)
# ==============================================================================
def get_liquidity_plumbing():
    tga_url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/dts_table_1?filter=account_type:eq:Treasury%20General%20Account%20(TGA)%20Closing%20Balance&sort=-record_date&page[size]=10"
    data = fetch_json(tga_url)
    tga_bal, tga_change, tga_score = 850.0, 0.0, 15
    
    if data and "data" in data and len(data["data"]) > 0:
        tga_rows = []
        for row in data["data"]:
            val = row.get("open_today_bal")
            if val in (None, "null", "", "None"):
                val = row.get("close_today_bal")
            if val not in (None, "null", "", "None"):
                try:
                    tga_rows.append(float(val))
                except ValueError:
                    pass
        if len(tga_rows) >= 2:
            latest = tga_rows[0]
            prev = tga_rows[min(4, len(tga_rows) - 1)]
            tga_change = (latest - prev) / 1000.0
            tga_bal = latest / 1000.0
            tga_score = min(100, int(abs(tga_change) * 1.5))

    swaps_url = "https://markets.newyorkfed.org/api/fxs/all/latest.json"
    swap_data = fetch_json(swaps_url)
    swap_volume_b = 0.0
    if swap_data and "data" in swap_data:
        for deal in swap_data.get("data", []):
            amt = deal.get("amount", 0)
            swap_volume_b += float(amt) / 1000000000.0
            
    swap_score = min(100, int(swap_volume_b * 10))
    composite = int((tga_score * 0.7) + (swap_score * 0.3))
    return composite, round(tga_bal, 1), round(tga_change, 1), round(swap_volume_b, 2)

# ==============================================================================
# SÄULE 4: KREDIT & RECHT (SEC FORM 8-K ITEM 2.04 - 14 TAGE)
# ==============================================================================
def get_credit_distress_vector():
    today = datetime.utcnow()
    two_weeks_ago = (today - timedelta(days=14)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    
    sec_url = f"https://efts.sec.gov/LATEST/search-index?q=%22Item+2.04%22&forms=8-K&startdt={two_weeks_ago}&enddt={today_str}"
    sec_data = fetch_json(sec_url, timeout=6)
    filing_count = 0
    if sec_data and "hits" in sec_data and "total" in sec_data["hits"]:
        filing_count = sec_data["hits"]["total"].get("value", 0)
        
    credit_score = min(100, max(5, int(filing_count * 4.0)))
    return credit_score, filing_count

# ==============================================================================
# SÄULE 5: KOGNITIV & PHYSISCH (WIKIPEDIA & CBP LAREDO)
# ==============================================================================
def get_cognitive_and_physical():
    articles = ["Bank_run", "Credit_default_swap", "Circuit_breaker_(stock_market)", "Force_majeure", "Bail-in", "Insolvency"]
    today = datetime.utcnow()
    end_date = (today - timedelta(days=1)).strftime("%Y%m%d")
    start_date = (today - timedelta(days=25)).strftime("%Y%m%d")
    
    anomalies = []
    for art in articles:
        url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/user/{art}/daily/{start_date}/{end_date}"
        data = fetch_json(url, timeout=5)
        if data and "items" in data and len(data["items"]) >= 10:
            views = [x["views"] for x in data["items"]]
            baseline = views[:-3]
            recent = views[-3:]
            avg_base = sum(baseline) / len(baseline)
            std_base = math.sqrt(sum((x - avg_base) ** 2 for x in baseline) / len(baseline)) or 1
            z_score = (sum(recent)/len(recent) - avg_base) / std_base
