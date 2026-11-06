# ==============================================================================
# EXPORT ENGINE (MIT VOLLER MOBILE-OPTIMIERUNG)
# ==============================================================================
def export_files(data):
    p = data["pillars"]
    t = data["tactical_posture"]
    
    # 1. JSON
    with open("weather.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # 2. TERMINAL TXT
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
 [2] Dark Pool Short Ratio  : Score {p['dark_pool_finra']['score']}/100 (SPY Off-Exchange Short: {p['dark_pool_finra']['spy_short_volume_ratio']}%)
 [3] Global Dollar Plumbing : Score {p['liquidity_plumbing']['score']}/100 (TGA: ${p['liquidity_plumbing']['tga_billions']}B | Swaps: ${p['liquidity_plumbing']['swaps_billions']}B)
 [4] Statutory Credit Risk  : Score {p['credit_statutory']['score']}/100 (SEC 8-K Accelerations: {p['credit_statutory']['sec_8k_filings']})
 [5] Cognitive & Logistics  : Score {p['cognitive_physical']['score']}/100 (Analyst Z: +{p['cognitive_physical']['wiki_z']}σ | Border: {p['cognitive_physical']['border_wait_m']}m)

 API: curl -sL https://{os.environ.get('CF_PAGES_URL', 'marketweather.pages.dev')}/weather.json
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

    # 4. MOBILE-OPTIMIZED HTML
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

        /* --- MOBILE SCREEN MEDIA QUERY (SMARTPHONES) --- */
        @media (max-width: 640px) {{
            body {{ padding: 1rem 0.75rem; }}
            .status-symbol {{ font-size: 3.2rem; }}
            .status-title {{ font-size: 1.3rem; }}
            .status-desc {{ font-size: 0.85rem; }}
            
            /* Stapelung der Tactical Posture auf kleinen Bildschirmen */
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
                    <td>Short Ratio: {p['dark_pool_finra']['spy_short_volume_ratio']}% (NMS)</td>
                    <td><span class="score-pill">{p['dark_pool_finra']['score']}/100</span></td>
                </tr>
                <tr>
                    <td><strong>3. Dollar Plumbing</strong></td>
                    <td>U.S. TGA Cash + NY Fed Central Bank Swaps</td>
                    <td>TGA: ${p['liquidity_plumbing']['tga_billions']}B | Swaps: ${p['liquidity_plumbing']['swaps_billions']}B</td>
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
