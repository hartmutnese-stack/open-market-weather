# open-market-weather

A weather report for the markets. One Python script pulls a handful of public data feeds, squeezes them into a single score between 0 and 100, and displays it the way a weather app would: ☀️ when things look calm, ⛈️ when they don't.

I built it for my own grid bot on Hyperliquid. Before it keeps deploying capital into a dropping market, it checks whether something odd is brewing in the plumbing outside of crypto. It's a rough heuristic: the weights are my own estimates and I haven't backtested any of it. Please don't treat it as a trading signal.

- Dashboard: https://open-market-weather.hartmut-nese.workers.dev
- JSON: https://open-market-weather.hartmut-nese.workers.dev/weather.json
- Plain text: `curl -sL https://open-market-weather.hartmut-nese.workers.dev/weather.txt`

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

## Why a weather report instead of charts?

RSI, moving averages, and Bollinger bands only show what price has already done. When a macro shock starts in traditional markets, crypto order books often react with a delay—meaning a grid bot just sees an attractive dip and buys all the way down. 

A weather metaphor fits because I don't care about predicting exact prices. Just like checking whether to take an umbrella before leaving the house, I only need to know whether the regime is calm enough for mean-reversion, or whether a squall is coming where resting bids are likely to get run over.

## What goes into the score

| Pillar | Weight | What it looks at | Source |
| :--- | :--- | :--- | :--- |
| Market volatility | 20% | VIX and MOVE | Yahoo Finance (unofficial chart endpoint) |
| Crypto leverage | 20% | BTC perp funding (annualized) and BTC volatility | Hyperliquid, Deribit |
| Dark pool shorting | 15% | Short share of SPY volume | FINRA daily Reg SHO files |
| Dollar liquidity | 20% | Treasury General Account balance and its rate of change, Fed FX swap usage | US Fiscal Data, NY Fed |
| Credit stress | 15% | 8-K filings citing Item 2.04 (debt acceleration) over the past 14 days | SEC EDGAR full-text search |
| Odds and ends | 10% | Wikipedia page views for crisis topics (bank run, CDS, circuit breaker, force majeure, bail-in, insolvency) against their 3-week baseline, plus truck wait times in Laredo | Wikimedia, CBP |

Each pillar maps to 0–100 via clamped linear scaling (e.g. VIX scales from 12 to 35). The six are combined using the weights above—no machine learning, no curve fitting. Below 25 is clear, below 50 scattered clouds, below 75 rain, and above that a storm warning.

The daily FINRA file is around 15 MB, so the script streams it line by line instead of loading it into memory.

## Things to know before you trust it

A lot of FINRA short volume is routine market maker hedging rather than directional speculation, so treat it as a noisy, weak signal. Similarly, Treasury liquidity triggers on volatility in either direction: the score spikes on sharp balance changes whether the government is draining or injecting reserves.

The feeds also run on completely different clocks. Crypto leverage updates continuously, while Treasury and FINRA reports only arrive once a day after market close. Furthermore, the Wikipedia crisis-traffic feed is experimental—page views naturally dip on weekends and fluctuate with academic terms, which is why it only gets a 10% weight alongside the border wait times.

Lastly, several endpoints (Yahoo, CBP, and SEC full-text search) are undocumented public interfaces that can break at any time. When an upstream request fails, the script substitutes a hard-coded fallback (such as VIX 16.5) so the run completes. The dashboard won't explicitly highlight when a number is a fallback, so check the run logs if values look suspiciously stable.

## Run it

```bash
git clone https://github.com/hartmutnese-stack/open-market-weather.git
cd open-market-weather
python3 engine.py
```

Requires Python 3.8+ with standard library only. It writes `index.html`, `weather.json`, `weather.txt`, and `badge.svg` into the local directory. I run it hourly via GitHub Actions and serve the static files from Cloudflare Pages, which costs nothing.

## Using it in a bot

`weather.json` includes a `tactical_posture` block with plain-language directives. For grid bots, the logic works as follows:

- **PAUSED** if the crypto score is above 65 or the composite score is 65 or higher
- **ACTIVE** if the composite is below 35, VIX is below 20, and the crypto score is below 40
- **CAUTION** otherwise

A calm composite score can still trigger CAUTION if equity volatility is slightly elevated, as shown in this trimmed payload:

```json
{
  "timestamp": "2026-11-09 08:36 UTC",
  "symbol": "☀️",
  "composite_score": 19,
  "status": "CLEAR SKIES",
  "tactical_posture": {
    "grid_bots": {
      "status": "CAUTION",
      "action": "Widen grid bands by 15-25%. Reduce leverage / lot sizes."
    }
  }
}
```

Here is a simplified consumer example. If the request fails, the loop ignores it and continues:

```python
import aiohttp

async def check_macro_circuit_breaker():
    url = "https://open-market-weather.hartmut-nese.workers.dev/weather.json"
    timeout = aiohttp.ClientTimeout(total=2.0)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                data = await resp.json()
        status = data["tactical_posture"]["grid_bots"]["status"]
        if status == "PAUSED":
            await cancel_resting_bids_only()      # your own implementation
        elif status == "CAUTION":
            apply_grid_modifiers(spread_mult=1.25, size_mult=0.6)
    except Exception:
        pass
```

## Contributing

If you have ideas for better normalization curves, cleaner weightings, or historical datasets to calibrate against, feel free to open an issue or pull request.

## License

MIT
