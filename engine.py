#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OPEN MARKET WEATHER OBSERVATORY // HYBRID MACRO & CRYPTO
Version: 3.6.3 (stdlib only)

Changes in 3.6.3:
  - Wikipedia: the series is aligned by calendar day (days without views count as
    zero) instead of by list position, and articles with too little traffic for a
    meaningful z-score are skipped with a log line.
  - Cold start: when no recent state exists, the assumed status (OMW_COLD_START_STATUS)
    now also decides which threshold band applies, not only the confirmation count.
  - Return-band text names every condition that holds the status back.
  - data_quality: fallback_count counts only fallback feeds, stale feeds have their
    own stale_count.

Optional environment variables:
  OMW_CONTACT                  Contact string for the User-Agent sent to SEC EDGAR and
                               Wikimedia. Both ask for a real contact, ideally an e-mail.
  OMW_BASE_URL                 Public URL of your deployment. Used to read the previous
                               state when there is no recent local weather.json.
  OMW_REPO_URL                 Direct link to the public GitHub repository.
  OMW_VALID_FOR_HOURS          How long a result is valid (default 2.5).
  OMW_STATE_MAX_AGE_HOURS      Previous state older than this is ignored (default 4).
  OMW_RECOVERY_CONFIRMATIONS   Consecutive runs needed to step the grid status down
                               (default 2, minimum 1).
  OMW_COLD_START_STATUS        Grid status assumed when no recent state exists
                               (ACTIVE, CAUTION or PAUSED; default CAUTION).
"""

import csv
import html as html_lib
import json
import math
import os
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


# ==============================================================================
# LOGGING AND CONFIG
# ==============================================================================
def utc_now():
    return datetime.now(timezone.utc)


def iso_utc(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def log(level, source, message):
    print(f"[{iso_utc(utc_now())}] [{level}] [{source}] {message}", flush=True)


def env_number(name, default, cast=float, minimum=None):
    """Read a number from the environment. Bad values fall back to the default."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = cast(raw)
    except ValueError:
        log("WARN", "CONFIG", f"{name}={raw!r} is not a valid number, using {default}")
        return default
    if minimum is not None and value < minimum:
        log("WARN", "CONFIG", f"{name}={raw!r} is below {minimum}, using {minimum}")
        return minimum
    return value


VERSION = "3.6.3"
SCHEMA_VERSION = 1
BASE_URL = os.environ.get(
    "OMW_BASE_URL", "https://open-market-weather.hartmut-nese.workers.dev"
).rstrip("/")
REPO_URL = os.environ.get(
    "OMW_REPO_URL", "https://github.com/hartmutnese-stack/open-market-weather"
)
CONTACT = os.environ.get("OMW_CONTACT", "admin@marktwetter.org")
VALID_FOR_HOURS = env_number("OMW_VALID_FOR_HOURS", 2.5, float, 0.1)
STATE_MAX_AGE_HOURS = env_number("OMW_STATE_MAX_AGE_HOURS", 4.0, float, 0.1)
RECOVERY_CONFIRMATIONS = env_number("OMW_RECOVERY_CONFIRMATIONS", 2, int, 1)
MAX_JSON_BYTES = 5_000_000

# Market feeds get a browser UA (some of them block unknown clients).
# SEC EDGAR and Wikimedia ask for an identified client with a real contact.
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

# Grid bot thresholds. All comparisons are >= for "hot" and < for "calm".
PAUSE_ENTER = 65.0   # composite or crypto score at/above this -> PAUSED
PAUSE_STAY = 58.0    # once PAUSED, stay until both are below this
CALM_ENTER = {"composite": 35.0, "vix": 20.0, "crypto": 40.0}
CALM_RETURN = {"composite": 28.0, "vix": 18.5, "crypto": 35.0}

GRID_SEVERITY = {"ACTIVE": 0, "CAUTION": 1, "PAUSED": 2}
GRID_COLORS = {"ACTIVE": "#00ff66", "CAUTION": "#ffcc00", "PAUSED": "#ff0033"}
_cold = os.environ.get("OMW_COLD_START_STATUS", "CAUTION").strip().upper()
COLD_START_STATUS = _cold if _cold in GRID_SEVERITY else "CAUTION"

# A feed whose newest data point is older than this (days) counts as STALE.
MAX_AGE_DAYS = {"yahoo": 5, "finra": 4, "tga": 6}

# Wikipedia: below this average of daily views a z-score is mostly noise.
WIKI_MIN_BASELINE_AVG = 20.0

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

# Old pillar names, still written to the JSON for existing consumers.
LEGACY_KEYS = {
    "market_implied": "market_volatility",
    "crypto_247": "crypto_leverage",
    "dark_pool_finra": "short_volume",
    "liquidity_plumbing": "dollar_liquidity",
    "credit_statutory": "credit_stress",
    "cognitive_physical": "odds_and_ends",
}

FALLBACK_PARTS = {
    "market_volatility": [("fallback", "yahoo")],
    "crypto_leverage": [("hl_fallback", "hyperliquid"), ("dvol_fallback", "deribit")],
    "short_volume": [("fallback", "finra")],
    "dollar_liquidity": [("tga_fallback", "tga"), ("swaps_fallback", "ny_fed")],
    "credit_stress": [("fallback", "sec")],
    "odds_and_ends": [("wiki_fallback", "wikipedia"), ("cbp_fallback", "cbp")],
}

QUALITY_PENALTIES = {
    "yahoo": 25, "hyperliquid": 25, "deribit": 25,
    "tga": 15, "ny_fed": 15, "finra": 10, "sec": 10,
    "wikipedia": 5, "cbp": 5,
}


# ==============================================================================
# HELPERS
# ==============================================================================
def clamp(value, lo=0, hi=100):
    return max(lo, min(hi, value))


def to_float(x):
    """float(x) or None. Accepts numbers and strings like '1,234.5'."""
    if x is None or isinstance(x, bool):
        return None
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, TypeError):
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


def parse_date(value):
    """'YYYY-MM-DD' -> date, or None."""
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


@dataclass
class FetchResult:
    data: object = None
    ok: bool = False
    status_code: Optional[int] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None


def fetch_json(url, source, timeout=10, headers=None, data=None, retries=1):
    """GET (or POST with data) and parse JSON. Always returns a FetchResult."""
    req_headers = headers or DEFAULT_HEADERS
    last = FetchResult(error_type="UNKNOWN")
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                raw = response.read(MAX_JSON_BYTES + 1)
                if len(raw) > MAX_JSON_BYTES:
                    last = FetchResult(status_code=status, error_type="RESPONSE_TOO_LARGE",
                                       error_message="JSON response exceeds limit")
                else:
                    try:
                        return FetchResult(data=json.loads(raw.decode("utf-8")), ok=True,
                                           status_code=status)
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        last = FetchResult(status_code=status, error_type="INVALID_JSON",
                                           error_message=str(exc))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                err = "HTTP_429"
            elif exc.code >= 500:
                err = "HTTP_5XX"
            else:
                err = f"HTTP_{exc.code}"
            last = FetchResult(status_code=exc.code, error_type=err, error_message=str(exc))
            if exc.code < 500 and exc.code != 429:
                break
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            err = "TIMEOUT" if "timed out" in str(reason).lower() else "NETWORK_ERROR"
            last = FetchResult(error_type=err, error_message=str(reason))
        except TimeoutError as exc:
            last = FetchResult(error_type="TIMEOUT", error_message=str(exc))
        except Exception as exc:
            last = FetchResult(error_type="NETWORK_ERROR", error_message=str(exc))
        if attempt < retries:
            time.sleep(1.5 * (2 ** attempt))
    log("WARN", source, f"{last.error_type}: {last.error_message or 'request failed'}")
    return last


def health(status="OK", error_type=None, detail=None):
    """One feed_health entry. status: OK | FALLBACK | STALE | CLOSED."""
    item = {"status": status}
    if error_type:
        item["error_type"] = error_type
    if detail:
        item["detail"] = detail
    return item


# ==============================================================================
# PILLAR 1: MARKET VOLATILITY (VIX & MOVE)
# ==============================================================================
def yahoo_last_price(ticker):
    """Returns (price, error_type, age_in_days). price is None on any problem."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
    result = fetch_json(url, "YAHOO")
    if not result.ok:
        return None, result.error_type, None
    meta = dig(result.data, "chart", "result", 0, "meta")
    price = to_float(dig(meta, "regularMarketPrice"))
    if price is None:
        log("WARN", "YAHOO", f"{ticker}: response has no regularMarketPrice")
        return None, "INVALID_RESPONSE", None
    quote_ts = to_float(dig(meta, "regularMarketTime"))
    age = (utc_now().timestamp() - quote_ts) / 86400.0 if quote_ts else None
    return price, None, age


def get_market_volatility(feed_health):
    vix, vix_err, vix_age = yahoo_last_price("%5EVIX")
    move, move_err, move_age = yahoo_last_price("%5EMOVE")
    fallback = vix is None or move is None
    if vix is None:
        vix = 16.5
    if move is None:
        move = 95.0

    ages = [a for a in (vix_age, move_age) if a is not None]
    oldest = max(ages) if ages else None
    if fallback:
        feed_health["yahoo"] = health("FALLBACK", vix_err or move_err)
    elif oldest is not None and oldest > MAX_AGE_DAYS["yahoo"]:
        feed_health["yahoo"] = health("STALE", None, f"oldest quote is {oldest:.1f} days old")
    else:
        feed_health["yahoo"] = health("OK")

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
    """Stress from the deviation to the baseline. Continuous (no cliffs)."""
    dev = apr - FUNDING_BASELINE_APR
    limit, steep = (14.0, 3.0) if dev >= 0 else (18.0, 3.5)
    d = abs(dev)
    return clamp(int(8 + min(d, limit) * 1.2 + max(0.0, d - limit) * steep))


def get_crypto_leverage(feed_health):
    funding_apr, oi_mil, dvol = FUNDING_BASELINE_APR, 0.0, 52.0
    hl_fallback = dvol_fallback = True

    payload = json.dumps({"type": "metaAndAssetCtxs"}).encode("utf-8")
    hr = fetch_json(
        "https://api.hyperliquid.xyz/info", "HYPERLIQUID", timeout=6,
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        data=payload,
    )
    hl_error = hr.error_type
    if hr.ok:
        try:
            universe, ctxs = hr.data[0]["universe"], hr.data[1]
            idx = next(i for i, c in enumerate(universe) if c.get("name") == "BTC")
            ctx = ctxs[idx]
            funding_apr = round(float(ctx["funding"]) * 24 * 365 * 100, 1)
            oi_mil = round(float(ctx["openInterest"]) * float(ctx["oraclePx"]) / 1_000_000, 1)
            hl_fallback, hl_error = False, None
        except (TypeError, KeyError, IndexError, StopIteration, ValueError, AttributeError):
            hl_error = "INVALID_RESPONSE"
            log("WARN", "HYPERLIQUID", "response not usable, using fallback funding")
    feed_health["hyperliquid"] = health("FALLBACK" if hl_fallback else "OK", hl_error)

    dr = fetch_json(
        "https://www.deribit.com/api/v2/public/get_index_price?index_name=btcdvol_usdc",
        "DERIBIT", timeout=6,
    )
    value = to_float(dig(dr.data, "result", "index_price")) if dr.ok else None
    dvol_error = dr.error_type
    if value is not None:
        dvol, dvol_fallback, dvol_error = round(value, 1), False, None
    elif dr.ok:
        dvol_error = "INVALID_RESPONSE"
        log("WARN", "DERIBIT", "response has no index_price, using fallback DVOL")
    feed_health["deribit"] = health("FALLBACK" if dvol_fallback else "OK", dvol_error)

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
                    try:
                        short_vol, total_vol = float(parts[2]), float(parts[4])
                    except ValueError:
                        continue
                    if total_vol > 0:
                        return round(short_vol / total_vol * 100, 1), "OK"
        return None, "MISSING"
    except urllib.error.HTTPError as exc:
        return None, ("MISSING" if exc.code in (403, 404) else "ERROR")
    except Exception:
        return None, "ERROR"


def get_short_volume(feed_health):
    today = utc_now()
    consecutive_errors = 0
    for i in range(7):
        day = today - timedelta(days=i)
        date_str = day.strftime("%Y%m%d")
        ratio, state = finra_spy_ratio(date_str)
        if state == "ERROR":
            consecutive_errors += 1
            if consecutive_errors >= 2:
                break
            continue
        consecutive_errors = 0
        if ratio is not None:
            age = i
            if age > MAX_AGE_DAYS["finra"]:
                feed_health["finra"] = health("STALE", None, f"newest file is {age} days old")
            else:
                feed_health["finra"] = health("OK")
            return {
                "score": short_volume_score(ratio),
                "spy_short_volume_ratio": ratio,
                "report_date": date_str,
                "fallback": False,
            }
    error = "NETWORK_ERROR" if consecutive_errors >= 2 else "NO_RECENT_FILE"
    log("WARN", "FINRA", f"{error}: no usable Reg SHO file, using fallback ratio")
    feed_health["finra"] = health("FALLBACK", error)
    return {
        "score": short_volume_score(49.0),
        "spy_short_volume_ratio": 49.0,
        "report_date": "Fallback",
        "fallback": True,
    }


# ==============================================================================
# PILLAR 4: DOLLAR LIQUIDITY (TREASURY GENERAL ACCOUNT & NY FED SWAP LINES)
# ==============================================================================
def get_dollar_liquidity(feed_health):
    tga_url = (
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/"
        "operating_cash_balance?filter=account_type:eq:Treasury%20General%20Account%20(TGA)"
        "%20Closing%20Balance&sort=-record_date&page%5Bsize%5D=10"
    )
    tr = fetch_json(tga_url, "TGA")
    rows = dig(tr.data, "data", default=[]) if tr.ok else []
    if not isinstance(rows, list):
        rows = []
    values = []
    latest_date = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        val = to_float(row.get("open_today_bal"))
        if val is None:
            val = to_float(row.get("close_today_bal"))
        if val is None:
            continue
        if not values:
            latest_date = parse_date(row.get("record_date"))
        values.append(val)

    tga_bal, tga_change, tga_score, tga_fallback = 850.0, 0.0, 15, True
    if len(values) >= 2:
        latest, prev = values[0], values[min(4, len(values) - 1)]
        tga_bal = latest / 1000.0                    # millions -> billions
        tga_change = (latest - prev) / 1000.0
        tga_score = clamp(int(abs(tga_change) * 1.5))
        tga_fallback = False

    if tga_fallback:
        feed_health["tga"] = health("FALLBACK", tr.error_type or "INVALID_RESPONSE")
    else:
        age = (utc_now().date() - latest_date).days if latest_date else None
        if age is not None and age > MAX_AGE_DAYS["tga"]:
            feed_health["tga"] = health("STALE", None, f"latest record is {age} days old")
        else:
            feed_health["tga"] = health("OK")

    sr = fetch_json("https://markets.newyorkfed.org/api/fxs/all/latest.json", "NY_FED")
    operations = find_list(sr.data, "operations") if sr.ok else None
    swap_b, swaps_fallback = 0.0, True
    if operations is not None:
        swaps_fallback = False
        for op in operations:
            amount = to_float(op.get("amount")) if isinstance(op, dict) else None
            if amount is not None:
                swap_b += amount / 1_000_000_000.0   # assumes USD
    feed_health["ny_fed"] = health(
        "FALLBACK" if swaps_fallback else "OK",
        (sr.error_type or "INVALID_RESPONSE") if swaps_fallback else None,
    )

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


def get_credit_stress(feed_health):
    today = utc_now()
    start = (today - timedelta(days=14)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    url = (
        "https://efts.sec.gov/LATEST/search-index?q=%22Item+2.04%22&forms=8-K"
        f"&dateRange=custom&startdt={start}&enddt={end}"
    )
    result = fetch_json(url, "SEC", timeout=8, headers=COMPLIANT_HEADERS)
    total = dig(result.data, "hits", "total") if result.ok else None
    if isinstance(total, dict):
        total = total.get("value")
    valid = isinstance(total, int) and not isinstance(total, bool)
    count = total if valid else 11
    feed_health["sec"] = health(
        "OK" if valid else "FALLBACK",
        None if valid else (result.error_type or "INVALID_RESPONSE"),
    )
    return {
        "score": credit_score_from_count(count),
        "sec_8k_filings": count,
        "fallback": not valid,
    }


# ==============================================================================
# PILLAR 6: ODDS AND ENDS (WIKIPEDIA CRISIS TRAFFIC 6% & CBP LAREDO TRUCKS 4%)
# ==============================================================================
WIKI_ARTICLES = [
    "Bank_run", "Credit_default_swap", "Circuit_breaker_(stock_market)",
    "Force_majeure", "Bail-in", "Insolvency",
]


def wikipedia_zscore(article, start, end):
    """Mean of the last 7 days against the 3+ weeks before. `start` and `end` are
    dates. The series is built per calendar day: the API leaves out days it has no
    views for, and those days count as zero. Aligning by list position instead
    would shift the 7-day window whenever a day is missing."""
    url = (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/"
        f"all-access/user/{article}/daily/{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}"
    )
    result = fetch_json(url, "WIKIPEDIA", timeout=5, headers=COMPLIANT_HEADERS)
    if not result.ok:
        log("WARN", "WIKIPEDIA", f"{article}: fetch failed ({result.error_type})")
        return None
    items = dig(result.data, "items")
    if not isinstance(items, list) or not items:
        log("WARN", "WIKIPEDIA", f"{article}: response has no observations")
        return None

    by_day = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        stamp = str(item.get("timestamp", ""))[:8]
        views = to_float(item.get("views"))
        if len(stamp) == 8 and views is not None:
            by_day[stamp] = views
    n_days = (end - start).days + 1
    series = [by_day.get((start + timedelta(days=i)).strftime("%Y%m%d"), 0.0)
              for i in range(n_days)]
    if len(series) < 21:
        log("WARN", "WIKIPEDIA", f"{article}: window has only {len(series)} days (needs 21)")
        return None

    baseline, recent = series[:-7], series[-7:]
    avg_base = sum(baseline) / len(baseline)
    if avg_base < WIKI_MIN_BASELINE_AVG:
        log("WARN", "WIKIPEDIA",
            f"{article}: low traffic ({avg_base:.1f} views/day, {len(items)}/{n_days} days "
            f"with data), skipped")
        return None
    std_base = math.sqrt(sum((x - avg_base) ** 2 for x in baseline) / len(baseline)) or 1
    return max(0.0, (sum(recent) / len(recent) - avg_base) / std_base)


def laredo_truck_wait():
    result = fetch_json("https://bwt.cbp.gov/api/bwtpublicmod", "CBP", timeout=8)
    data = result.data if result.ok else None
    if not isinstance(data, list):
        return None, False, (result.error_type or "INVALID_RESPONSE")
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
    error = None if found_laredo else "NO_LAREDO_ENTRY"
    return (max(delays) if delays else None), found_laredo, error


def get_odds_and_ends(feed_health):
    today = utc_now()
    end = (today - timedelta(days=2)).date()      # latency buffer
    start = (today - timedelta(days=32)).date()

    zscores = []
    for article in WIKI_ARTICLES:
        z = wikipedia_zscore(article, start, end)
        if z is not None:
            zscores.append(z)
    wiki_fallback = not zscores
    avg_z = sum(zscores) / len(zscores) if zscores else 0.0
    if wiki_fallback:
        feed_health["wikipedia"] = health("FALLBACK", "INSUFFICIENT_DATA")
    else:
        detail = None
        if len(zscores) < len(WIKI_ARTICLES):
            detail = f"{len(zscores)}/{len(WIKI_ARTICLES)} articles usable"
        feed_health["wikipedia"] = health("OK", None, detail)
    wiki_score = clamp(int(avg_z * 25))

    wait, cbp_ok, cbp_error = laredo_truck_wait()
    cbp_fallback = not cbp_ok
    phys_score = clamp(int((wait - 15) * (100 / 105))) if wait is not None else 0
    if cbp_fallback:
        feed_health["cbp"] = health("FALLBACK", cbp_error)
        border_state = "UNKNOWN"
    elif wait is None:
        feed_health["cbp"] = health("CLOSED", None, "Laredo feed reachable; no delay value")
        border_state = "CLOSED"
    else:
        feed_health["cbp"] = health("OK")
        border_state = "OBSERVED"

    return {
        "score": int(wiki_score * 0.6 + phys_score * 0.4),
        "wiki_z": round(avg_z, 2),
        "wiki_articles_ok": len(zscores),
        "border_wait_m": wait,
        "border_state": border_state,
        "fallback": wiki_fallback or cbp_fallback,
        "wiki_fallback": wiki_fallback,
        "cbp_fallback": cbp_fallback,
    }


# ==============================================================================
# PREVIOUS STATE (for hysteresis)
# ==============================================================================
def parse_ts(value):
    """Accepts '2026-01-01T12:00:00Z' and '2026-01-01 12:00 UTC'."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        pass
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def read_local_state():
    try:
        with open("weather.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def previous_state():
    """The last run's weather.json (local file first, then the live site)."""
    loaders = (
        read_local_state,
        lambda: fetch_json(f"{BASE_URL}/weather.json", "PREVIOUS_STATE", timeout=6, retries=0).data,
    )
    for load in loaders:
        try:
            prev = load()
        except Exception:
            prev = None
        ts = parse_ts(dig(prev, "generated_at") or dig(prev, "timestamp"))
        if ts and utc_now() - ts <= timedelta(hours=STATE_MAX_AGE_HOURS):
            return prev
    return None


def previous_grid_status(prev):
    status = dig(prev, "tactical_posture", "grid_bots", "status")
    return status if isinstance(status, str) and status in GRID_SEVERITY else None


# ==============================================================================
# DATA QUALITY
# ==============================================================================
def data_quality(feed_health):
    score = 100
    fallback, stale = [], []
    for name, item in feed_health.items():
        penalty = QUALITY_PENALTIES.get(name, 5)
        if item["status"] == "FALLBACK":
            score -= penalty
            fallback.append(name)
        elif item["status"] == "STALE":
            score -= max(1, penalty // 2)
            stale.append(name)
    score = clamp(score)
    status = "HIGH" if score >= 90 else ("MEDIUM" if score >= 70 else "LOW")
    degraded = [n for n in feed_health if n in fallback or n in stale]
    return {"status": status, "score": score, "fallback_count": len(fallback),
            "stale_count": len(stale), "degraded_feeds": degraded}


# ==============================================================================
# GRID STATUS (level bands + run-count confirmation)
# ==============================================================================
def raw_grid_candidate(composite, p, clean, band_status):
    """What the grid status would be without confirmation delay.
    band_status decides which threshold band applies."""
    vix = p["market_volatility"]["vix"]
    crypto = p["crypto_leverage"]["score"]
    pause_limit = PAUSE_STAY if band_status == "PAUSED" else PAUSE_ENTER
    if crypto >= pause_limit or composite >= pause_limit:
        return "PAUSED"
    band = CALM_RETURN if band_status in ("CAUTION", "PAUSED") else CALM_ENTER
    calm = composite < band["composite"] and vix < band["vix"] and crypto < band["crypto"]
    return "ACTIVE" if calm and clean else "CAUTION"


def resolve_grid_status(candidate, prev_status, prev_transition):
    """Apply confirmation to a raw candidate. Returns (status, transition)."""
    cold_start = prev_status is None
    previous = prev_status or COLD_START_STATUS
    required = RECOVERY_CONFIRMATIONS
    base = {
        "previous_status": previous,
        "candidate_status": candidate,
        "required_runs": required,
        "cold_start": cold_start,
    }
    cand_sev, prev_sev = GRID_SEVERITY[candidate], GRID_SEVERITY[previous]

    if cand_sev >= prev_sev:
        return candidate, {**base, "confirmed_runs": 0, "recovering": False,
                           "recovery_target": None, "status_changed": candidate != previous}

    streak, target = 0, candidate
    old = prev_transition if isinstance(prev_transition, dict) else {}
    if old.get("recovering") and old.get("previous_status") == previous:
        streak = int(to_float(old.get("confirmed_runs")) or 0)
        old_target = old.get("recovery_target")
        if isinstance(old_target, str) and old_target in GRID_SEVERITY \
                and GRID_SEVERITY[old_target] > GRID_SEVERITY[target]:
            target = old_target
    streak += 1

    if streak >= required:
        done = streak if target == candidate else 0
        return target, {**base, "confirmed_runs": done, "recovering": False,
                        "recovery_target": None, "status_changed": True}
    return previous, {**base, "confirmed_runs": streak, "recovering": True,
                      "recovery_target": target, "status_changed": False}


def return_band_blockers(composite, vix, crypto_score):
    """Conditions that keep the status out of ACTIVE under the stricter return band."""
    blockers = []
    if composite >= CALM_RETURN["composite"]:
        blockers.append(f"overall {composite:.1f} >= {CALM_RETURN['composite']:g}")
    if vix >= CALM_RETURN["vix"]:
        blockers.append(f"VIX {vix:.2f} >= {CALM_RETURN['vix']:g}")
    if crypto_score >= CALM_RETURN["crypto"]:
        blockers.append(f"crypto {crypto_score} >= {CALM_RETURN['crypto']:g}")
    return blockers


# ==============================================================================
# TACTICAL POSTURE
# ==============================================================================
def generate_tactical_posture(composite, p, quality, prev):
    vix = p["market_volatility"]["vix"]
    crypto_score = p["crypto_leverage"]["score"]
    funding = p["crypto_leverage"]["btc_funding_apr"]
    svr = p["short_volume"]["spy_short_volume_ratio"]
    swaps = p["dollar_liquidity"]["swaps_billions"]
    clean = quality["status"] == "HIGH" and not quality["degraded_feeds"]
    posture = {}

    # 1. Grid bots
    prev_status = previous_grid_status(prev)
    prev_transition = dig(prev, "transition", default={})
    # Without a recent state the assumed cold-start status also picks the band.
    band_status = prev_status or COLD_START_STATUS

    calm_enter = composite < CALM_ENTER["composite"] and vix < CALM_ENTER["vix"] and crypto_score < CALM_ENTER["crypto"]
    calm_return = composite < CALM_RETURN["composite"] and vix < CALM_RETURN["vix"] and crypto_score < CALM_RETURN["crypto"]
    band_held_calm = band_status in ("CAUTION", "PAUSED") and calm_enter and not calm_return

    hot_enter = crypto_score >= PAUSE_ENTER or composite >= PAUSE_ENTER
    hot_stay = crypto_score >= PAUSE_STAY or composite >= PAUSE_STAY
    band_held_pause = band_status == "PAUSED" and not hot_enter and hot_stay

    candidate = raw_grid_candidate(composite, p, clean, band_status)
    grid_status, transition = resolve_grid_status(candidate, prev_status, prev_transition)
    streak_held = grid_status != candidate
    held = band_held_calm or band_held_pause or streak_held

    pending = f"{transition['confirmed_runs']}/{transition['required_runs']} confirmations"
    if transition["cold_start"]:
        pending += ", no recent previous state"

    if grid_status == "PAUSED" and streak_held:
        action = f"Staying paused: recovery pending ({pending})."
    elif grid_status == "PAUSED" and band_status == "PAUSED" and not hot_enter:
        action = f"Staying paused until the overall and crypto scores fall below {PAUSE_STAY:g}."
    elif grid_status == "PAUSED":
        action = (f"Pause new grid bids. Dislocation risk elevated "
                  f"(overall {composite:.1f}, crypto {crypto_score}).")
    elif grid_status == "ACTIVE":
        action = "Calm conditions. Standard grid parameters."
    elif band_held_calm:
        reasons = ", ".join(return_band_blockers(composite, vix, crypto_score))
        action = f"Widen grid bands by 15-25%. Return band active ({reasons})."
    elif streak_held:
        action = f"Widen grid bands by 15-25%. Recovery pending ({pending})."
    elif not clean:
        action = "Widen grid bands by 15-25%. Upstream data quality is degraded."
    else:
        action = "Widen grid bands by 15-25%. Reduce leverage / lot sizes."

    posture["grid_bots"] = {
        "status": grid_status, "color": GRID_COLORS[grid_status], "action": action,
        "hysteresis": held, "confirmed_runs": transition["confirmed_runs"],
    }

    # 2. Dip buying
    if composite < 45 and svr < 55.0 and crypto_score < 50 and clean:
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
        posture["collateral"] = {"status": "FRICTION DETECTED", "color": "#ff0033", "action": f"Central bank swap operations: ${swaps}B."}
    elif composite >= 50:
        posture["collateral"] = {"status": "WATCH", "color": "#ffcc00", "action": "Swap operations quiet, but overall market friction is elevated."}
    else:
        posture["collateral"] = {"status": "STABLE", "color": "#00ff66", "action": "No meaningful central bank swap operations."}

    return posture, transition


# ==============================================================================
# MAIN ENGINE
# ==============================================================================
def calculate_systemic_weather():
    started = utc_now()
    prev = previous_state()
    feed_health = {}

    pillars = {
        "market_volatility": get_market_volatility(feed_health),
        "crypto_leverage": get_crypto_leverage(feed_health),
        "short_volume": get_short_volume(feed_health),
        "dollar_liquidity": get_dollar_liquidity(feed_health),
        "credit_stress": get_credit_stress(feed_health),
        "odds_and_ends": get_odds_and_ends(feed_health),
    }
    composite = round(sum(pillars[k]["score"] * w for k, w in WEIGHTS.items()), 2)
    composite_score = int(math.floor(composite + 1e-9))
    fallback_flags = {k: v["fallback"] for k, v in pillars.items()}
    quality = data_quality(feed_health)

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

    tactical, transition = generate_tactical_posture(composite, pillars, quality, prev)

    for old_key, new_key in LEGACY_KEYS.items():
        pillars[old_key] = pillars[new_key]

    generated = utc_now()
    result = {
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "timestamp": generated.strftime("%Y-%m-%d %H:%M UTC"),
        "generated_at": iso_utc(generated),
        "valid_until": iso_utc(generated + timedelta(hours=VALID_FOR_HOURS)),
        "run_status": "COMPLETE" if not quality["degraded_feeds"] else "DEGRADED",
        "run_duration_seconds": round((generated - started).total_seconds(), 2),
        "symbol": symbol,
        "composite_score": composite_score,
        "composite_raw": composite,
        "display_score": composite_score,
        "status": status,
        "desc": desc,
        "color": color,
        "data_quality": quality,
        "fallback_flags": fallback_flags,
        "feed_health": feed_health,
        "transition": transition,
        "tactical_posture": tactical,
        "pillars": pillars,
    }
    log("INFO", "ENGINE",
        f"Composite={composite:.2f} Quality={quality['score']} "
        f"Degraded={','.join(quality['degraded_feeds']) or 'none'} "
        f"Grid={tactical['grid_bots']['status']}")
    return result


# ==============================================================================
# EXPORT
# ==============================================================================
def fb_tag(pillar_key, pillar, feed_health):
    """'fallback: tga, ny fed; stale: yahoo' or ''."""
    parts = FALLBACK_PARTS[pillar_key]
    fallback = [feed.replace("_", " ") for flag, feed in parts if pillar.get(flag)]
    stale = [feed.replace("_", " ") for _, feed in parts
             if dig(feed_health, feed, "status") == "STALE"]
    tags = []
    if fallback:
        tags.append(f"fallback: {', '.join(fallback)}")
    if stale:
        tags.append(f"stale: {', '.join(stale)}")
    return "; ".join(tags)


def pillar_rows(p, feed_health):
    mv, cl, sv = p["market_volatility"], p["crypto_leverage"], p["short_volume"]
    dl, cs, oe = p["dollar_liquidity"], p["credit_stress"], p["odds_and_ends"]
    funding_str = f"{cl['btc_funding_apr']:+.1f}%"
    if oe["border_wait_m"] is not None:
        border = f"{oe['border_wait_m']}m"
    elif oe.get("border_state") == "UNKNOWN":
        border = "unknown"
    else:
        border = "closed / no data"
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
    return [(key, title, feed, values, p[key]["score"], fb_tag(key, p[key], feed_health))
            for key, title, feed, values in rows]


def blank_if(pillar, flag, field):
    """Value for the history CSV, empty when that feed was on fallback data."""
    value = pillar[field]
    return "" if pillar.get(flag) or value is None else value


def history_row(data):
    p = data["pillars"]
    mv, cl, sv = p["market_volatility"], p["crypto_leverage"], p["short_volume"]
    dl, cs, oe = p["dollar_liquidity"], p["credit_stress"], p["odds_and_ends"]
    return [
        data["timestamp"], data["composite_raw"],
        blank_if(mv, "fallback", "vix"), blank_if(mv, "fallback", "move_index"),
        blank_if(cl, "hl_fallback", "btc_funding_apr"), blank_if(cl, "dvol_fallback", "dvol_index"),
        blank_if(sv, "fallback", "spy_short_volume_ratio"),
        blank_if(dl, "tga_fallback", "tga_billions"), blank_if(dl, "tga_fallback", "tga_5d_flow"),
        blank_if(dl, "swaps_fallback", "swaps_billions"),
        blank_if(cs, "fallback", "sec_8k_filings"),
        blank_if(oe, "wiki_fallback", "wiki_z"), blank_if(oe, "cbp_fallback", "border_wait_m"),
    ]


def append_history(data):
    """Append raw values to history.csv for later percentile calibration."""
    exists = os.path.exists(HISTORY_FILE) and os.path.getsize(HISTORY_FILE) > 0
    rows_before = 0
    if exists:
        with open(HISTORY_FILE, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            rows_before = sum(1 for _ in reader)
        if header != HISTORY_HEADER:
            log("WARN", "HISTORY", f"unexpected header in {HISTORY_FILE}, appending anyway")
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(HISTORY_HEADER)
        writer.writerow(history_row(data))
        f.flush()
        os.fsync(f.fileno())
    log("INFO", "HISTORY", f"loaded {rows_before} observations; appended observation {rows_before + 1}")


def render_text(data, rows):
    t = data["tactical_posture"]
    q = data["data_quality"]
    lines = [
        "",
        "=" * 70,
        f" OPEN MARKET WEATHER OBSERVATORY // HYBRID MACRO & CRYPTO // v{data['version']}",
        f" {data['timestamp']} // {data['run_status']} // VALID UNTIL {data['valid_until']}",
        "=" * 70,
        "",
        " SCOPE: Experimental rule-based macro regime observer.",
        " NOTICE: Purely heuristic. Not an investment signal, solicitation, or advice.",
        "",
        f" OVERALL STATUS : {data['status']} [Score: {data['composite_score']}/100]",
        f" DATA QUALITY   : {q['status']} [{q['score']}/100]",
    ]
    if q["degraded_feeds"]:
        lines.append(f" DEGRADED FEEDS : {', '.join(q['degraded_feeds'])}")
    lines += [
        f" CURRENT REGIME : {data['desc']}",
        "",
        " --- OPERATIONAL POSTURE (RULE-BASED REFERENCE HEURISTICS) ---",
    ]
    for label, key in (("GRID BOTS", "grid_bots"), ("DIP BUYING", "dip_buying"),
                       ("CRYPTO PERPS", "crypto_perps"), ("SHORT VOLUME", "dark_pool"),
                       ("COLLATERAL", "collateral")):
        lines.append(f" [*] {label:<13}: {t[key]['status']} -> {t[key]['action']}")
    lines += ["", " --- 6 PILLARS ---"]
    for i, (key, title, feed, values, score, fb) in enumerate(rows, 1):
        tag = f" [{fb}]" if fb else ""
        lines.append(f" [{i}] {title:<18}: Score {score}/100 ({values}){tag}")
    lines += [
        "",
        f" API: curl -sL {BASE_URL}/weather.json",
        f" REPO: {REPO_URL}",
        "=" * 70,
        "",
    ]
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
        .scope-notice { color: #a0aec0; font-size: 0.8rem; margin-top: 0.3rem; }
        .status-box { border: 2px solid __COLOR__; background: #111419; padding: 1.5rem 1rem; margin-bottom: 2rem; text-align: center; border-radius: 4px; }
        .status-symbol { font-size: 3.8rem; line-height: 1; margin-bottom: 0.6rem; display: block; }
        .status-title { font-size: 1.5rem; color: __COLOR__; margin: 0 0 0.5rem 0; font-weight: bold; }
        .status-desc { color: #9ca3af; font-size: 0.95rem; max-width: 650px; margin: auto; }
        .quality { margin-top: 0.8rem; font-size: 0.85rem; font-weight: bold; }
        .q-high { color: #00ff66; }
        .q-medium { color: #ffcc00; }
        .q-low { color: #ff6600; }
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
        .footer { margin-top: 2.5rem; border-top: 1px dashed #2d3748; padding-top: 1rem; font-size: 0.75rem; color: #718096; line-height: 1.6; }
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
    q = data["data_quality"]
    score, symbol, status = data["composite_score"], data["symbol"], esc(data["status"])
    timestamp, desc = data["timestamp"], esc(data["desc"])
    css = HTML_CSS.replace("__COLOR__", data["color"])
    quality_class = "q-" + q["status"].lower()
    degraded = f" // degraded: {esc(', '.join(q['degraded_feeds']))}" if q["degraded_feeds"] else ""

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
    <meta name="description" content="A heuristic macro- and crypto-regime observer aggregating public operational feeds.">
    <link rel="icon" href="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%20100%20100'%3E%3Ctext%20y='.9em'%20font-size='90'%3E{symbol}%3C/text%3E%3C/svg%3E">
    <style>{css}</style>
</head>
<body>
    <div class="header">
        <strong>OPEN MARKET WEATHER OBSERVATORY</strong><br>
        <span class="badge-sub">TIMESTAMP: {timestamp} // {esc(data['run_status'])} // v{data['version']}</span><br>
        <div class="scope-notice">SCOPE: Rule-based environmental regime observer. Not an investment signal or advisory tool.</div>
        <div class="header-links">
            <a href="weather.json">[Raw JSON API]</a> &nbsp;|&nbsp;
            <a href="weather.txt">[Plaintext for cURL]</a> &nbsp;|&nbsp;
            <a href="badge.svg">[Live SVG Badge]</a> &nbsp;|&nbsp;
            <a href="{esc(REPO_URL)}" target="_blank" rel="noopener">[GitHub Repository]</a>
        </div>
    </div>

    <div class="status-box">
        <span class="status-symbol">{symbol}</span>
        <div class="status-title">{status} (SCORE: {score}/100)</div>
        <div class="status-desc">{desc}</div>
        <div class="quality {quality_class}">DATA QUALITY: {q['status']} ({q['score']}/100){degraded}</div>
    </div>

    <div class="posture-card">
        <div class="posture-title">Operational Posture // Rule-Based Reference Heuristics</div>{posture_html}
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
        Open market metrics. Built with Python stdlib on Cloudflare and GitHub Actions.<br>
        STRICTLY INFORMATIONAL &amp; EXPERIMENTAL. No investment advice, trade signals, or commercial solicitation. All metrics are heuristic, derived, and subject to latency.<br>
        CLI access: <code>curl -sL {esc(BASE_URL)}/weather.txt</code>
    </div>
</body>
</html>
"""


def atomic_write(path, content):
    """Write via temp file + os.replace so readers never see a half-written file."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    try:
        mode = os.stat(path).st_mode & 0o777
    except OSError:
        mode = 0o644
    fd, tmp = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def validate_output(data):
    required = ("schema_version", "generated_at", "valid_until", "run_status",
                "composite_score", "composite_raw", "data_quality", "feed_health",
                "tactical_posture", "pillars")
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Output validation failed; missing: {', '.join(missing)}")
    if not isinstance(data["composite_score"], int) or isinstance(data["composite_score"], bool):
        raise ValueError("composite_score must be an int")
    if not isinstance(data["composite_raw"], (int, float)) or not 0 <= data["composite_raw"] <= 100:
        raise ValueError("composite_raw must be a number between 0 and 100")
    if data["tactical_posture"]["grid_bots"]["status"] not in GRID_SEVERITY:
        raise ValueError("Invalid grid status")
    absent = [k for k in WEIGHTS if k not in data["pillars"]]
    if absent:
        raise ValueError(f"Output validation failed; pillars missing: {', '.join(absent)}")


def export_files(data):
    validate_output(data)
    rows = pillar_rows(data["pillars"], data["feed_health"])
    outputs = {
        "weather.txt": render_text(data, rows),
        "badge.svg": render_badge(data),
        "index.html": render_html(data, rows),
        "weather.json": json.dumps(data, indent=2, ensure_ascii=False),
    }
    for name in ("weather.txt", "badge.svg", "index.html", "weather.json"):
        atomic_write(name, outputs[name])
    try:
        append_history(data)
    except Exception as exc:
        log("ERROR", "HISTORY", f"could not append to {HISTORY_FILE}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    log("INFO", "ENGINE", f"Running Market Weather Engine v{VERSION}")
    try:
        weather = calculate_systemic_weather()
        export_files(weather)
        log("INFO", "ENGINE",
            f"Complete: {weather['composite_score']}/100 -> {weather['status']} / "
            f"{weather['tactical_posture']['grid_bots']['status']}")
    except Exception as exc:
        log("ERROR", "ENGINE", f"Run failed, previous outputs stay in place: {type(exc).__name__}: {exc}")
        raise
