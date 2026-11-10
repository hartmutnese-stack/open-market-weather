# open-market-weather

A weather report for the markets. One Python script pulls a handful of public data feeds, squeezes them into a single score between 0 and 100, and displays it the way a weather app would: ☀️ when things look calm, ⛈️ when they don't.

I built it for my own grid bot on Hyperliquid. Before it keeps buying dips, it checks macro plumbing and crypto leverage to see if something odd is going on. It's a rough heuristic: the weights are my own guesses and I haven't backtested any of it. Please don't treat it as a trading signal.

- Dashboard: https://open-market-weather.hartmut-nese.workers.dev
- JSON: https://open-market-weather.hartmut-nese.workers.dev/weather.json
- Plain text: `curl -sL https://open-market-weather.hartmut-nese.workers.dev/weather.txt`

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

## Why a weather report instead of charts?

RSI, moving averages and Bollinger bands only show what price has already done. Sometimes a shock starts in traditional markets, and a grid bot only sees an attractive dip and keeps buying on the way down.

I'm not trying to predict prices. It's like checking for an umbrella before leaving the house: I just want to know whether the market is calm enough for a grid to work, or whether a storm is coming that will run over my resting bids.

## What goes into the score

| Pillar | Weight | What it looks at | Source |
| :--- | :--- | :--- | :--- |
| Market volatility | 20% | VIX and MOVE | Yahoo Finance (unofficial chart endpoint) |
| Crypto leverage | 20% | BTC perp funding (annualized) and BTC volatility | Hyperliquid, Deribit |
| Dark pool shorting | 15% | Short share of SPY volume | FINRA daily Reg SHO files |
| Dollar liquidity | 20% | Treasury General Account balance and how fast it moves, Fed FX swap usage | US Fiscal Data, NY Fed |
| Credit stress | 15% | 8-K filings citing Item 2.04 (debt acceleration) in the last 14 days | SEC EDGAR full-text search |
| Odds and ends | 10% | Wikipedia crisis traffic (6%) + truck wait times in Laredo (4%) | Wikimedia, CBP |

Each pillar maps to 0–100 via clamped linear scaling (VIX, for example, runs from 12 to 35). The six are combined using the weights above. No model, no fitting. Below 25 is clear, below 50 scattered clouds, below 75 rain, above that a storm.

The daily FINRA file is around 15 MB, so the script streams it line by line instead of loading it into memory.

## Things to know before you trust it

- **Short volume is noisy.** Much of it is routine market maker hedging rather than directional bets. I use it as a weak signal.
- **Treasury cash moves both ways.** The liquidity score spikes on large swings in either direction, whether the government is draining or injecting reserves.
- **Wikipedia is experimental.** Page views drop on weekends and follow school terms, so I keep its weight small: 60% of a pillar that is worth 10%, which makes 6% of the total.
- **Different clocks.** Crypto data is real-time. FINRA and Treasury numbers arrive once a day with a lag.
- **Fallbacks and unofficial endpoints.** Yahoo, CBP and SEC search are unofficial interfaces that can break. If a feed fails, the script substitutes a hard-coded default (like VIX 16.5). The `weather.json` payload flags active fallbacks under `fallback_flags`, and the dashboard displays `[fallback]` next to affected values.

## Run it

```bash
git clone https://github.com/hartmutnese-stack/open-market-weather.git
cd open-market-weather
python3 engine.py
```

Python 3.8+, standard library only. It writes `index.html`, `weather.json`, `weather.txt`, and `badge.svg` into the current folder. I run it hourly via GitHub Actions and serve it from Cloudflare for free.

## Using it in a bot

`weather.json` includes a `tactical_posture` block with plain-language suggestions for trading bots. For grid bots, it works like this:

- **PAUSED** if the crypto score is above 65 or the overall score is 65 or higher.
- **ACTIVE** if the overall score is below 35, VIX is below 20, and the crypto score is below 40.
- **CAUTION** for anything in between.

A calm overall score can still land on CAUTION if VIX is above 20 or crypto leverage is elevated, as in this trimmed example:

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

Here is how my bot reads it. If the request fails, it carries on:

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

If you have ideas for better normalization curves, cleaner weights, or historical data to calibrate against, open an issue or a PR.

## License

MIT
