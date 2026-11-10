# open-market-weather

A weather report for the markets. One Python script pulls a handful of public data feeds, squeezes them into a single score between 0 and 100 and shows it the way a weather app would: ☀️ when things look calm, ⛈️ when they don't.

I built it for my own Hyperliquid grid bot. Before the bot keeps buying dips, it can check whether something odd is going on in the wider market. It's a rough heuristic: the weights are my guesses and I haven't backtested any of it. Please don't treat it as a trading signal.

- Dashboard: https://open-market-weather.hartmut-nese.workers.dev
- JSON: https://open-market-weather.hartmut-nese.workers.dev/weather.json
- Plain text: `curl -sL https://open-market-weather.hartmut-nese.workers.dev/weather.txt`

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

## Why weather?

RSI, moving averages and Bollinger bands are calculated from price, so they only tell me what price has already done. I wanted a few signals from the plumbing around the market instead: how crowded derivatives traders are, how much cash the Treasury is sitting on, whether trucks are stuck at the border. None of these predicts anything on its own. Together they give me a rough feel for whether today is a good day to run a tight grid.

I run a perpetual grid bot on Hyperliquid. After watching it blindly catch a cascade of falling knives during a macro-driven selloff that had nothing to do with crypto fundamentals, I realized the bot needed a simple way to read the room before deploying more capital.

## What goes into the score

| Pillar | Weight | What it looks at | Source |
| :--- | :--- | :--- | :--- |
| Market volatility | 20% | VIX and MOVE | Yahoo Finance (unofficial chart endpoint) |
| Crypto leverage | 20% | BTC perp funding (annualized) and BTC volatility | Hyperliquid, Deribit |
| Dark pool shorting | 15% | Short share of SPY volume | FINRA daily Reg SHO files |
| Dollar liquidity | 20% | Treasury General Account balance and how fast it moves, Fed FX swap usage | US Fiscal Data, NY Fed |
| Credit stress | 15% | 8-K filings mentioning Item 2.04 (debt acceleration) in the last 14 days | SEC EDGAR full-text search |
| Odds and ends | 10% | Wikipedia page views for crisis topics (bank run, CDS, circuit breaker, force majeure, bail-in, insolvency) against the previous three weeks, plus truck wait times in Laredo | Wikimedia, CBP |

Each pillar is mapped to 0–100 with plain clamped linear scaling (VIX, for example, runs from 12 to 35), and the six are combined using the weights above. No model, no fitting. Below 25 is sun, below 50 clouds, below 75 rain, above that a storm.

The daily FINRA file is around 15 MB, so the script reads it line by line instead of loading it into memory.

## Things to know before you trust it

- **Fallbacks.** If a feed fails, the script prints a warning and substitutes a hard-coded default (VIX 16.5, for example). The output doesn't always show that a value is a stand-in, so check the run log if a number looks suspiciously normal.
- **Short volume is noisy.** A big part of it is market makers hedging, not institutions betting against the market. I use it as a weak signal.
- **Treasury cash moves in both directions.** The liquidity score goes up when the balance changes a lot, whether it rises or falls.
- **Unofficial endpoints.** Yahoo, CBP and SEC full-text search aren't stable APIs and can break without notice.
- **Different clocks.** Crypto data is live. FINRA and Treasury numbers come once a day, with a lag.

## Run it

```bash
git clone https://github.com/hartmutnese-stack/open-market-weather.git
cd open-market-weather
python3 engine.py
```

Python 3.8+, standard library only. It writes `index.html`, `weather.json`, `weather.txt` and `badge.svg` into the current folder. I run it hourly via GitHub Actions and serve the files from Cloudflare, which costs me nothing.

## Using it in a bot

`weather.json` has a `tactical_posture` block with plain-language suggestions. The one for grid bots works like this:

- **PAUSED** if the crypto score is above 65 or the overall score is 65 or higher
- **ACTIVE** if the overall score is below 35, VIX is below 20 and the crypto score is below 40
- **CAUTION** otherwise

So a calm overall score can still end up on CAUTION, as in this trimmed example:

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

Here is how my bot reads it. If the request fails, it just carries on. Whether that's right for you is your call:

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
            await cancel_resting_bids_only()      # your own function
        elif status == "CAUTION":
            apply_grid_modifiers(spread_mult=1.25, size_mult=0.6)  # yours too
    except Exception:
        pass
```

## Contributing

If you have a better idea for the scoring curves or the weights, or some historical data to calibrate against, open an issue or a PR. I'd like to hear it.

## License

MIT
