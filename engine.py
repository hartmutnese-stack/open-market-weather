import json
import math
import os
import urllib.request
from datetime import datetime, timedelta

# --- KONFIGURATION & QUELLEN (100% FREI, KEIN API-KEY) ---
HEADERS = {"User-Agent": "OpenMarketWeatherObservatory/1.0 (opensource; contact@null.org)"}

def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"[!] Fehler bei {url}: {e}")
        return None

# 1. KOGNITIVER VEKTOR: Wikimedia Desktop-Traffic auf Krisenbegriffe
def get_wikimedia_score():
    articles = ["Bank_run", "Credit_default_swap"]
    today = datetime.utcnow()
    # Letzte 30 Tage als Baseline, die letzten 3 Tage als Signal
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
            
            # Z-Score: Wie viele Standardabweichungen weicht der Wert ab?
            z_score = (avg_recent - avg_base) / std_base
            anomalies.append(max(0.0, z_score))
            
    avg_z = sum(anomalies) / len(anomalies) if anomalies else 0.0
    # Normalisierung auf Skala 0 - 100
    score = min(100, int(avg_z * 25))
    return score, round(avg_z, 2)

# 2. LIQUIDITÄTS-VEKTOR: U.S. Treasury General Account (TGA)
def get_treasury_score():
    # US Fiscal Data API: Tägliches Liquiditäts-Konto der Fed
    url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/dts_table_1?sort=-record_date&page[size]=10"
    data = fetch_json(url)
    if data and "data" in data and len(data["data"]) >= 5:
        # Extrahiere Operating Cash Balance
        records = [float(row["close_today_bal"]) for row in data["data"] if "close_today_bal" in row]
        if len(records) >= 2:
            latest = records[0]
            five_days_ago = records[-1]
            # Schneller Abfluss oder massiver Entzug erzeugt Reibung
            change_billions = (latest - five_days_ago) / 1000
            
            # Starke Schwankungen (> 50 Mrd. USD in wenigen Tagen) belasten die Liquidität
            friction = min(100, int(abs(change_billions) * 1.5))
            return friction, round(latest / 1000, 1), round(change_billions, 1)
            
    return 20, 0.0, 0.0  # Fallback Normalwert

# --- BERECHNUNG DES GESAMT-WETTERS ---
def calculate_weather():
    wiki_score, wiki_z = get_wikimedia_score()
    tga_score, tga_bal, tga_change = get_treasury_score()
    
    # Gewichteter Gesamt-Index (0 - 100)
    composite = int((wiki_score * 0.4) + (tga_score * 0.6))
    
    if composite < 25:
        status = "☀️ RUHIGER HIMMEL"
        desc = "Systemische Friktion minimal. Normale Marktphasen, Liquidität stabil."
        color = "#00ff66"
    elif composite < 50:
        status = "⛅ LEICHTE BEWÖLKUNG"
        desc = "Hintergrundrauschen im Normbereich. Keine akuten Schockmuster erkannt."
        color = "#ffcc00"
    elif composite < 75:
        status = "🌧️ DAUERREGEN / BÖEN"
        desc = "Erhöhter Druck: Ungewöhnliche Liquiditätsbewegungen oder kognitiver Stress messbar."
        color = "#ff6600"
    else:
        status = "⛈️ SCHWERES UNWETTER"
        desc = "WARNUNG: Massive Anomalien in den Systemdaten. Hohe Wahrscheinlichkeit schlagartiger Volatilität."
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
            "treasury_tga_billions": tga_bal,
            "treasury_5d_flow_billions": tga_change,
            "treasury_friction_score": tga_score
        }
    }

# --- GENERIERUNG DER STATISCHEN DATEIEN ---
def generate_outputs(data):
    # 1. RAW JSON
    with open("weather.json", "w") as f:
        json.dump(data, f, indent=2)

    # 2. TERMINAL TXT (Für `curl marktwetter.org`)
    terminal_txt = f"""
======================================================================
 OPEN MARKET WEATHER OBSERVATORY // RAW SYSTEMIC FRICTION
 {data['timestamp']} // HOSTED ON FREE-TIER COMPUTE // NO ADS
======================================================================

 STATUS: {data['status']} [Score: {data['composite_score']}/100]
 DETAIL: {data['desc']}

 --- SEISMISCHE VEKTOREN ---
 [Kognitiv]  Analysten-Recherche Spike:  Z-Score: +{data['signals']['analyst_panic_z_score']}σ (Score: {data['signals']['analyst_panic_score']}/100)
 [Liquidity] US Treasury Cash Balance:   ${data['signals']['treasury_tga_billions']} Mrd. (5T-Delta: {data['signals']['treasury_5d_flow_billions']} Mrd.)

 API: curl https://marktwetter.org/weather.json
======================================================================
"""
    with open("weather.txt", "w", encoding="utf-8") as f:
        f.write(terminal_txt)

    # 3. SEMANTISCHES BRUTALIST HTML
    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Marktwetter // Unabhängiges Volatilitäts-Observatorium</title>
    <meta name="description" content="Ein offenes Barometer für systemische Marktvolatilität basierend auf unmanipulierbaren Rohdaten.">
    <!-- JSON-LD für Suchmaschinen / Schema.org -->
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
            max-width: 800px;
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
        .table td, .table th {{ padding: 0.6rem; text-align: left; border-bottom: 1px solid #1f2937; }}
        .table th {{ color: #9ca3af; }}
        a {{ color: #60a5fa; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .footer {{ margin-top: 3rem; border-top: 1px dashed #374151; padding-top: 1rem; font-size: 0.85rem; color: #6b7280; }}
    </style>
</head>
<body>
    <div class="header">
        <strong>OPEN MARKET WEATHER OBSERVATORY</strong><br>
        <span class="badge">STAND: {data['timestamp']} // E2.MICRO ENGINE // ZERO COMMERCIAL BIAS</span><br>
        <a href="weather.json">[Raw JSON API]</a> | <a href="weather.txt">[Plaintext for cURL]</a>
    </div>

    <div class="status-box">
        <div class="status-title">{data['status']} ({data['composite_score']}/100)</div>
        <p>{data['desc']}</p>
    </div>

    <h3>SYSTEMISCHE VEKTOREN (ROHDATEN)</h3>
    <table class="table">
        <thead>
            <tr>
                <th>Vektor</th>
                <th>Messwert</th>
                <th>Zustand</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Analysten-Recherche</strong><br><small>Wikimedia Desktop Traffic</small></td>
                <td>Z-Score: +{data['signals']['analyst_panic_z_score']}σ</td>
                <td>Score: {data['signals']['analyst_panic_score']}/100</td>
            </tr>
            <tr>
                <td><strong>US-Girokonto (TGA)</strong><br><small>Treasury Operating Balance</small></td>
                <td>${data['signals']['treasury_tga_billions']} Mrd. (5T: {data['signals']['treasury_5d_flow_billions']} Mrd.)</td>
                <td>Score: {data['signals']['treasury_friction_score']}/100</td>
            </tr>
        </tbody>
    </table>

    <div class="footer">
        Freies Web-Projekt. Keine Anlageberatung. Basiert auf öffentlichen Behörden- und Physikschnittstellen.<br>
        Terminal: <code>curl https://marktwetter.org/weather.txt</code>
    </div>
</body>
</html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    print("[*] Erfasse Daten...")
    weather = calculate_weather()
    generate_outputs(weather)
    print(f"[+] Fertig: Status ist {weather['status']} ({weather['composite_score']}/100)")
