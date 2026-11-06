import json
import math
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OpenMarketWeather/2.3"
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
# SÄULE 2: FINRA DARK POOL SHORT VOLUME (ÜBER NEUES FINRA CDN)
# ==============================================================================
def get_finra_darkpool_short():
    today = datetime.utcnow()
    # Prüfe die letzten 6 Tage (deckt Wochenenden & Feiertage ab)
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
# SÄULE 3: DOLLAR PLUMBING (EXAKTER TGA CLOSING FILTER & NY FED SWAPS)
# ==============================================================================
def get_liquidity_plumbing():
    # Exakter Filter auf TGA Closing Balance (Wert steht im Feld open_today_bal)
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
            # Vergleich mit vor 5 Geschäftstagen (oder ältestem verfügbarem Eintrag)
            prev = tga_rows[min(4, len(tga_rows) - 1)]
            tga_change = (latest - prev) / 1000.0
            tga_bal = latest / 1000.0
            tga_score = min(100, int(abs(tga_change) * 1.5))

    # NY Fed Central Bank Liquidity Swaps
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
# SÄULE 5: KOGNITIV & PHYSISCH (WIKIPEDIA & KORREKTE CBP WAITTIMES API)
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
            anomalies.append(max(0.0, z_score))
            
    avg_z = sum(anomalies) / len(anomalies) if anomalies else 0.0
    wiki_score = min(100, int(avg_z * 25))

    # Korrekte CBP API: /api/waittimes
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
            
    phys_score = min(100, max(0, int((laredo_wait - 15) * (100 / 105))))
    composite = int((wiki_score * 0.6) + (phys_score * 0.4))
    return composite, round(avg_z, 2), laredo_wait

# ==============================================================================
# TAKTISCHE HANDLUNGSANWEISUNGEN
# ==============================================================================
def generate_tactical_posture(composite, vix, finra_svr, swaps_vol):
    posture = {}
    
    if composite < 35 and vix < 20:
        posture["grid_bots"] = {"status": "ACTIVE", "color": "#00ff66", "action": "Favorable range-bound market regime. Mean reversion active."}
    elif composite < 60 and vix < 26:
        posture["grid_bots"] = {"status": "CAUTION", "color": "#ffcc00", "action": "Widen grid bands by 15-25%. Reduce leverage."}
    else:
        posture["grid_bots"] = {"status": "PAUSED", "color": "#ff0033", "action": "High dislocation probability. Pause automated grid execution."}
        
    if composite < 45 and finra_svr < 55.0:
        posture["dip_buying"] = {"status": "FAVORABLE", "color": "#00ff66", "action": "Pullbacks reflect standard liquidity absorption. Support lines holding."}
    else:
        posture["dip_buying"] = {"status": "DEFENSIVE", "color": "#ff6600", "action": "Support lines fragile. Do not catch falling knives; preserve capital."}
        
    if finra_svr < 50.0:
        posture["dark_pool"] = {"status": "NOMINAL", "color": "#00ff66", "action": f"Balanced flow ({finra_svr}% off-exchange short ratio on SPY)."}
    elif finra_svr < 58.0:
        posture["dark_pool"] = {"status": "ELEVATED", "color": "#ffcc00", "action": f"Elevated institutional downside hedging ({finra_svr}% SVR on SPY)."}
    else:
        posture["dark_pool"] = {"status": "AGGRESSIVE", "color": "#ff0033", "action": f"Stealth institutional short accumulation ({finra_svr}% SVR on SPY)."}
        
    if swaps_vol == 0.0 and composite < 50:
        posture["collateral"] = {"status": "STABLE", "color": "#00ff66", "action": "No central bank emergency swap usage. US Dollar conduits clear."}
    else:
        posture["collateral"] = {"status": "FRICTION DETECTED", "color": "#ff0033", "action": f"Emergency facility draw active (${swaps_vol}B). Tightened liquidity."}
        
    return posture

# ==============================================================================
# GESAMTBERECHNUNG
# ==============================================================================
def calculate_systemic_weather():
    mkt_score, vix_val, move_val = get_market_volatility()
    finra_score, finra_svr, finra_date = get_finra_darkpool_short()
    liq_score, tga_bal, tga_flow, swap_vol = get_liquidity_plumbing()
    cred_score, sec_filings = get_credit_distress_vector()
    cog_score, wiki_z, laredo_wait = get_cognitive_and_physical()
    
    composite = int(
        (mkt_score * 0.25) +
        (finra_score * 0.20) +
        (liq_score * 0.25) +
        (cred_score * 0.15) +
        (cog_score * 0.15)
    )
    
    if composite < 25:
        symbol = "☀️"
        status = "CLEAR SKIES"
        desc = "Systemic friction minimal. Normal market regime, macro conduits undisturbed."
        color = "#00ff66"
    elif composite < 50:
        symbol = "⛅"
        status = "SCATTERED CLOUDS"
        desc = "Background operational noise within historical boundaries. No immediate systemic fracture."
        color = "#ffcc00"
    elif composite < 75:
        symbol = "🌧️"
        status = "SQUALL / DOWNPOUR"
        desc = "ELEVATED SYSTEMIC FRICTION: Notable divergence in dark pool flow or interbank plumbing."
        color = "#ff6600"
    else:
        symbol = "⛈️"
        status = "SEVERE GALE / SYSTEMIC SHOCK"
        desc = "CRITICAL WARNING: Severe multi-vector dislocation across off-exchange, credit, and market layers."
        color = "#ff0033"
        
    tactical = generate_tactical_posture(composite, vix_val, finra_svr, swap_vol)
    
    return {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "symbol": symbol,
        "composite_score": composite,
        "status": status,
        "desc": desc,
        "color": color,
        "tactical_posture": tactical,
        "pillars": {
            "market_implied": {"score": mkt_score, "vix": vix_val, "move_index": move_val},
            "dark_pool_finra": {"score": finra_score, "spy_short_volume_ratio": finra_svr, "report_date": finra_date},
            "liquidity_plumbing": {"score": liq_score, "tga_billions": tga_bal, "tga_5d_flow": tga_flow, "swaps_billions": swap_vol},
            "credit_statutory": {"score": cred_score, "sec_8k_filings": sec_filings},
            "cognitive_physical": {"score": cog_score, "wiki_z": wiki_z, "border_wait_m": laredo_wait}
        }
    }

# ==============================================================================
# EXPORT ENGINE (MIT MOBILE-OPTIMIERUNG)
# ==============================================================================
def export_files(data):
    p = data["pillars"]
    t = data["tactical_posture"]
    
    with open("weather.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    term = f"""
======================================================================
 OPEN MARKET WEATHER OBSERVATORY // UNBIASED MACRO FRICTION
 {data['timestamp']} // ZERO COMMERCIAL BIAS // RAW EXHAUST DATA
======================================================================

 OVERALL STATUS : {data['status']} [Score: {data['composite_score']}/100]
 CURRENT REGIME : {data['desc']}

 --- TACTICAL POSTURE (OPERATIONAL DIRECTIVES) ---
 [*] GRID BOTS      : {t['grid_bots']['status']} -> {t['grid_bots']['action']}
 [*] DIP BUYING     : {t['dip_buying']['status']} -> {t['dip_buying']['action']}
 [*] DARK POOL FLOW : {t['dark_pool']['status']} -> {t['dark_pool']['action']}
 [*] COLLATERAL     : {t['collateral']['status']} -> {t['collateral']['action']}

 --- 5 OPERATIONAL PILLARS ---
 [1] Market Options Vola    : Score {p['market_implied']['score']}/100 (VIX: {p['market_implied']['vix']} | MOVE: {p['market_implied']['move_index']})
 [2] Dark Pool Short Ratio  : Score {p['dark_pool_finra']['score']}/100 (SPY Short: {p['dark_pool_finra']['spy_short_volume_ratio']}% | Date: {p['dark_pool_finra']['report_date']})
 [3] Global Dollar Plumbing : Score {p['liquidity_plumbing']['score']}/100 (TGA: ${p['liquidity_plumbing']['tga_billions']}B [5D: {p['liquidity_plumbing']['tga_5d_flow']}B] | Swaps: ${p['liquidity_plumbing']['swaps_billions']}B)
 [4] Statutory Credit Risk  : Score {p['credit_statutory']['score']}/100 (SEC 8-K Accelerations: {p['credit_statutory']['sec_8k_filings']})
 [5] Cognitive & Logistics  : Score {p['cognitive_physical']['score']}/100 (Analyst Z: +{p['cognitive_physical']['wiki_z']}σ | Border: {p['cognitive_physical']['border_wait_m']}m)

 API: curl -sL https://{os.environ.get('CF_PAGES_URL', 'marketweather.pages.dev')}/weather.json
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

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
    <title>Market Weather // Macro Observatory</title>
    <meta name="description" content="Decentralized systemic risk barometer tracking FINRA dark pools, interbank liquidity, and options market stress.">
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            background: #090b0e;
            color: #d1d5db;
            font-family: 'SF Mono', Consolas, 'Liberation Mono', Menlo, monospace;
            padding: 1.5rem 1rem;
            max-width: 900px;
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
        .posture-label {{ font-weight: bold; color: #a0aec0; width: 130px; flex-shrink: 0; }}
        .posture-status {{ font-weight: bold; width: 110px; flex-shrink: 0; }}
        .posture-action {{ color: #cbd5e0; flex: 1; text-align: right; }}
        
        .table-container {{
            width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            margin-top: 1rem;
            border: 1px solid #1a202c;
            border-radius: 4px;
        }}
        .table {{ width: 100%; border-collapse: collapse; min-width: 600px; }}
        .table td, .table th {{ padding: 0.75rem 0.6rem; text-align: left; border-bottom: 1px solid #1a202c; }}
        .table th {{ color: #718096; font-size: 0.8rem; text-transform: uppercase; background: #0d1117; }}
        a {{ color: #63b3ed; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .footer {{ margin-top: 2.5rem; border-top: 1px dashed #2d3748; padding-top: 1rem; font-size: 0.8rem; color: #718096; }}
        .score-pill {{ font-weight: bold; padding: 2px 8px; border-radius: 3px; background: #1a202c; white-space: nowrap; }}

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
        <strong>OPEN MARKET WEATHER OBSERVATORY // MACRO MATRIX</strong><br>
        <span class="badge-sub">TIMESTAMP: {data['timestamp']} // ZERO COMMERCIAL BIAS // RAW EXHAUST DATA</span>
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
        <div class="posture-title">🎯 Tactical Posture // Operational Directives</div>
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
            <span class="posture-label">DARK POOL</span>
            <span class="posture-status" style="color: {t['dark_pool']['color']}">{t['dark_pool']['status']}</span>
            <span class="posture-action">{t['dark_pool']['action']}</span>
        </div>
        <div class="posture-item">
            <span class="posture-label">COLLATERAL</span>
            <span class="posture-status" style="color: {t['collateral']['color']}">{t['collateral']['status']}</span>
            <span class="posture-action">{t['collateral']['action']}</span>
        </div>
    </div>

    <h3>THE 5 OPERATIONAL PILLARS</h3>
    <div class="table-container">
        <table class="table">
            <thead>
                <tr>
                    <th>Pillar</th>
                    <th>Underlying Exhaust Feed</th>
                    <th>Live Values</th>
                    <th>Stress Score</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>1. Market Derivatives</strong></td>
                    <td>S&P 500 VIX + Treasury MOVE Index</td>
                    <td>VIX: {p['market_implied']['vix']} | MOVE: {p['market_implied']['move_index']}</td>
                    <td><span class="score-pill">{p['market_implied']['score']}/100</span></td>
                </tr>
                <tr>
                    <td><strong>2. Dark Pool Flow</strong></td>
                    <td>FINRA Reg SHO Daily Short Volume (SPY)</td>
                    <td>Short Ratio: {p['dark_pool_finra']['spy_short_volume_ratio']}% ({p['dark_pool_finra']['report_date']})</td>
                    <td><span class="score-pill">{p['dark_pool_finra']['score']}/100</span></td>
                </tr>
                <tr>
                    <td><strong>3. Dollar Plumbing</strong></td>
                    <td>U.S. TGA Cash + NY Fed Central Bank Swaps</td>
                    <td>TGA: ${p['liquidity_plumbing']['tga_billions']}B (5D: {p['liquidity_plumbing']['tga_5d_flow']}B) | Swaps: ${p['liquidity_plumbing']['swaps_billions']}B</td>
                    <td><span class="score-pill">{p['liquidity_plumbing']['score']}/100</span></td>
                </tr>
                <tr>
                    <td><strong>4. Statutory Credit Risk</strong></td>
                    <td>SEC 8-K Form (Item 2.04 Acceleration - 14D)</td>
                    <td>Active Filings: {p['credit_statutory']['sec_8k_filings']}</td>
                    <td><span class="score-pill">{p['credit_statutory']['score']}/100</span></td>
                </tr>
                <tr>
                    <td><strong>5. Cognitive & Logistics</strong></td>
                    <td>Wikimedia Desk Traffic + CBP Laredo Freight</td>
                    <td>Analyst Z: +{p['cognitive_physical']['wiki_z']}σ | Border: {p['cognitive_physical']['border_wait_m']}m</td>
                    <td><span class="score-pill">{p['cognitive_physical']['score']}/100</span></td>
                </tr>
            </tbody>
        </table>
    </div>

    <div class="footer">
        Decentralized public utility. Built on FINRA off-exchange flows, physics, central bank balance sheets, and statutory disclosures.<br>
        CLI Access: <code>curl -sL [YOUR-URL]/weather.txt</code><br>
        Bot Embed: <code>&lt;img src="[YOUR-URL]/badge.svg"&gt;</code>
    </div>
</body>
</html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    print("[*] Running Institutional-Grade Macro Engine v2.3...")
    w = calculate_systemic_weather()
    export_files(w)
    print(f"[+] Complete: Overall Score is {w['composite_score']}/100 -> {w['status']}")
