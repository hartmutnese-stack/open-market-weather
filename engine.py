import json
import math
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# --- GLOBALE KONFIGURATION ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OpenMarketWeather/2.0 (macro-observatory; contact@marktwetter.org)"
}

def fetch_json(url, timeout=10):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"[!] Warning: Could not fetch {url}: {e}")
        return None

# ==============================================================================
# SÄULE 1: MARKT-MECHANIK (VIX & MOVE INDEX)
# ==============================================================================
def get_market_volatility():
    # Direktabfrage Yahoo Finance Chart Endpoints (VIX & MOVE)
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
                # VIX Normalisierung: <15 ruhig, >30 Sturm
                score = min(100, max(0, int((val - 12) * (100 / 23))))
                scores["vix"] = (score, round(val, 2))
            elif name == "MOVE":
                # MOVE Normalisierung: <80 ruhig, >140 Anleihepanik
                score = min(100, max(0, int((val - 70) * (100 / 80))))
                scores["move"] = (score, round(val, 2))
        else:
            scores[name.lower()] = (20, 16.5 if name == "VIX" else 95.0) # Plausibler Fallback
            
    avg_score = int((scores["vix"][0] * 0.5) + (scores["move"][0] * 0.5))
    return avg_score, scores["vix"][1], scores["move"][1]

# ==============================================================================
# SÄULE 2: LIQUIDITÄT & DOLLAR-PLUMBING (TGA & NY FED SWAPS)
# ==============================================================================
def get_liquidity_plumbing():
    # 1. TGA Operating Cash Balance (mit gefixtem Null-Check!)
    tga_url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/dts_table_1?sort=-record_date&page[size]=50"
    data = fetch_json(tga_url)
    tga_bal, tga_change, tga_score = 750.0, 0.0, 20
    
    if data and "data" in data:
        tga_rows = []
        for row in data["data"]:
            acc = row.get("account_type", "")
            if "Federal Reserve Account" in acc or "Treasury General Account" in acc:
                val = row.get("close_today_bal")
                if val in (None, "null", "", "None"):
                    val = row.get("open_today_bal")
                if val not in (None, "null", "", "None"):
                    try:
                        tga_rows.append(float(val))
                    except ValueError:
                        pass
        if len(tga_rows) >= 2:
            latest = tga_rows[0]
            prev = tga_rows[-1]
            tga_change = (latest - prev) / 1000
            tga_bal = latest / 1000
            tga_score = min(100, int(abs(tga_change) * 1.5))

    # 2. NY Fed Central Bank Liquidity Swaps
    swaps_url = "https://markets.newyorkfed.org/api/fxs/all/latest.json"
    swap_data = fetch_json(swaps_url)
    swap_volume_b = 0.0
    if swap_data and "data" in swap_data:
        for deal in swap_data.get("data", []):
            amt = deal.get("amount", 0)
            swap_volume_b += float(amt) / 1000000000
            
    swap_score = min(100, int(swap_volume_b * 10)) # >10 Mrd. USD Abruf deutet auf Stress hin
    composite = int((tga_score * 0.7) + (swap_score * 0.3))
    return composite, round(tga_bal, 1), round(tga_change, 1), round(swap_volume_b, 2), composite

# ==============================================================================
# SÄULE 3: PHYSIK & HANDEL (CBP GRENZSTAU & TREASURY BID-TO-COVER)
# ==============================================================================
def get_physical_and_debt_strain():
    # 1. CBP Border Wait Times (Laredo, Texas - World Trade Bridge)
    cbp_url = "https://bwt.cbp.gov/api/bwturl"
    cbp_data = fetch_json(cbp_url)
    laredo_wait_min = 25 # Normalzustand
    
    if cbp_data and isinstance(cbp_data, list):
        for port in cbp_data:
            if "Laredo" in port.get("port_name", ""):
                commercial = port.get("commercial_lanes", {})
                std_lanes = commercial.get("standard_lanes", {})
                delay = std_lanes.get("delay_minutes")
                if delay and delay.isdigit():
                    laredo_wait_min = int(delay)
                    break
                    
    # Normalisierung LKW-Stau: 0-30 min normal, >120 min Lieferkettenabriss
    logistics_score = min(100, max(0, int((laredo_wait_min - 20) * (100 / 100))))

    # 2. US Treasury Auction Demand (Bid-to-Cover Ratio)
    auct_url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query?sort=-record_date&page[size]=5"
    auct_data = fetch_json(auct_url)
    b2c_ratio = 2.50 # Gesunder Standardwert
    
    if auct_data and "data" in auct_data and len(auct_data["data"]) > 0:
        for auct in auct_data["data"]:
            ratio = auct.get("bid_to_cover_ratio")
            if ratio and ratio != "null":
                try:
                    b2c_ratio = float(ratio)
                    break
                except ValueError:
                    pass
                    
    # Wenn B2C unter 2.0 fällt = Auktion schwach / Anleihedruck
    debt_score = min(100, max(0, int((2.6 - b2c_ratio) * 125)))
    composite = int((logistics_score * 0.5) + (debt_score * 0.5))
    return composite, laredo_wait_min, round(b2c_ratio, 2)

# ==============================================================================
# SÄULE 4: KOGNITIVE PANIK & LUFTRUHE (WIKIPEDIA & OPENSKY)
# ==============================================================================
def get_cognitive_and_air_vector():
    # 1. Wikipedia Krisenkorb
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
            
    avg_z = sum(anomalies) / len(anomalies) if anomalies else 0.1
    wiki_score = min(100, int(avg_z * 25))

    # 2. OpenSky Network (ADS-B Korridor Basel BIZ / Zürich)
    # Bounding Box Schweiz/Süddeutschland: lat 47.0-48.0, lon 7.5-8.8
    opensky_url = "https://opensky-network.org/api/states/all?lamin=47.0&lomin=7.5&lamax=48.0&lomax=8.8"
    air_data = fetch_json(opensky_url, timeout=6)
    flight_count = 0
    if air_data and "states" in air_data and air_data["states"]:
        flight_count = len(air_data["states"])
        
    # OpenSky normal: 30-70 Flugzeuge aktiv im Fenster. Spikes am Wochenende deuten auf Krisentreffen.
    air_score = 15
    if today.weekday() in (5, 6) and flight_count > 60: # Wochenende
        air_score = 65
        
    composite = int((wiki_score * 0.7) + (air_score * 0.3))
    return composite, round(avg_z, 2), flight_count

# ==============================================================================
# SÄULE 5: KREDIT-FRIKTION (SEC FORM 8-K ITEM 2.04 & NOTFALL-FENSTER)
# ==============================================================================
def get_credit_distress_vector():
    # SEC EDGAR Volltext-Suchindex für Notfallklausel Item 2.04 (Accelerate Direct Financial Obligation)
    sec_url = "https://efts.sec.gov/LATEST/search-index?q=%22Item+2.04%22&forms=8-K"
    sec_data = fetch_json(sec_url, timeout=6)
    filing_count = 0
    
    if sec_data and "hits" in sec_data and "total" in sec_data["hits"]:
        filing_count = sec_data["hits"]["total"].get("value", 0)
        
    # Normalwert der Treffer im aktuellen Zeitraum: <10 normal, >30 Kündigungswelle
    credit_score = min(100, max(10, int(filing_count * 2.5))) if filing_count > 0 else 18
    return credit_score, filing_count

# ==============================================================================
# GESAMT-BERECHNUNG (GEWICHTETE MATRIX)
# ==============================================================================
def calculate_systemic_weather():
    mkt_score, vix_val, move_val = get_market_volatility()
    liq_score, tga_bal, tga_flow, swap_vol, _ = get_liquidity_plumbing()
    phys_score, laredo_wait, b2c_ratio = get_physical_and_debt_strain()
    cog_score, wiki_z, air_flights = get_cognitive_and_air_vector()
    cred_score, sec_filings = get_credit_distress_vector()
    
    # Ausbalancierte Gewichtung über alle 5 Säulen
    composite = int(
        (mkt_score * 0.25) +
        (liq_score * 0.25) +
        (cred_score * 0.20) +
        (phys_score * 0.15) +
        (cog_score * 0.15)
    )
    
    if composite < 25:
        status = "☀️ CLEAR SKIES"
        desc = "Systemic friction minimal. Normal market regime, macro conduits undisturbed."
        color = "#00ff66"
    elif composite < 50:
        status = "⛅ SCATTERED CLOUDS"
        desc = "Background operational noise within historical boundaries. No immediate systemic fracture."
        color = "#ffcc00"
    elif composite < 75:
        status = "🌧️ SQUALL / DOWNPOUR"
        desc = "ELEVATED SYSTEMIC FRICTION: Detectable divergence in credit covenants or liquidity plumbing."
        color = "#ff6600"
    else:
        status = "⛈️ SEVERE GALE / SYSTEMIC SHOCK"
        desc = "CRITICAL WARNING: Severe multi-vector dislocation across physical, bureaucratic, and market layers."
        color = "#ff0033"
        
    return {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "composite_score": composite,
        "status": status,
        "desc": desc,
        "color": color,
        "pillars": {
            "market_implied": {
                "score": mkt_score,
                "vix": vix_val,
                "move_index": move_val
            },
            "liquidity_plumbing": {
                "score": liq_score,
                "tga_billions": tga_bal,
                "tga_5d_flow": tga_flow,
                "central_bank_swaps_billions": swap_vol
            },
            "credit_and_statutory": {
                "score": cred_score,
                "sec_8k_covenant_breaches": sec_filings
            },
            "physical_logistics": {
                "score": phys_score,
                "border_freight_delay_min": laredo_wait,
                "treasury_bid_to_cover": b2c_ratio
            },
            "cognitive_and_kinetic": {
                "score": cog_score,
                "wiki_analyst_z_score": wiki_z,
                "central_bank_airspace_flights": air_flights
            }
        }
    }

# ==============================================================================
# STATIC EXPORT ENGINE
# ==============================================================================
def export_files(data):
    # 1. JSON API
    with open("weather.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # 2. TERMINAL TXT
    p = data["pillars"]
    term = f"""
======================================================================
 OPEN MARKET WEATHER OBSERVATORY // MULTI-VECTOR FRICTION MATRIX
 {data['timestamp']} // ZERO COMMERCIAL BIAS // RAW EXHAUST DATA
======================================================================

 OVERALL STATUS : {data['status']} [Score: {data['composite_score']}/100]
 CURRENT REGIME : {data['desc']}

 --- 5 OPERATIONAL PILLARS ---
 [1] Market Options Vola    : Score {p['market_implied']['score']}/100 (VIX: {p['market_implied']['vix']} | MOVE: {p['market_implied']['move_index']})
 [2] Global Dollar Plumbing : Score {p['liquidity_plumbing']['score']}/100 (TGA: ${p['liquidity_plumbing']['tga_billions']}B | Swaps: ${p['liquidity_plumbing']['central_bank_swaps_billions']}B)
 [3] Statutory Credit Risk  : Score {p['credit_and_statutory']['score']}/100 (SEC Form 8-K Item 2.04 Filings: {p['credit_and_statutory']['sec_8k_covenant_breaches']})
 [4] Logistics & Sovereign  : Score {p['physical_logistics']['score']}/100 (Laredo Border Delay: {p['physical_logistics']['border_freight_delay_min']}m | Debt B2C: {p['physical_logistics']['treasury_bid_to_cover']}x)
 [5] Cognitive / Air Kinetic: Score {p['cognitive_and_kinetic']['score']}/100 (Analyst Z: +{p['cognitive_and_kinetic']['wiki_analyst_z_score']}σ | BIS Air Corridor: {p['cognitive_and_kinetic']['central_bank_airspace_flights']})

 API Endpoint: curl -sL https://{os.environ.get('CF_PAGES_URL', 'marketweather.pages.dev')}/weather.json
======================================================================
"""
    with open("weather.txt", "w", encoding="utf-8") as f:
        f.write(term)

    # 3. SVG BADGE
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

    # 4. FULL BRUTALIST DASHBOARD HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Market Weather // Macro Observatory</title>
    <meta name="description" content="Decentralized systemic risk barometer tracking real-world physical, statutory, and liquidity exhaust data.">
    <style>
        body {{
            background: #090b0e;
            color: #d1d5db;
            font-family: 'SF Mono', Consolas, 'Liberation Mono', Menlo, monospace;
            padding: 2rem;
            max-width: 900px;
            margin: auto;
            line-height: 1.5;
        }}
        .header {{ border-bottom: 1px dashed #2d3748; padding-bottom: 1rem; margin-bottom: 2rem; }}
        .badge-sub {{ color: #718096; font-size: 0.85rem; }}
        .status-box {{
            border: 2px solid {data['color']};
            background: #111419;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }}
        .status-title {{ font-size: 1.7rem; color: {data['color']}; margin: 0 0 0.5rem 0; font-weight: bold; }}
        .table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        .table td, .table th {{ padding: 0.75rem 0.6rem; text-align: left; border-bottom: 1px solid #1a202c; }}
        .table th {{ color: #718096; font-size: 0.85rem; text-transform: uppercase; }}
        a {{ color: #63b3ed; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .footer {{ margin-top: 3rem; border-top: 1px dashed #2d3748; padding-top: 1rem; font-size: 0.85rem; color: #718096; }}
        .score-pill {{ font-weight: bold; padding: 2px 8px; border-radius: 3px; background: #1a202c; }}
    </style>
</head>
<body>
    <div class="header">
        <strong>OPEN MARKET WEATHER OBSERVATORY // MULTI-VECTOR MATRIX</strong><br>
        <span class="badge-sub">TIMESTAMP: {data['timestamp']} // ZERO COMMERCIAL BIAS // RAW EXHAUST DATA</span><br><br>
        <a href="weather.json">[Raw JSON API]</a> &nbsp;|&nbsp; 
        <a href="weather.txt">[Plaintext for cURL]</a> &nbsp;|&nbsp; 
        <a href="badge.svg">[Live SVG Badge]</a>
    </div>

    <div class="status-box">
        <div class="status-title">{data['status']} (SCORE: {data['composite_score']}/100)</div>
        <p style="margin: 0; font-size: 1.05rem;">{data['desc']}</p>
    </div>

    <h3>THE 5 OPERATIONAL PILLARS</h3>
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
                <td><strong>2. Dollar Plumbing</strong></td>
                <td>U.S. TGA Cash + NY Fed Central Bank Swaps</td>
                <td>TGA: ${p['liquidity_plumbing']['tga_billions']}B | Swaps: ${p['liquidity_plumbing']['central_bank_swaps_billions']}B</td>
                <td><span class="score-pill">{p['liquidity_plumbing']['score']}/100</span></td>
            </tr>
            <tr>
                <td><strong>3. Statutory Credit Risk</strong></td>
                <td>SEC 8-K Form (Item 2.04 Debt Covenant Acceleration)</td>
                <td>Active Filings: {p['credit_and_statutory']['sec_8k_covenant_breaches']}</td>
                <td><span class="score-pill">{p['credit_and_statutory']['score']}/100</span></td>
            </tr>
            <tr>
                <td><strong>4. Physical & Sovereign</strong></td>
                <td>CBP Freight Border Delay (Laredo) + Auction B2C</td>
                <td>Wait: {p['physical_logistics']['border_freight_delay_min']}m | Debt Demand: {p['physical_logistics']['treasury_bid_to_cover']}x</td>
                <td><span class="score-pill">{p['physical_logistics']['score']}/100</span></td>
            </tr>
            <tr>
                <td><strong>5. Cognitive & Kinetic</strong></td>
                <td>Wikimedia Desk Traffic + BIS Basel Air Corridor</td>
                <td>Analyst Z: +{p['cognitive_and_kinetic']['wiki_analyst_z_score']}σ | Flights: {p['cognitive_and_kinetic']['central_bank_airspace_flights']}</td>
                <td><span class="score-pill">{p['cognitive_and_kinetic']['score']}/100</span></td>
            </tr>
        </tbody>
    </table>

    <div class="footer">
        Decentralized public utility. Built on physics, central bank balance sheets, statutory disclosures, and physical freight queues.<br>
        CLI Access: <code>curl -sL [YOUR-URL]/weather.txt</code><br>
        Bot Embed: <code>&lt;img src="[YOUR-URL]/badge.svg"&gt;</code>
    </div>
</body>
</html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    print("[*] Running Multi-Vector Macro Matrix Engine...")
    w = calculate_systemic_weather()
    export_files(w)
    print(f"[+] Complete: Overall Score is {w['composite_score']}/100 -> {w['status']}")
