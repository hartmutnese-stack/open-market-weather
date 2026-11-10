import json
import math
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OpenMarketWeather/3.1"
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
# SÄULE 1: TRADFI VOLATILITY (VIX & MOVE)
# ==============================================================================
def get_market_volatility():
    tickers = {"VIX": "%5EVIX", "MOVE": "%5EMOVE"}
    scores = {}
    is_fallback = False
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
            is_fallback = True
            
    avg_score = int((scores["vix"][0] * 0.5) + (scores["move"][0] * 0.5))
    return avg_score, scores["vix"][1], scores["move"][1], is_fallback

# ==============================================================================
# SÄULE 2: CRYPTO LEVERAGE & DVOL (HYPERLIQUID & DERIBIT DVOL INDEX)
# ==============================================================================
def get_crypto_247_vector():
    btc_funding_apr = 10.0
    btc_oi_mil = 0.0
    dvol_val = 52.0
    is_fallback = False
    
    # 1. Hyperliquid Native API
    try:
        hl_url = "https://api.hyperliquid.xyz/info"
        hl_payload = json.dumps({"type": "metaAndAssetCtxs"}).encode("utf-8")
        req = urllib.request.Request(
            hl_url, 
            data=hl_payload, 
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
            if len(data) >= 2 and "universe" in data[0]:
                universe = data[0]["universe"]
                asset_ctxs = data[1]
                btc_idx = None
                for idx, coin_meta in enumerate(universe):
                    if coin_meta.get("name") == "BTC":
                        btc_idx = idx
                        break
                if btc_idx is not None and btc_idx < len(asset_ctxs):
                    ctx = asset_ctxs[btc_idx]
                    hourly_funding = float(ctx.get("funding", 0.0))
                    btc_funding_apr = round(hourly_funding * 24 * 365 * 100, 1)
                    oracle_px = float(ctx.get("oraclePx", 0.0))
                    oi = float(ctx.get("openInterest", 0.0))
                    btc_oi_mil = round((oi * oracle_px) / 1_000_000, 1)
    except Exception as e:
        print(f"[!] Hyperliquid fetch error: {e}")
        is_fallback = True

    # 2. Deribit Real DVOL Index Endpoint
    try:
        deribit_url = "https://www.deribit.com/api/v2/public/get_index_price?index_name=btcdvol_usdc"
        dvol_data = fetch_json(deribit_url, timeout=6)
        if dvol_data and "result" in dvol_data and "index_price" in dvol_data["result"]:
            dvol_val = round(float(dvol_data["result"]["index_price"]), 1)
        else:
            is_fallback = True
    except Exception as e:
        print(f"[!] Deribit DVOL fetch error: {e}")
        is_fallback = True

    funding_stress = 15
    if btc_funding_apr > 25.0:
        funding_stress = min(100, int((btc_funding_apr - 20.0) * 3.0) + 30)
    elif btc_funding_apr < -10.0:
        funding_stress = min(100, int(abs(btc_funding_apr + 10.0) * 3.5) + 40)
    else:
        funding_stress = max(10, int(abs(btc_funding_apr) * 1.5))
        
    vola_stress = min(100, max(0, int((dvol_val - 45.0) * (100 / 35))))
    crypto_score = int((funding_stress * 0.6) + (vola_stress * 0.4))
    
    return crypto_score, btc_funding_apr, btc_oi_mil, dvol_val, is_fallback

# ==============================================================================
# SÄULE 3: FINRA SHORT VOLUME (SPY)
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
                                return score, ratio, date_str, False
        except Exception:
            continue
    return 25, 48.0, "Fallback", True

# ==============================================================================
# SÄULE 4: DOLLAR LIQUIDITY (TGA & NY FED SWAPS)
# ==============================================================================
def get_liquidity_plumbing():
    tga_url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/dts_table_1?filter=account_type:eq:Treasury%20General%20Account%20(TGA)%20Closing%20Balance&sort=-record_date&page[size]=10"
    data = fetch_json(tga_url)
    tga_bal, tga_change, tga_score = 850.0, 0.0, 15
    is_fallback = False
    
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
        else:
            is_fallback = True
    else:
        is_fallback = True

    swaps_url = "https://markets.newyorkfed.org/api/fxs/all/latest.json"
    swap_data = fetch_json(swaps_url)
    swap_volume_b = 0.0
    if swap_data and "data" in swap_data:
        for deal in swap_data.get("data", []):
            amt = deal.get("amount", 0)
            swap_volume_b += float(amt) / 1000000000.0
    else:
        is_fallback = True
            
    swap_score = min(100, int(swap_volume_b * 10))
    composite = int((tga_score * 0.7) + (swap_score * 0.3))
    return composite, round(tga_bal, 1), round(tga_change, 1), round(swap_volume_b, 2), is_fallback

# ==============================================================================
# SÄULE 5: CREDIT STRESS (SEC 8-K ITEM 2.04)
# ==============================================================================
def get_credit_distress_vector():
    today = datetime.utcnow()
    two_weeks_ago = (today - timedelta(days=14)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    is_fallback = False
    
    sec_url = f"https://efts.sec.gov/LATEST/search-index?q=%22Item+2.04%22&forms=8-K&startdt={two_weeks_ago}&enddt={today_str}"
    sec_data = fetch_json(sec_url, timeout=6)
    filing_count = 0
    if sec_data and "hits" in sec_data and "total" in sec_data["hits"]:
        filing_count = sec_data["hits"]["total"].get("value", 0)
    else:
        filing_count = 11
        is_fallback = True
        
    credit_score = min(100, max(5, int(filing_count * 4.0)))
    return credit_score, filing_count, is_fallback

# ==============================================================================
# SÄULE 6: ODDS AND ENDS (WIKIPEDIA & CBP LAREDO)
# ==============================================================================
def get_cognitive_and_physical():
    articles = ["Bank_run", "Credit_default_swap", "Circuit_breaker_(stock_market)", "Force_majeure", "Bail-in", "Insolvency"]
    today = datetime.utcnow()
    end_date = (today - timedelta(days=1)).strftime("%Y%m%d")
    start_date = (today - timedelta(days=25)).strftime("%Y%m%d")
    is_fallback = False
    
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
            anomalies.append(max(0.0, z_score))
        else:
            is_fallback = True
            
    avg_z = sum(anomalies) / len(anomalies) if anomalies else 0.0
    wiki_score = min(100, int(avg_z * 25))

    cbp_url = "https://bwt.cbp.gov/api/waittimes"
    cbp_data = fetch_json(cbp_url, timeout=8)
    laredo_wait = 20
    if cbp_data and isinstance(cbp_data, list):
        delays = []
        for port in cbp_data:
            if "Laredo" in port.get("port_name", ""):
                comm = port.get("commercial_lanes") or {}
                std = comm.get("standard_lanes") or {}
                delay = std.get("delay_minutes")
                if delay is not None and str(delay).strip().isdigit():
                    delays.append(int(delay))
        if delays:
            laredo_wait = max(delays)
    else:
        is_fallback = True
            
    phys_score = min(100, max(0, int((laredo_wait - 15) * (100 / 105))))
    composite = int((wiki_score * 0.6) + (phys_score * 0.4))
    return composite, round(avg_z, 2), laredo_wait, is_fallback

# ==============================================================================
# TACTICAL POSTURE GENERATOR
# ==============================================================================
def generate_tactical_posture(composite, vix, finra_svr, swaps_vol, crypto_score, btc_funding):
    posture = {}
    
    # 1. Grid Bots Directive
    if crypto_score > 65 or composite >= 65:
        posture["grid_bots"] = {"status": "PAUSED", "color": "#ff0033", "action": f"Pause new grids. Dislocation or leverage risk elevated (Crypto score: {crypto_score})."}
    elif composite < 35 and vix < 20 and crypto_score < 40:
        posture["grid_bots"] = {"status": "ACTIVE", "color": "#00ff66", "action": "Calm conditions. Standard grid parameters."}
    else:
        posture["grid_bots"] = {"status": "CAUTION", "color": "#ffcc00", "action": "Widen grid bands by 15-25%. Reduce leverage / lot sizes."}
        
    # 2. Dip-Buying (DCA)
    if composite < 45 and finra_svr < 55.0 and crypto_score < 50:
        posture["dip_buying"] = {"status": "FAVORABLE", "color": "#00ff66", "action": "Orderly pullbacks. Liquidity supports absorption."}
    else:
        posture["dip_buying"] = {"status": "DEFENSIVE", "color": "#ff6600", "action": "Support lines fragile. Do not catch falling knives."}
        
    # 3. Crypto Perps
    funding_sign = f"{btc_funding:+.1f}%"
    if btc_funding > 25.0:
        posture["crypto_perps"] = {"status": "OVERHEATED", "color": "#ff0033", "action": f"High perp funding ({funding_sign} APR). Long squeeze risk."}
    elif btc_funding < -10.0:
        posture["crypto_perps"] = {"status": "HEAVY SHORT", "color": "#ff6600", "action": f"Negative perp funding ({funding_sign} APR). Potential short squeeze."}
    else:
        posture["crypto_perps"] = {"status": "NOMINAL", "color": "#00ff66", "action": f"Moderate derivatives leverage (BTC funding: {funding_sign} APR)."}

    # 4. Short Volume (FINRA)
    if finra_svr < 50.0:
        posture["dark_pool"] = {"status": "NOMINAL", "color": "#00ff66", "action": f"Normal short volume share on SPY ({finra_svr}%)."}
    elif finra_svr < 58.0:
        posture["dark_pool"] = {"status": "ELEVATED", "color": "#ffcc00", "action": f"Elevated short volume share on SPY ({finra_svr}%)."}
    else:
        posture["dark_pool"] = {"status": "HIGH", "color": "#ff0033", "action": f"High short volume share on SPY ({finra_svr}%)."}
        
    # 5. Interbank Collateral
    if swaps_vol == 0.0 and composite < 50:
        posture["collateral"] = {"status": "STABLE", "color": "#00ff66", "action": "No central bank emergency swap usage."}
    else:
        posture["collateral"] = {"status": "FRICTION DETECTED", "color": "#ff0033", "action": f"Emergency facility draw active (${swaps_vol}B)."}
        
    return posture

# ==============================================================================
# MAIN ENGINE
# ==============================================================================
def calculate_systemic_weather():
    mkt_score, vix_val, move_val, fb_mkt = get_market_volatility()
    crypto_score, btc_funding, btc_oi, dvol_val, fb_crypto = get_crypto_247_vector()
    finra_score, finra_svr, finra_date, fb_finra = get_finra_darkpool_short()
    liq_score, tga_bal, tga_flow, swap_vol, fb_liq = get_liquidity_plumbing()
    cred_score, sec_filings, fb_cred = get_credit_distress_vector()
    cog_score, wiki_z, laredo_wait, fb_cog = get_cognitive_and_physical()
    
    composite = int(
        (mkt_score * 0.20) +
        (crypto_score * 0.20) +
        (finra_score * 0.15) +
        (liq_score * 0.20) +
        (cred_score * 0.15) +
        (cog_score * 0.10)
    )
    
    if composite < 25:
        symbol = "☀️"
        status = "CLEAR SKIES"
        desc = "Systemic friction minimal. Normal market conditions across macro and crypto feeds."
        color = "#00ff66"
    elif composite < 50:
        symbol = "⛅"
        status = "SCATTERED CLOUDS"
        desc = "Operational noise within standard ranges. No immediate systemic fracture."
        color = "#ffcc00"
    elif composite < 75:
        symbol = "🌧️"
        status = "SQUALL / DOWNPOUR"
        desc = "Elevated friction: notable divergence in crypto leverage, options or liquidity plumbing."
        color = "#ff6600"
    else:
        symbol = "⛈️"
        status = "SEVERE GALE / SYSTEMIC SHOCK"
        desc = "High alert: widespread dislocation across multiple operational feeds."
        color = "#ff0033"
        
    tactical = generate_tactical_posture(composite, vix_val, finra_svr, swap_vol, crypto_score, btc_funding)
    
    fallback_flags = {
        "market_implied": fb_mkt,
        "crypto_247": fb_crypto,
        "dark_pool_finra": fb_finra,
        "liquidity_plumbing": fb_liq,
        "credit_statutory": fb_cred,
        "odds_and_ends": fb_cog
    }
    
    return {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "symbol": symbol,
        "composite_score": composite,
        "status": status,
        "desc": desc,
        "color": color,
        "fallback_flags": fallback_flags,
        "tactical_posture": tactical,
        "pillars": {
            "market_implied": {"score": mkt_score, "vix": vix_val, "move_index": move_val, "fallback": fb_mkt},
            "crypto_247": {"score": crypto_score, "btc_funding_apr": btc_funding, "btc_oi_mil": btc_oi, "dvol_index": dvol_val, "fallback": fb_crypto},
            "dark_pool_finra": {"score": finra_score, "spy_short_volume_ratio": finra_svr, "report_date": finra_date, "fallback": fb_finra},
            "liquidity_plumbing": {"score": liq_score, "tga_billions": tga_bal, "tga_5d_flow": tga_flow, "swaps_billions": swap_vol, "fallback": fb_liq},
            "credit_statutory": {"score": cred_score, "sec_8k_filings": sec_filings, "fallback": fb_cred},
            "odds_and_ends": {"score": cog_score, "wiki_z": wiki_z, "border_wait_m": laredo_wait, "fallback": fb_cog}
        }
    }

# ==============================================================================
# EXPORT ENGINE
# ==============================================================================
def export_files(data):
    p = data["pillars"]
    t = data["tactical_posture"]
    base_url = "https://open-market-weather.hartmut-nese.workers.dev"
    
    with open("weather.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # Helper für Fallback-Tagging im Terminal
    fb = lambda key: " [fallback]" if p[key].get("fallback") else ""
    funding_str = f"{p['crypto_247']['btc_funding_apr']:+.1f}%"

    term = f"""
======================================================================
 OPEN MARKET WEATHER OBSERVATORY // HYBRID MACRO & CRYPTO
 {data['timestamp']} // STANDALONE HEURISTIC // HOURLY REFRESH
======================================================================

 OVERALL STATUS : {data['status']} [Score: {data['composite_score']}/100]
 CURRENT REGIME : {data['desc']}

 --- TACTICAL POSTURE (OPERATIONAL DIRECTIVES) ---
 [*] GRID BOTS      : {t['grid_bots']['status']} -> {t['grid_bots']['action']}
 [*] DIP BUYING     : {t['dip_buying']['status']} -> {t['dip_buying']['action']}
 [*] CRYPTO PERPS   : {t['crypto_perps']['status']} -> {t['crypto_perps']['action']}
 [*] SHORT VOLUME   : {t['dark_pool']['status']} -> {t['dark_pool']['action']}
 [*] COLLATERAL     : {t['collateral']['status']} -> {t['collateral']['action']}

 --- 6 OPERATIONAL PILLARS ---
 [1] Market Volatility     : Score {p['market_implied']['score']}/100 (VIX: {p['market_implied']['vix']} | MOVE: {p['market_implied']['move_index']}){fb('market_implied')}
 [2] Crypto Leverage       : Score {p['crypto_247']['score']}/100 (Funding: {funding_str} APR | DVOL: {p['crypto_247']['dvol_index']}%){fb('crypto_247')}
 [3] Dark Pool Short Share : Score {p['dark_pool_finra']['score']}/100 (SPY Short: {p['dark_pool_finra']['spy_short_volume_ratio']}% | Date: {p['dark_pool_finra']['report_date']}){fb('dark_pool_finra')}
 [4] Dollar Liquidity      : Score {p['liquidity_plumbing']['score']}/100 (TGA: ${p['liquidity_plumbing']['tga_billions']}B | Swaps: ${p['liquidity_plumbing']['swaps_billions']}B){fb('liquidity_plumbing')}
 [5] Credit Stress         : Score {p['credit_statutory']['score']}/100 (SEC 8-K Accelerations: {p['credit_statutory']['sec_8k_filings']}){fb('credit_statutory')}
 [6] Odds and Ends         : Score {p['odds_and_ends']['score']}/100 (Analyst Z: +{p['odds_and_ends']['wiki_z']}σ | Border: {p['odds_and_ends']['border_wait_m']}m){fb('odds_and_ends')}

 API: curl -sL {base_url}/weather.json
======================================================================
"""
    with open("weather.txt", "w", encoding="utf-8") as f:
        f.write(term)

    badge = f"""<svg xmlns="http://www.w3.org/2000/svg" width="160" height="20">
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
    with open("badge.svg", "w", encoding="utf-8") as f:
        f.write(badge)

    # HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
    <title>Market Weather ({data['composite_score']}/100)</title>
    <meta name="description" content="A weather report for the markets based on public macro and crypto data feeds.">
    <link rel="icon" href="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%20100%20100'%3E%3Ctext%20y='.9em'%20font-size='90'%3E{data['symbol']}%3C/text%3E%3C/svg%3E">
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            background: #090b0e;
            color: #d1d5db;
            font-family: 'SF Mono', Consolas, 'Liberation Mono', Menlo, monospace;
            padding: 1.5rem 1rem;
            max-width: 920px;
            margin: auto;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }}
        .header {{ border-bottom: 1px dashed #2d3748; padding-bottom: 1rem; margin-bottom: 1.5rem; }}
        .header-links {{ margin-top: 0.8rem; font-size: 0.9rem; word-break: break-all; }}
        .badge-sub {{ color: #718096; font-size: 0.8rem; }}
        .status-box {{
            border: 2px solid {data['color']};
            background: #111419;
            padding: 1.5rem 1rem;
            margin-bottom: 2rem;
            text-align: center;
            border-radius: 4px;
        }}
        .status-symbol {{
            font-size: 3.8rem;
            line-height: 1;
            margin-bottom: 0.6rem;
            display: block;
        }}
        .status-title {{
            font-size: 1.5rem;
            color: {data['color']};
            margin: 0 0 0.5rem 0;
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
        .status-desc {{
            color: #9ca3af;
            font-size: 0.95rem;
            max-width: 650px;
            margin: auto;
        }}
        .posture-card {{
            border: 1px solid #2d3748;
            background: #0d1117;
            padding: 1.25rem;
            margin-bottom: 2rem;
            border-radius: 4px;
        }}
        .posture-title {{
            font-size: 0.9rem;
            font-weight: bold;
            color: #e2e8f0;
            text-transform: uppercase;
            letter-spacing: 1px;
            border-bottom: 1px dashed #2d3748;
            padding-bottom: 0.5rem;
            margin-bottom: 0.75rem;
        }}
        .posture-item {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            padding: 0.5rem 0;
            border-bottom: 1px solid #161b22;
            font-size: 0.9rem;
        }}
        .posture-item:last-child {{ border-bottom: none; }}
        .posture-label {{ font-weight: bold; color: #a0aec0; width: 140px; flex-shrink: 0; }}
        .posture-status {{ font-weight: bold; width: 120px; flex-shrink: 0; }}
        .posture-action {{ color: #cbd5e0; flex: 1; text-align: right; }}
        
        .table-container {{
            width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            margin-top: 1rem;
            border: 1px solid #1a202c;
            border-radius: 4px;
        }}
        .table {{ width: 100%; border-collapse: collapse; min-width: 640px; }}
        .table td, .table th {{ padding: 0.75rem 0.6rem; text-align: left; border-bottom: 1px solid #1a202c; }}
        .table th {{ color: #718096; font-size: 0.8rem; text-transform: uppercase; background: #0d1117; }}
        a {{ color: #63b3ed; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .footer {{ margin-top: 2.5rem; border-top: 1px dashed #2d3748; padding-top: 1rem; font-size: 0.8rem; color: #718096; }}
        .score-pill {{ font-weight: bold; padding: 2px 8px; border-radius: 3px; background: #1a202c; white-space: nowrap; }}
        .tag-fallback {{ color: #f59e0b; font-size: 0.75rem; margin-left: 4px; }}
        code {{ background: #1a202c; padding: 2px 6px; border-radius: 3px; color: #e2e8f0; }}

        @media (max-width: 640px) {{
            body {{ padding: 1rem 0.75rem; }}
            .status-symbol {{ font-size: 3.2rem; }}
            .status-title {{ font-size: 1.3rem; }}
            .status-desc {{ font-size: 0.85rem; }}
            
            .posture-item {{
                flex-direction: column;
                align-items: flex-start;
                gap: 4px;
                padding: 0.6rem 0;
            }}
            .posture-label {{ width: 100%; font-size: 0.8rem; }}
            .posture-status {{ width: 100%; font-size: 0.85rem; margin-bottom: 2px; }}
            .posture-action {{ text-align: left; font-size: 0.85rem; color: #a0aec0; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <strong>OPEN MARKET WEATHER OBSERVATORY</strong><br>
        <span class="badge-sub">TIMESTAMP: {data['timestamp']} // HOURLY REFRESH // HEURISTIC MATRIX</span>
        <div class="header-links">
            <a href="weather.json">[Raw JSON API]</a> &nbsp;|&nbsp; 
            <a href="weather.txt">[Plaintext for cURL]</a> &nbsp;|&nbsp; 
            <a href="badge.svg">[Live SVG Badge]</a>
        </div>
    </div>

    <div class="status-box">
        <span class="status-symbol">{data['symbol']}</span>
        <div class="status-title">{data['status']} (SCORE: {data['composite_score']}/100)</div>
        <div class="status-desc">{data['desc']}</div>
    </div>

    <div class="posture-card">
        <div class="posture-title">Tactical Posture // Suggestions for Trading Bots</div>
        <div class="posture-item">
            <span class="posture-label">GRID BOTS</span>
            <span class="posture-status" style="color: {t['grid_bots']['color']}">{t['grid_bots']['status']}</span>
            <span class="posture-action">{t['grid_bots']['action']}</span>
        </div>
        <div class="posture-item">
            <span class="posture-label">DIP BUYING</span>
            <span class="posture-status" style="color: {t['dip_buying']['color']}">{t['dip_buying']['status']}</span>
            <span class="posture-action">{t['dip_buying']['action']}</span>
        </div>
        <div class="posture-item">
            <span class="posture-label">CRYPTO PERPS</span>
            <span class="posture-status" style="color: {t['crypto_perps']['color']}">{t['crypto_perps']['status']}</span>
            <span class="posture-action">{t['crypto_perps']['action']}</span>
        </div>
        <div class="posture-item">
            <span class="posture-label">SHORT VOLUME</span>
            <span class="posture-status" style="color: {t['dark_pool']['color']}">{t['dark_pool']['status']}</span>
            <span class="posture-action">{t['dark_pool']['action']}</span>
        </div>
        <div class="posture-item">
            <span class="posture-label">COLLATERAL</span>
            <span class="posture-status" style="color: {t['collateral']['color']}">{t['collateral']['status']}</span>
            <span class="posture-action">{t['collateral']['action']}</span>
        </div>
    </div>

    <h3>THE 6 PILLARS</h3>
    <div class="table-container">
        <table class="table">
            <thead>
                <tr>
                    <th>Pillar</th>
                    <th>Underlying Feed</th>
                    <th>Live Values</th>
                    <th>Friction Score</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>1. Market Volatility</strong></td>
                    <td>S&P 500 VIX + Treasury MOVE Index</td>
                    <td>VIX: {p['market_implied']['vix']} | MOVE: {p['market_implied']['move_index']}{'<span class="tag-fallback">[fallback]</span>' if p['market_implied']['fallback'] else ''}</td>
                    <td><span class="score-pill">{p['market_implied']['score']}/100</span></td>
                </tr>
                <tr>
                    <td><strong>2. Crypto Leverage</strong></td>
                    <td>Hyperliquid BTC Funding + Deribit DVOL Index</td>
                    <td>Funding: {funding_str} APR | DVOL: {p['crypto_247']['dvol_index']}%{'<span class="tag-fallback">[fallback]</span>' if p['crypto_247']['fallback'] else ''}</td>
                    <td><span class="score-pill">{p['crypto_247']['score']}/100</span></td>
                </tr>
                <tr>
                    <td><strong>3. Short Volume</strong></td>
                    <td>FINRA Reg SHO Daily Flat File (SPY)</td>
                    <td>Short Ratio: {p['dark_pool_finra']['spy_short_volume_ratio']}% ({p['dark_pool_finra']['report_date']}){'<span class="tag-fallback">[fallback]</span>' if p['dark_pool_finra']['fallback'] else ''}</td>
                    <td><span class="score-pill">{p['dark_pool_finra']['score']}/100</span></td>
                </tr>
                <tr>
                    <td><strong>4. Dollar Liquidity</strong></td>
                    <td>U.S. TGA Cash + NY Fed Central Bank Swaps</td>
                    <td>TGA: ${p['liquidity_plumbing']['tga_billions']}B | Swaps: ${p['liquidity_plumbing']['swaps_billions']}B{'<span class="tag-fallback">[fallback]</span>' if p['liquidity_plumbing']['fallback'] else ''}</td>
                    <td><span class="score-pill">{p['liquidity_plumbing']['score']}/100</span></td>
                </tr>
                <tr>
                    <td><strong>5. Credit Stress</strong></td>
                    <td>SEC 8-K Form (Item 2.04 Acceleration - 14D)</td>
                    <td>Active Filings: {p['credit_statutory']['sec_8k_filings']}{'<span class="tag-fallback">[fallback]</span>' if p['credit_statutory']['fallback'] else ''}</td>
                    <td><span class="score-pill">{p['credit_statutory']['score']}/100</span></td>
                </tr>
                <tr>
                    <td><strong>6. Odds and Ends</strong></td>
                    <td>Wikimedia Crisis Traffic (6%) + CBP Laredo Freight (4%)</td>
                    <td>Analyst Z: +{p['odds_and_ends']['wiki_z']}σ | Border: {p['odds_and_ends']['border_wait_m']}m{'<span class="tag-fallback">[fallback]</span>' if p['odds_and_ends']['fallback'] else ''}</td>
                    <td><span class="score-pill">{p['odds_and_ends']['score']}/100</span></td>
                </tr>
            </tbody>
        </table>
    </div>

    <div class="footer">
        Open market metrics. Built with Python stdlib on Cloudflare and GitHub Actions. No financial advice.<br>
        CLI Access: <code>curl -sL {base_url}/weather.txt</code><br>
        Bot Embed: <code>&lt;img src="{base_url}/badge.svg"&gt;</code>
    </div>
</body>
</html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    print("[*] Running Market Weather Engine v3.1...")
    w = calculate_systemic_weather()
    export_files(w)
    print(f"[+] Complete: Score is {w['composite_score']}/100 -> {w['status']}")
