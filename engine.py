#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OPEN MARKET WEATHER OBSERVATORY // HYBRID MACRO & CRYPTO
Version: 3.5.1 (stdlib only)

Optional environment variables:
  OMW_CONTACT   Contact string for the User-Agent sent to SEC EDGAR and Wikimedia.
                Both ask for a real contact, ideally an e-mail address.
  OMW_BASE_URL  Public URL of your deployment. Used to read the previous state
                when there is no recent local weather.json (needed for hysteresis).
"""

import csv
import html as html_lib
import json
import math
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

VERSION = "3.5.1"
BASE_URL = os.environ.get(
    "OMW_BASE_URL", "https://open-market-weather.hartmut-nese.workers.dev"
).rstrip("/")
CONTACT = os.environ.get(
    "OMW_CONTACT", "admin@marktwetter.org"
)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
COMPLIANT_HEADERS = {"User-Agent": f"MarketWeatherObservatory/{VERSION} ({CONTACT})"}

# Hyperliquid pays a fixed baseline of 0.01% per 8h, which is about 10.95% APR.
# Only deviations from it are treated as stress.
FUNDING_BASELINE_APR = 10.95
# The NY Fed "latest" file can list small routine operations. Below this
# amount (in billions USD) swap usage counts as noise, not as stress.
SWAP_NOISE_B = 1.0
# A previous state older than this is ignored for the hysteresis logic.
STATE_MAX_AGE_HOURS = 3

HISTORY_FILE = "history.csv"
HISTORY_HEADER = [
    "timestamp", "composite", "vix", "move", "btc_funding", "dvol", "spy_svr",
    "tga_bal", "tga_flow", "swaps_b", "sec_8k", "wiki_z", "cbp_wait",
]

WEIGHTS = {
    "market_volatility": 0.20,
    "crypto_leverage": 0.20,
    "short_volume": 0.15,
    "dollar_liquidity": 0.20,
    "credit_stress": 0.15,
    "odds_and_ends": 0.10,
}

# Old pillar names, still written to the JSON for existing consumers. Remove in v4.
LEGACY_KEYS = {
    "market_implied": "market_volatility",
    "crypto_247": "crypto_leverage",
    "dark_pool_finra": "short_volume",
    "liquidity_plumbing": "dollar_liquidity",
    "credit_statutory": "credit_stress",
    "cognitive_physical": "odds_and_ends",
}

# Which sub-feed flags belong to which pillar (for the "[fallback: ...]" tags).
FALLBACK_PARTS = {
    "market_volatility": [("fallback", "yahoo")],
    "crypto_leverage": [("hl_fallback", "hyperliquid"), ("dvol_fallback", "deribit")],
    "short_volume": [("fallback", "finra")],
    "dollar_liquidity": [("tga_fallback", "tga"), ("swaps_fallback", "ny fed")],
    "credit_stress": [("fallback", "sec")],
    "odds_and_ends": [("wiki_fallback", "wikipedia"), ("cbp_fallback", "cbp")],
}


# ==============================================================================
# HELPERS
# ==============================================================================
def utc_now():
    return datetime.now(timezone.utc)


def clamp(value, lo=0, hi=100):
    return max(lo, min(hi, value))


def to_float(x):
    """float(x) or None. Accepts numbers and strings like '1,234.5'."""
    if x is None or isinstance(x, bool):
        return None
    try:
        return float(str(x).replace(",", "").strip())
    except ValueError:
        return None


def dig(obj, *path, default=None):
    """Safe nested lookup: dig(data, 'a', 0, 'b')."""
    for key in path:
        try:
            obj = obj[key]
        except (KeyError, IndexError, TypeError):
            return default
    return obj


def find_list(obj, key):
    """First list stored under `key` anywhere inside obj, or None."""
    if isinstance(obj, dict):
        if isinstance(obj.get(key), list):
            return obj[key]
        children = obj.values()
    elif isinstance(obj, list):
        children = obj
    else:
        return None
    for child in children:
        found = find_list(child, key)
        if found is not None:
            return found
    return None


def fetch_json(url, timeout=10, headers=None, data=None, retries=1):
    """GET (or POST with data) and parse JSON. Returns None on failure.
    Retries once on network errors and 5xx, never on 4xx."""
    req_headers = headers or DEFAULT_HEADERS
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print(f"[!] Warning: HTTP {e.code} from {url}")
            if e.code < 500:
                return None
        except Exception as e:
            print(f"[!] Warning: Could not fetch JSON from {url}: {e}")
        if attempt < retries:
            time.sleep(1.5)
    return None


# ==============================================================================
# PILLAR 1: MARKET VOLATILITY (VIX & MOVE)
# ==============================================================================
def yahoo_last_price(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
    return to_float(dig(fetch_json(url), "chart", "result", 0, "meta", "regularMarketPrice"))


def get_market_volatility():
    vix = yahoo_last_price("%5EVIX")
    move = yahoo_last_price("%5EMOVE")
    fallback = vix is None or move is None
    if vix is None:
        vix = 16.5
    if move is None:
        move = 95.0
    vix_score = clamp(int((vix - 12) * (100 / 23)))      # 12..35
    move_score = clamp(int((move - 70) * (100 / 80)))    # 70..150
    return {
        "score": int(vix_score * 0.5 + move_score * 0.5),
        "vix": round(vix, 2),
        "move_index": round(move, 2),
        "fallback": fallback,
    }


# ==============================================================================
# PILLAR 2: CRYPTO LEVERAGE (HYPERLIQUID FUNDING & DERIBIT DVOL)
# ==============================================================================
def funding_stress(apr):
    """Stress from the deviation to the baseline. Continuous (no cliffs):
    gentle slope inside the normal band, steeper outside. Negative funding
    starts to count earlier (from about -7% APR) than positive (from about +25%)."""
    dev = apr - FUNDING_BASELINE_APR
    limit, steep = (14.0, 3.0) if dev >= 0 else (18.0, 3.5)
    d = abs(dev)
    return clamp(int(8 + min(d, limit) * 1.2 + max(0.0, d - limit) * steep))


def get_crypto_leverage():
    funding_apr, oi_mil, dvol = FUNDING_BASELINE_APR, 0.0, 52.0
    hl_fallback = dvol_fallback = True

    payload = json.dumps({"type": "metaAndAssetCtxs"}).encode("utf-8")
    data = fetch_json(
        "https://api.hyperliquid.xyz/info",
        timeout=6,
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        data=payload,
    )
    try:
        universe, ctxs = data[0]["universe"], data[1]
        idx = next(i for i, c in enumerate(universe) if c.get("name") == "BTC")
        ctx = ctxs[idx]
        funding = round(float(ctx["funding"]) * 24 * 365 * 100, 1)
        oi = round(float(ctx["openInterest"]) * float(ctx["oraclePx"]) / 1_000_000, 1)
        funding_apr, oi_mil, hl_fallback = funding, oi, False
    except (TypeError, KeyError, IndexError, StopIteration, ValueError, AttributeError):
        print("[!] Warning: Hyperliquid response not usable, using fallback funding")

    dvol_data = fetch_json(
        "https://www.deribit.com/api/v2/public/get_index_price?index_name=btcdvol_usdc",
        timeout=6,
    )
    value = to_float(dig(dvol_data, "result", "index_price"))
    if value is not None:
        dvol, dvol_fallback = round(value, 1), False

    vola_stress = clamp(int((dvol - 42.0) * (100 / 38)))   # 42..80
    return {
        "score": int(funding_stress(funding_apr) * 0.6 + vola_stress * 0.4),
        "btc_funding_apr": funding_apr,
        "btc_oi_mil": oi_mil,
        "dvol_index": dvol,
        "fallback": hl_fallback or dvol_fallback,
        "hl_fallback": hl_fallback,
        "dvol_fallback": dvol_fallback,
    }


# ==============================================================================
# PILLAR 3: SHORT VOLUME (FINRA REG SHO, SPY)
# ==============================================================================
def short_volume_score(ratio):
    """Roughly 50% -> 18, 55% -> 43, 60% -> 68, 65% -> 93. Below ~46% -> 0."""
    return clamp(int((ratio - 46.4) * 5))


def finra_spy_ratio(date_str):
    """SPY short volume share (in %) for one day, or None if the file is missing."""
    url = f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date_str}.txt"
    try:
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="ignore")
                if "|SPY|" not in line:
                    continue
                parts = line.strip().split("|")
                if len(parts) >= 5 and parts[1] == "SPY":
                    short_vol, total_vol = float(parts[2]), float(parts[4])
                    if total_vol > 0:
                        return round(short_vol / total_vol * 100, 1)
    except Exception:
        pass
    return None


def get_short_volume():
    today = utc_now()
    for i in range(7):
        date_str = (today - timedelta(days=i)).strftime("%Y%m%d")
        ratio = finra_spy_ratio(date_str)
        if ratio is not None:
            return {
                "score": short_volume_score(ratio),
                "spy_short_volume_ratio": ratio,
                "report_date": date_str,
                "fallback": False,
            }
    return {
        "score": short_volume_score(49.0),
        "spy_short_volume_ratio": 49.0,
        "report_date": "Fallback",
        "fallback": True,
    }


# ==============================================================================
# PILLAR 4: DOLLAR LIQUIDITY (TREASURY GENERAL ACCOUNT & NY FED SWAP LINES)
# ==============================================================================
def get_dollar_liquidity():
    tga_url = (
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/"
        "operating_cash_balance?filter=account_type:eq:Treasury%20General%20Account%20(TGA)"
        "%20Closing%20Balance&sort=-record_date&page%5Bsize%5D=10"
    )
    rows = dig(fetch_json(tga_url), "data", default=[]) or []
    values = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        val = to_float(row.get("open_today_bal"))
        if val is None:
            val = to_float(row.get("close_today_bal"))
        if val is not None:
            values.append(val)

    tga_bal, tga_change, tga_score, tga_fallback = 850.0, 0.0, 15, True
    if len(values) >= 2:
        latest, prev = values[0], values[min(4, len(values) - 1)]
        tga_bal = latest / 1000.0                    # millions -> billions
        tga_change = (latest - prev) / 1000.0
        tga_score = clamp(int(abs(tga_change) * 1.5))
        tga_fallback = False

    swap_data = fetch_json("https://markets.newyorkfed.org/api/fxs/all/latest.json")
    operations = find_list(swap_data, "operations")
    swap_b, swaps_fallback = 0.0, True
    if operations is not None:
        # An empty list is the normal case: no swap line usage, not an error.
        swaps_fallback = False
        for op in operations:
            amount = to_float(op.get("amount")) if isinstance(op, dict) else None
            if amount is not None:
                swap_b += amount / 1_000_000_000.0   # assumes USD

    swap_score = clamp(int(swap_b * 10))
    return {
        "score": int(tga_score * 0.7 + swap_score * 0.3),
        "tga_billions": round(tga_bal, 1),
        "tga_5d_flow": round(tga_change, 1),
        "swaps_billions": round(swap_b, 2),
        "fallback": tga_fallback or swaps_fallback,
        "tga_fallback": tga_fallback,
        "swaps_fallback": swaps_fallback,
    }


# ==============================================================================
# PILLAR 5: CREDIT STRESS (SEC 8-K, ITEM 2.04, LAST 14 DAYS)
# ==============================================================================
def credit_score_from_count(count):
    """Roughly 10 filings -> 14, 12 -> 23, 15 -> 36, 25 -> 80. Floor of 5."""
    return clamp(int((count - 6.8) * 4.4), 5, 100)


def get_credit_stress():
    today = utc_now()
    start = (today - timedelta(days=14)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    url = (
        "https://efts.sec.gov/LATEST/search-index?q=%22Item+2.04%22&forms=8-K"
        f"&dateRange=custom&startdt={start}&enddt={end}"
    )
    data = fetch_json(url, timeout=8, headers=COMPLIANT_HEADERS)
    total = dig(data, "hits", "total")
    if isinstance(total, dict):
        total = total.get("value")
    if isinstance(total, int) and not isinstance(total, bool):
        count, fallback = total, False
    else:
        count, fallback = 11, True
    return {
        "score": credit_score_from_count(count),
        "sec_8k_filings": count,
        "fallback": fallback,
    }


# ==============================================================================
# PILLAR 6: ODDS AND ENDS (WIKIPEDIA CRISIS TRAFFIC 6% & CBP LAREDO TRUCKS 4%)
# ==============================================================================
def wikipedia_zscore(article, start_date, end_date):
    """Mean of the last 7 days against the 3+ weeks before. A full week in the
    recent window cancels the weekday/weekend swing."""
    url = (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/"
        f"all-access/user/{article}/daily/{start_date}/{end_date}"
    )
    items = dig(fetch_json(url, timeout=5, headers=COMPLIANT_HEADERS), "items")
    if not isinstance(items, list) or len(items) < 21:
        return None
    views = [x.get("views", 0) for x in items]
    baseline, recent = views[:-7], views[-7:]
    avg_base = sum(baseline) / len(baseline)
    std_base = math.sqrt(sum((x - avg_base) ** 2 for x in baseline) / len(baseline)) or 1
    return max(0.0, (sum(recent) / len(recent) - avg_base) / std_base)


def laredo_truck_wait():
    """Returns (wait, feed_ok).

    wait:    longest commercial-lane delay in minutes across the Laredo crossings,
             or None when no crossing reports a delay value. That is normal at night:
             the World Trade Bridge is closed from midnight to 7 am (Central) and
             reports no delay data ("Lanes Closed" / "Update Pending").
    feed_ok: False only when the response is unusable or has no Laredo entries at all.
    """
    data = fetch_json("https://bwt.cbp.gov/api/bwtpublicmod", timeout=8)
    if not isinstance(data, list):
        return None, False
    found_laredo = False
    delays = []
    for port in data:
        if not isinstance(port, dict):
            continue
        name = f"{port.get('port_name', '')} {port.get('crossing_name', '')}"
        if "Laredo" not in name:
            continue
        found_laredo = True
        comm = port.get("commercial_vehicle_lanes") or port.get("commercial_lanes") or {}
        if not isinstance(comm, dict):
            continue
        for lane_key in ("standard_lanes", "FAST_lanes", "lanes"):
            lane = comm.get(lane_key)
            if isinstance(lane, dict):
                delay = lane.get("delay_minutes")
                if delay is not None and str(delay).strip().isdigit():
                    delays.append(int(delay))
    return (max(delays) if delays else None), found_laredo


def get_odds_and_ends():
    articles = [
        "Bank_run", "Credit_default_swap", "Circuit_breaker_(stock_market)",
        "Force_majeure", "Bail-in", "Insolvency",
    ]
    today = utc_now()
    end_date = (today - timedelta(days=2)).strftime("%Y%m%d")      # latency buffer
    start_date = (today - timedelta(days=32)).strftime("%Y%m%d")

    zscores = []
    for article in articles:
        z = wikipedia_zscore(article, start_date, end_date)
        if z is not None:
            zscores.append(z)
    wiki_fallback = not zscores
    avg_z = sum(zscores) / len(zscores) if zscores else 0.0
    wiki_score = clamp(int(avg_z * 25))

    wait, cbp_ok = laredo_truck_wait()
    cbp_fallback = not cbp_ok
    # No delay value (bridge closed, update pending) counts as no border stress,
    # and it is not a feed failure.
    phys_score = clamp(int((wait - 15) * (100 / 105))) if wait is not None else 0

    return {
        "score": int(wiki_score * 0.6 + phys_score * 0.4),
        "wiki_z": round(avg_z, 2),
        "wiki_articles_ok": len(zscores),
        "border_wait_m": wait,
        "fallback": wiki_fallback or cbp_fallback,
        "wiki_fallback": wiki_fallback,
        "cbp_fallback": cbp_fallback,
    }


# ==============================================================================
# PREVIOUS STATE (for hysteresis)
# ==============================================================================
def parse_ts(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def read_local_state():
    try:
        with open("weather.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def previous_grid_status():
    """Grid status of the last run, from the local file or the live site.
    Ignored when older than STATE_MAX_AGE_HOURS."""
    loaders = (
        read_local_state,
        lambda: fetch_json(f"{BASE_URL}/weather.json", timeout=6, retries=0),
    )
    for load in loaders:
        prev = load()
        ts = parse_ts(dig(prev, "timestamp"))
        if ts and utc_now() - ts <= timedelta(hours=STATE_MAX_AGE_HOURS):
            status = dig(prev, "tactical_posture", "grid_bots", "status")
            if status:
                return status
    return None


# ==============================================================================
# TACTICAL POSTURE (with hysteresis for the grid bot status)
# ==============================================================================
def generate_tactical_posture(composite, p, fallback_flags, prev_grid_status=None):
    vix = p["market_volatility"]["vix"]
    crypto_score = p["crypto_leverage"]["score"]
    funding = p["crypto_leverage"]["btc_funding_apr"]
    svr = p["short_volume"]["spy_short_volume_ratio"]
    swaps = p["dollar_liquidity"]["swaps_billions"]
    any_fallback = any(fallback_flags.values())
    posture = {}

    # 1. Grid bots. Leaving CAUTION or PAUSED needs clearer readings than entering.
    hot_enter = crypto_score > 65 or composite >= 65
    hot_stay = crypto_score > 58 or composite >= 58
    hot = hot_stay if prev_grid_status == "PAUSED" else hot_enter
    calm_enter = composite < 35 and vix < 20.0 and crypto_score < 40
    calm_return = composite < 28 and vix < 18.5 and crypto_score < 35
    calm = calm_return if prev_grid_status in ("CAUTION", "PAUSED") else calm_enter
    held = (hot and not hot_enter) or (not hot and calm_enter and not calm)

    if hot and not hot_enter:
        grid = ("PAUSED", "#ff0033", "Staying paused until the overall and crypto scores fall below 58.")
    elif hot:
        grid = ("PAUSED", "#ff0033", f"Pause new grids. Dislocation risk elevated (overall {composite}, crypto {crypto_score}).")
    elif calm and any_fallback:
        grid = ("CAUTION", "#ffcc00", "Widen grid bands by 15-25%. Upstream fallback data active on one or more feeds.")
    elif calm:
        grid = ("ACTIVE", "#00ff66", "Calm conditions. Standard grid parameters.")
    else:
        grid = ("CAUTION", "#ffcc00", "Widen grid bands by 15-25%. Reduce leverage / lot sizes.")
    posture["grid_bots"] = {"status": grid[0], "color": grid[1], "action": grid[2], "hysteresis": held}

    # 2. Dip buying
    if composite < 45 and svr < 55.0 and crypto_score < 50 and not any_fallback:
        posture["dip_buying"] = {"status": "FAVORABLE", "color": "#00ff66", "action": "Orderly pullbacks. Liquidity supports absorption."}
    else:
        posture["dip_buying"] = {"status": "DEFENSIVE", "color": "#ff6600", "action": "Support lines fragile. Do not catch falling knives."}

    # 3. Crypto perps
    apr = f"{funding:+.1f}%"
    if funding > 25.0:
        posture["crypto_perps"] = {"status": "OVERHEATED", "color": "#ff0033", "action": f"High perp funding ({apr} APR). Long squeeze risk."}
    elif funding < -7.0:
        posture["crypto_perps"] = {"status": "HEAVY SHORT", "color": "#ff6600", "action": f"Negative perp funding ({apr} APR). Potential short squeeze."}
    elif abs(funding - FUNDING_BASELINE_APR) < 3.0:
        posture["crypto_perps"] = {"status": "NOMINAL", "color": "#00ff66", "action": f"Neutral baseline funding ({apr} APR)."}
    else:
        posture["crypto_perps"] = {"status": "NOMINAL", "color": "#00ff66", "action": f"Moderate derivatives bias ({apr} APR)."}

    # 4. Short volume
    if svr < 52.0:
        posture["dark_pool"] = {"status": "NOMINAL", "color": "#00ff66", "action": f"Normal short volume share on SPY ({svr}%)."}
    elif svr < 59.0:
        posture["dark_pool"] = {"status": "ELEVATED", "color": "#ffcc00", "action": f"Elevated short volume share on SPY ({svr}%)."}
    else:
        posture["dark_pool"] = {"status": "HIGH", "color": "#ff0033", "action": f"High short volume share on SPY ({svr}%)."}

    # 5. Central bank swap lines
    if swaps >= SWAP_NOISE_B:
        posture["collateral"] = {"status": "FRICTION DETECTED", "color": "#ff0033", "action": f"Central bank swap lines in use (${swaps}B)."}
    elif composite >= 50:
        posture["collateral"] = {"status": "WATCH", "color": "#ffcc00", "action": "Swap lines quiet, but overall market friction is elevated."}
    else:
        posture["collateral"] = {"status": "STABLE", "color": "#00ff66", "action": "No meaningful central bank swap usage."}

    return posture


# ==============================================================================
# MAIN ENGINE
# ==============================================================================
def calculate_systemic_weather():
    prev_status = previous_grid_status()

    pillars = {
        "market_volatility": get_market_volatility(),
        "crypto_leverage": get_crypto_leverage(),
        "short_volume": get_short_volume(),
        "dollar_liquidity": get_dollar_liquidity(),
        "credit_stress": get_credit_stress(),
        "odds_and_ends": get_odds_and_ends(),
    }
    composite = int(sum(pillars[k]["score"] * w for k, w in WEIGHTS.items()) + 1e-9)
    fallback_flags = {k: v["fallback"] for k, v in pillars.items()}

    if composite < 25:
        symbol, status, color = "☀️", "CLEAR SKIES", "#00ff66"
        desc = "Systemic friction minimal. Normal market conditions across macro and crypto feeds."
    elif composite < 50:
        symbol, status, color = "⛅", "SCATTERED CLOUDS", "#ffcc00"
        desc = "Operational noise within standard ranges. No immediate systemic fracture."
    elif composite < 75:
        symbol, status, color = "🌧️", "SQUALL / DOWNPOUR", "#ff6600"
        desc = "Elevated friction: notable divergence in crypto leverage, options or liquidity plumbing."
    else:
        symbol, status, color = "⛈️", "SEVERE GALE / SYSTEMIC SHOCK", "#ff0033"
        desc = "High alert: widespread dislocation across multiple operational feeds."

    tactical = generate_tactical_posture(composite, pillars, fallback_flags, prev_status)

    for old_key, new_key in LEGACY_KEYS.items():
        pillars[old_key] = pillars[new_key]

    return {
        "version": VERSION,
        "timestamp": utc_now().strftime("%Y-%m-%d %H:%M UTC"),
        "symbol": symbol,
        "composite_score": composite,
        "status": status,
        "desc": desc,
        "color": color,
        "fallback_flags": fallback_flags,
        "tactical_posture": tactical,
        "pillars": pillars,
    }


# ==============================================================================
# EXPORT
# ==============================================================================
def fb_tag(pillar_key, pillar):
    """'fallback: tga, ny fed' or ''."""
    bad = [label for flag, label in FALLBACK_PARTS[pillar_key] if pillar.get(flag)]
    return f"fallback: {', '.join(bad)}" if bad else ""


def pillar_rows(p):
    mv, cl, sv = p["market_volatility"], p["crypto_leverage"], p["short_volume"]
    dl, cs, oe = p["dollar_liquidity"], p["credit_stress"], p["odds_and_ends"]
    funding_str = f"{cl['btc_funding_apr']:+.1f}%"
    border = f"{oe['border_wait_m']}m" if oe["border_wait_m"] is not None else "closed / no data"
    rows = [
        ("market_volatility", "Market Volatility", "S&P 500 VIX + Treasury MOVE Index",
         f"VIX: {mv['vix']} | MOVE: {mv['move_index']}"),
        ("crypto_leverage", "Crypto Leverage", "Hyperliquid BTC funding + Deribit DVOL",
         f"Funding: {funding_str} APR | DVOL: {cl['dvol_index']}%"),
        ("short_volume", "Short Volume", "FINRA Reg SHO daily file (SPY)",
         f"Short ratio: {sv['spy_short_volume_ratio']}% ({sv['report_date']})"),
        ("dollar_liquidity", "Dollar Liquidity", "U.S. TGA cash + NY Fed swap lines",
         f"TGA: ${dl['tga_billions']}B | Swaps: ${dl['swaps_billions']}B"),
        ("credit_stress", "Credit Stress", "SEC 8-K filings mentioning Item 2.04 (14 days)",
         f"Filings: {cs['sec_8k_filings']}"),
        ("odds_and_ends", "Odds and Ends", "Wikipedia crisis traffic (6%) + CBP Laredo truck waits (4%)",
         f"Wiki Z: +{oe['wiki_z']}σ | Border: {border}"),
    ]
    return [(key, title, feed, values, p[key]["score"], fb_tag(key, p[key]))
            for key, title, feed, values in rows]


def blank_if(pillar, flag, field):
    """Value for the history CSV, empty when that feed was on fallback data."""
    value = pillar[field]
    return "" if pillar.get(flag) or value is None else value


def write_history(data):
    """Append raw values to history.csv for later calibration. Values that came
    from fallback defaults are left empty so they don't pollute the history."""
    p = data["pillars"]
    mv, cl, sv = p["market_volatility"], p["crypto_leverage"], p["short_volume"]
    dl, cs, oe = p["dollar_liquidity"], p["credit_stress"], p["odds_and_ends"]
    row = [
        data["timestamp"], data["composite_score"],
        blank_if(mv, "fallback", "vix"), blank_if(mv, "fallback", "move_index"),
        blank_if(cl, "hl_fallback", "btc_funding_apr"), blank_if(cl, "dvol_fallback", "dvol_index"),
        blank_if(sv, "fallback", "spy_short_volume_ratio"),
        blank_if(dl, "tga_fallback", "tga_billions"), blank_if(dl, "tga_fallback", "tga_5d_flow"),
        blank_if(dl, "swaps_fallback", "swaps_billions"),
        blank_if(cs, "fallback", "sec_8k_filings"),
        blank_if(oe, "wiki_fallback", "wiki_z"), blank_if(oe, "cbp_fallback", "border_wait_m"),
    ]
    is_new = not os.path.exists(HISTORY_FILE)
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(HISTORY_HEADER)
        writer.writerow(row)


def render_text(data, rows):
    t = data["tactical_posture"]
    lines = [
        "",
        "=" * 70,
        f" OPEN MARKET WEATHER OBSERVATORY // HYBRID MACRO & CRYPTO // v{data['version']}",
        f" {data['timestamp']} // STANDALONE HEURISTIC // PERIODIC RUN",
        "=" * 70,
        "",
        f" OVERALL STATUS : {data['status']} [Score: {data['composite_score']}/100]",
        f" CURRENT REGIME : {data['desc']}",
        "",
        " --- TACTICAL POSTURE (SUGGESTIONS FOR TRADING BOTS) ---",
    ]
    for label, key in (("GRID BOTS", "grid_bots"), ("DIP BUYING", "dip_buying"),
                       ("CRYPTO PERPS", "crypto_perps"), ("SHORT VOLUME", "dark_pool"),
                       ("COLLATERAL", "collateral")):
        lines.append(f" [*] {label:<13}: {t[key]['status']} -> {t[key]['action']}")
    lines += ["", " --- 6 PILLARS ---"]
    for i, (key, title, feed, values, score, fb) in enumerate(rows, 1):
        tag = f" [{fb}]" if fb else ""
        lines.append(f" [{i}] {title:<18}: Score {score}/100 ({values}){tag}")
    lines += ["", f" API: curl -sL {BASE_URL}/weather.json", "=" * 70, ""]
    return "\n".join(lines)


def render_badge(data):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="160" height="20">
    <mask id="a"><rect width="160" height="20" rx="3" fill="#fff"/></mask>
    <g mask="url(#a)">
        <path fill="#222" d="M0 0h95v20H0z"/>
        <path fill="{data['color']}" d="M95 0h65v20H95z"/>
    </g>
    <g fill="#fff" text-anchor="middle" font-family="monospace" font-size="11">
        <text x="47" y="14">MarketWeather</text>
        <text x="127" y="14" fill="#000" font-weight="bold">{data['composite_score']}/100</text>
    </g>
</svg>"""


HTML_CSS = """
        * { box-sizing: border-box; }
        body {
            background: #090b0e;
            color: #d1d5db;
            font-family: 'SF Mono', Consolas, 'Liberation Mono', Menlo, monospace;
            padding: 1.5rem 1rem;
            max-width: 920px;
            margin: auto;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }
        .header { border-bottom: 1px dashed #2d3748; padding-bottom: 1rem; margin-bottom: 1.5rem; }
        .header-links { margin-top: 0.8rem; font-size: 0.9rem; word-break: break-all; }
        .badge-sub { color: #718096; font-size: 0.8rem; }
        .status-box { border: 2px solid __COLOR__; background: #111419; padding: 1.5rem 1rem; margin-bottom: 2rem; text-align: center; border-radius: 4px; }
        .status-symbol { font-size: 3.8rem; line-height: 1; margin-bottom: 0.6rem; display: block; }
        .status-title { font-size: 1.5rem; color: __COLOR__; margin: 0 0 0.5rem 0; font-weight: bold; }
        .status-desc { color: #9ca3af; font-size: 0.95rem; max-width: 650px; margin: auto; }
        .posture-card { border: 1px solid #2d3748; background: #0d1117; padding: 1.25rem; margin-bottom: 2rem; border-radius: 4px; }
        .posture-title { font-size: 0.9rem; font-weight: bold; color: #e2e8f0; text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px dashed #2d3748; padding-bottom: 0.5rem; margin-bottom: 0.75rem; }
        .posture-item { display: flex; justify-content: space-between; align-items: baseline; padding: 0.5rem 0; border-bottom: 1px solid #161b22; font-size: 0.9rem; }
        .posture-item:last-child { border-bottom: none; }
        .posture-label { font-weight: bold; color: #a0aec0; width: 140px; flex-shrink: 0; }
        .posture-status { font-weight: bold; width: 150px; flex-shrink: 0; }
        .posture-action { color: #cbd5e0; flex: 1; text-align: right; }
        .table-container { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-top: 1rem; border: 1px solid #1a202c; border-radius: 4px; }
        .table { width: 100%; border-collapse: collapse; min-width: 640px; }
        .table td, .table th { padding: 0.75rem 0.6rem; text-align: left; border-bottom: 1px solid #1a202c; }
        .table th { color: #718096; font-size: 0.8rem; text-transform: uppercase; background: #0d1117; }
        a { color: #63b3ed; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .footer { margin-top: 2.5rem; border-top: 1px dashed #2d3748; padding-top: 1rem; font-size: 0.8rem; color: #718096; }
        .score-pill { font-weight: bold; padding: 2px 8px; border-radius: 3px; background: #1a202c; white-space: nowrap; }
        .tag-fallback { color: #f59e0b; font-size: 0.75rem; margin-left: 6px; font-weight: normal; }
        code { background: #1a202c; padding: 2px 6px; border-radius: 3px; color: #e2e8f0; }
        @media (max-width: 640px) {
            body { padding: 1rem 0.75rem; }
            .posture-item { flex-direction: column; align-items: flex-start; gap: 4px; padding: 0.6rem 0; }
            .posture-label, .posture-status { width: 100%; }
            .posture-action { text-align: left; font-size: 0.85rem; color: #a0aec0; }
        }
"""


def fb_html(fb):
    return f'<span class="tag-fallback">[{html_lib.escape(fb)}]</span>' if fb else ""


def render_html(data, rows):
    esc = html_lib.escape
    t = data["tactical_posture"]
    score, symbol, status = data["composite_score"], data["symbol"], esc(data["status"])
    timestamp, desc = data["timestamp"], esc(data["desc"])
    css = HTML_CSS.replace("__COLOR__", data["color"])

    posture_html = "".join(
        f"""
        <div class="posture-item">
            <span class="posture-label">{label}</span>
            <span class="posture-status" style="color: {t[key]['color']}">{esc(t[key]['status'])}</span>
            <span class="posture-action">{esc(t[key]['action'])}</span>
        </div>"""
        for label, key in (("GRID BOTS", "grid_bots"), ("DIP BUYING", "dip_buying"),
                           ("CRYPTO PERPS", "crypto_perps"), ("SHORT VOLUME", "dark_pool"),
                           ("COLLATERAL", "collateral"))
    )
    rows_html = "".join(
        f"""
                <tr>
                    <td><strong>{i}. {esc(title)}</strong></td>
                    <td>{esc(feed)}</td>
                    <td>{esc(values)}{fb_html(fb)}</td>
                    <td><span class="score-pill">{pscore}/100</span></td>
                </tr>"""
        for i, (key, title, feed, values, pscore, fb) in enumerate(rows, 1)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
    <title>Market Weather ({score}/100)</title>
    <meta name="description" content="A weather report for the markets, based on public macro and crypto data feeds.">
    <link rel="icon" href="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%20100%20100'%3E%3Ctext%20y='.9em'%20font-size='90'%3E{symbol}%3C/text%3E%3C/svg%3E">
    <style>{css}</style>
</head>
<body>
    <div class="header">
        <strong>OPEN MARKET WEATHER OBSERVATORY</strong><br>
        <span class="badge-sub">TIMESTAMP: {timestamp} // PERIODIC RUN // v{data['version']}</span>
        <div class="header-links">
            <a href="weather.json">[Raw JSON API]</a> &nbsp;|&nbsp;
            <a href="weather.txt">[Plaintext for cURL]</a> &nbsp;|&nbsp;
            <a href="badge.svg">[Live SVG Badge]</a>
        </div>
    </div>

    <div class="status-box">
        <span class="status-symbol">{symbol}</span>
        <div class="status-title">{status} (SCORE: {score}/100)</div>
        <div class="status-desc">{desc}</div>
    </div>

    <div class="posture-card">
        <div class="posture-title">Tactical Posture // Suggestions for Trading Bots</div>{posture_html}
    </div>

    <h3>THE 6 PILLARS</h3>
    <div class="table-container">
        <table class="table">
            <thead>
                <tr><th>Pillar</th><th>Underlying Feed</th><th>Live Values</th><th>Friction Score</th></tr>
            </thead>
            <tbody>{rows_html}
            </tbody>
        </table>
    </div>

    <div class="footer">
        Open market metrics. Built with Python stdlib on Cloudflare and GitHub Actions. No financial advice.<br>
        CLI access: <code>curl -sL {BASE_URL}/weather.txt</code>
    </div>
</body>
</html>
"""


def export_files(data):
    rows = pillar_rows(data["pillars"])

    with open("weather.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    write_history(data)
    with open("weather.txt", "w", encoding="utf-8") as f:
        f.write(render_text(data, rows))
    with open("badge.svg", "w", encoding="utf-8") as f:
        f.write(render_badge(data))
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(render_html(data, rows))


if __name__ == "__main__":
    print(f"[*] Running Market Weather Engine v{VERSION}...")
    w = calculate_systemic_weather()
    export_files(w)
    print(f"[+] Complete: Score is {w['composite_score']}/100 -> {w['status']}")
