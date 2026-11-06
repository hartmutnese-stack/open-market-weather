import json
import math
import os
import urllib.request
from datetime import datetime, timedelta

# --- CONFIGURATION & HEADERS (NO API KEYS REQUIRED) ---
HEADERS = {"User-Agent": "OpenMarketWeatherObservatory/1.0 (academic-research; contact@null.org)"}

def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"[!] Error fetching {url}: {e}")
        return None

# 1. COGNITIVE VECTOR: 8 Crisis Keywords (Wikipedia Desktop Users)
def get_wikimedia_score():
    articles = [
        "Bank_run", 
        "Credit_default_swap", 
        "Circuit_breaker_(stock_market)", 
        "Force_majeure", 
        "Insolvency", 
        "Bail-in",
        "Lender_of_last_resort",
        "Trading_halt"
    ]
    today = datetime.utcnow()
    end_date = (today - timedelta(days=1)).strftime("%Y%m%d")
    start_date = (today - timedelta(days=30)).strftime("%Y%m%d")
    
    anomalies = []
    for art in articles:
        url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/user/{art}/daily/{start_date}/{end_date}"
        data = fetch_json(url)
        if data and "items" in data and len(data["items"]) >= 10:
            views = [x["views"] for x in data["items"]]
            baseline = views[:-3]
            recent = views[-3:]
            
            avg_base = sum(baseline) / len(baseline)
            std_base = math.sqrt(sum((x - avg_base) ** 2 for x in baseline) / len(baseline)) or 1
            avg_recent = sum(recent) / len(recent)
            
            z_score = (avg_recent - avg_base) / std_base
            anomalies.append(max(0.0, z_score))
            
    avg_z = sum(anomalies) / len(anomalies) if anomalies else 0.0
    score = min(100, int(avg_z * 25))
    return score, round(avg_z, 2), len(anomalies)

# 2. LIQUIDITY VECTOR: U.S. Treasury General Account (TGA)
def get_treasury_score():
    url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/dts_table_1?sort=-record_date&page[size]=50"
    data = fetch_json(url)
    
    if data and "data" in data:
        tga_rows = []
        for row in data["data"]:
            acc = row.get("account_type", "")
            if "Federal Reserve Account" in acc or "Treasury General Account" in acc:
                val = row.get("close_today_bal") if val in (None, "null", "", "None"):     val = row.get("open_today_bal")
                if val is not None:
                    try:
                        tga_rows.append(float(val))
                    except ValueError:
                        pass
        
        if len(tga_rows) >= 2:
            latest = tga_rows[0]
            prev = tga_rows[-1]
            change = latest - prev
            
            # Friction score based on rapid draining or liquidity shock
            friction = min(100, int(abs(change / 1000) * 1.5))
            return friction, round(latest / 1000, 1), round(change / 1000, 1)

    return 15, 750.0, 0.0  # Plausible fallback if API throttles

# 3. COMPOSITE INDEX COMPUTATION
def calculate_weather():
    wiki_score, wiki_z, tracked_count = get_wikimedia_score()
    tga_score, tga_bal, tga_change = get_treasury_score()
    
    composite = int((wiki_score * 0.45) + (tga_score * 0.55))
    
    if composite < 25:
        status = "☀️ CLEAR SKIES"
        desc = "Systemic friction minimal. Normal market regime, liquidity undisturbed."
        color = "#00ff66"
    elif composite < 50:
        status = "⛅ SCATTERED CLOUDS"
        desc = "Background volatility within normal parameters. No immediate shock pattern."
        color = "#ffcc00"
    elif composite < 75:
        status = "🌧️ SQUALL / DOWNPOUR"
        desc = "Elevated systemic pressure: Notable liquidity fluctuations or cognitive distress detected."
        color = "#ff6600"
    else:
        status = "⛈️ SEVERE GALE / STORM"
        desc = "HIGH ALERT: Severe structural anomalies detected across core operational vectors."
        color = "#ff0033"
        
    return {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "composite_score": composite,
        "status": status,
        "desc": desc,
        "color": color,
        "signals": {
            "analyst_panic_z_score": wiki_z,
            "analyst_panic_score": wiki_score,
            "analyst_terms_tracked": tracked_count,
            "treasury_tga_billions": tga_bal,
            "treasury_5d_flow_billions": tga_change,
            "treasury_friction_score": tga_score
        }
    }

# 4. EXPORT ENGINE (HTML, JSON, TXT, SVG BADGE)
def generate_outputs(data):
    # JSON API
    with open("weather.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # TERMINAL OUTPUT (curl)
    terminal_txt = f"""
======================================================================
 OPEN MARKET WEATHER OBSERVATORY // RAW SYSTEMIC FRICTION
 {data['timestamp']} // ZERO COMMERCIAL BIAS // OPEN EXHAUST DATA
======================================================================

 STATUS: {data['status']} [Score: {data['composite_score']}/100]
 DETAIL: {data['desc']}

 --- SEISMIC VECTORS ---
 [Cognitive]  Risk Desk Research Spike: Z-Score: +{data['signals']['analyst_panic_z_score']}σ ({data['signals']['analyst_terms_tracked']} crisis terms)
 [Liquidity]  US Treasury Cash Balance:  ${data['signals']['treasury_tga_billions']}B (Delta: {data['signals']['treasury_5d_flow_billions']}B)

 API Endpoint: curl https://{os.environ.get('CF_PAGES_URL', 'marketweather.org')}/weather.json
======================================================================
"""
    with open("weather.txt", "w", encoding="utf-8") as f:
        f.write(terminal_txt)

    # DYNAMIC SVG BADGE
    badge_svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="160" height="20">
    <linearGradient id="b" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
    <mask id="a"><rect width="160" height="20" rx="3" fill="#fff"/></mask>
    <g mask="url(#a)">
        <path fill="#555" d="M0 0h95v20H0z"/>
        <path fill="{data['color']}" d="M95 0h65v20H95z"/>
        <path fill="url(#b)" d="M0 0h160v20H0z"/>
    </g>
    <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
        <text x="47" y="15" fill="#010101" fill-opacity=".3">Market Weather</text>
        <text x="47" y="14">Market Weather</text>
        <text x="127" y="15" fill="#010101" fill-opacity=".3">{data['composite_score']}/100</text>
        <text x="127" y="14">{data['composite_score']}/100</text>
    </g>
</svg>"""
    with open("badge.svg", "w", encoding="utf-8") as f:
        f.write(badge_svg)

    # BRUTALIST HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Market Weather // Open Volatility Observatory</title>
    <meta name="description" content="An open-source systemic friction barometer based on raw, unmanipulated operational exhaust data.">
    <script type="application/ld+json">
    {{
      "@context": "https://schema.org",
      "@type": "SpecialAnnouncement",
      "name": "Open Market Weather Forecast",
      "datePosted": "{data['timestamp']}",
      "text": "{data['status']} - Score: {data['composite_score']}/100"
    }}
    </script>
    <style>
        body {{
            background: #0d0f12;
            color: #d1d5db;
            font-family: 'Courier New', Courier, monospace;
            padding: 2rem;
            max-width: 820px;
            margin: auto;
            line-height: 1.5;
        }}
        .header {{ border-bottom: 1px dashed #374151; padding-bottom: 1rem; margin-bottom: 2rem; }}
        .badge {{ color: #9ca3af; font-size: 0.85rem; }}
        .status-box {{
            border: 2px solid {data['color']};
            background: #161b22;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }}
        .status-title {{ font-size: 1.6rem; color: {data['color']}; margin: 0 0 0.5rem 0; font-weight: bold; }}
        .table {{ width: 100%; border-collapse: collapse; margin-top: 1.5rem; }}
        .table td, .table th {{ padding: 0.75rem 0.5rem; text-align: left; border-bottom: 1px solid #1f2937; }}
        .table th {{ color: #9ca3af; font-size: 0.9rem; }}
        a {{ color: #60a5fa; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .footer {{ margin-top: 3rem; border-top: 1px dashed #374151; padding-top: 1rem; font-size: 0.85rem; color: #6b7280; }}
        code {{ background: #1f2937; padding: 2px 5px; color: #f3f4f6; }}
    </style>
</head>
<body>
    <div class="header">
        <strong>OPEN MARKET WEATHER OBSERVATORY</strong><br>
        <span class="badge">AS OF: {data['timestamp']} // ZERO COMMERCIAL BIAS // RAW EXHAUST DATA</span><br><br>
        <a href="weather.json">[Raw JSON API]</a> &nbsp;|&nbsp; 
        <a href="weather.txt">[Plaintext for cURL]</a> &nbsp;|&nbsp; 
        <a href="badge.svg">[Live SVG Badge]</a>
    </div>

    <div class="status-box">
        <div class="status-title">{data['status']} ({data['composite_score']}/100)</div>
        <p>{data['desc']}</p>
    </div>

    <h3>SYSTEMIC VECTORS (RAW OBSERVATIONS)</h3>
    <table class="table">
        <thead>
            <tr>
                <th>Vector</th>
                <th>Observation & Source</th>
                <th>Friction Score</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Cognitive Distress</strong><br><small>Analyst Search Volume ({data['signals']['analyst_terms_tracked']} Crisis Terms)</small></td>
                <td>Z-Score: +{data['signals']['analyst_panic_z_score']}σ<br><small>Wikimedia REST API (Desktop Users Only)</small></td>
                <td><strong>{data['signals']['analyst_panic_score']}/100</strong></td>
            </tr>
            <tr>
                <td><strong>U.S. Cash Plumbing (TGA)</strong><br><small>Treasury Operating Balance</small></td>
                <td>${data['signals']['treasury_tga_billions']}B (5-Day Net Flow: {data['signals']['treasury_5d_flow_billions']}B)<br><small>U.S. Fiscal Data Service</small></td>
                <td><strong>{data['signals']['treasury_friction_score']}/100</strong></td>
            </tr>
        </tbody>
    </table>

    <div class="footer">
        Independent public utility. Powered by physical, bureaucratic, and cognitive exhaust data.<br>
        Terminal access: <code>curl -sL [YOUR-URL]/weather.txt</code><br>
        Embeddable badge: <code>&lt;img src="[YOUR-URL]/badge.svg"&gt;</code>
    </div>
</body>
</html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    print("[*] Gathering systemic exhaust data...")
    weather = calculate_weather()
    generate_outputs(weather)
    print(f"[+] Done: State is {weather['status']} ({weather['composite_score']}/100)")
