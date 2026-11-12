 #!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OPEN MARKET WEATHER OBSERVATORY // HYBRID MACRO & CRYPTO
Version: 3.6.4 (stdlib only)

Changes in 3.6.4:
  - Wikipedia: a missing day is no longer always read as zero views. Whether an
    article has enough traffic is decided on the series with gaps counted as zero.
    For an article above that line a genuine zero day is practically impossible, so
    its gaps are treated as gaps: the z-score is computed from the days that are
    there, and the article is skipped when too many are missing. One missing day no
    longer collapses the z-score of a busy article.
  - Return-band text names data quality as well when both hold the status back.
  - Posture wording: the action texts describe reference settings instead of giving
    orders, and "Standard grid parameters" is now "No change to your usual grid
    settings". Status values and JSON structure are unchanged.

Changes in 3.6.3:
  - Wikipedia: the series is aligned by calendar day instead of by list position, and
    articles with too little traffic for a meaningful z-score are skipped with a log line.
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

import csv: symbol,
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
