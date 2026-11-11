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
| Crypto leverage | 20% | BTC perp funding (annualized) and BTC implied volatility (DVOL) | Hyperliquid, Deribit |
| Short volume | 15% | Short share of SPY volume | FINRA daily Reg SHO files |
| Dollar liquidity | 20% | Treasury General Account balance and how fast it moves, Fed FX swap line usage | US Fiscal Data, NY Fed |
| Credit stress | 15% | 8-K filings mentioning Item 2.04 (debt acceleration) in the last 14 days | SEC EDGAR full-text search |
| Odds and ends | 10% | Wikipedia crisis traffic (6%) + truck wait times in Laredo (4%) | Wikimedia, CBP |

Each pillar is mapped to 0–100 with simple clamped scaling. VIX, for example, runs from 12 to 35, and BTC funding is only scored by how far it sits from Hyperliquid's baseline of about 11% APR. The six pillars are combined using the weights above. No model, no fitting. Below 25 is clear, below 50 scattered clouds, below 75 rain, above that a storm.

The daily FINRA file is around 15 MB, so the script streams it line by line instead of loading it into memory.

## Things to know before you trust it

- **Thresholds are guesses.** All the scaling ranges and cutoffs are hand-picked. Short volume and credit stress in particular can sit high in normal times. Every run appends the raw values to `history.csv`, so I can calibrate against real history later.
- **Short volume is noisy.** Much of it is routine market maker hedging rather than directional bets. I use it as a weak signal.
- **Treasury cash moves both ways.** The liquidity score goes up on large swings in either direction, whether the government is draining or injecting reserves. Swap line usage below $1B counts as noise.
- **Wikipedia is experimental.** I compare the last 7 days of page views with the three weeks before, so the weekend dip cancels out. It still follows school terms and news cycles, which is why it only gets 6% of the total (60% of a pillar worth 10%).
- **Different clocks.** Crypto data is real-time. FINRA and Treasury numbers arrive once a day with a lag.
- **Unofficial endpoints.** Yahoo, CBP and SEC search aren't stable APIs and can break without notice.
- **Fallbacks.** If a feed fails, the script retries once and then uses a hard-coded default (like VIX 16.5). `weather.json` lists affected pillars under `fallback_flags`, the pillar entries show which feed it was (`tga_fallback`, `cbp_fallback` and so on), and the dashboard shows tags like `[fallback: tga, ny fed]`. While any feed is on fallback data, the grid bot status never reaches ACTIVE. In `history.csv` those values are left empty.

## Run it

```bash
git clone https://github.com/hartmutnese-stack/open-market-weather.git
cd open-market-weather
python3 engine.py
```

Python 3.8+, standard library only. It writes `index.html`, `weather.json`, `weather.txt` and `badge.svg` into the current folder and appends a row to `history.csv`. I run it hourly via GitHub Actions and serve the files from Cloudflare for free. `history.csv` only keeps growing if your workflow commits it back to the repo.

Two optional environment variables:

- `OMW_CONTACT`: a contact string for the User-Agent sent to SEC EDGAR and Wikimedia, ideally an e-mail address. Both ask for one and may block requests without it. Set this if you fork it.
- `OMW_BASE_URL`: the public URL of your deployment. The script reads the previous state from there when there is no recent local `weather.json`.

## Using it in a bot

`weather.json` includes a `tactical_posture` block with plain-language suggestions for trading bots. For grid bots it works like this:

- **PAUSED** if the crypto score is above 65 or the overall score is 65 or higher.
- **ACTIVE** if the overall score is below 35, VIX is below 20, the crypto score is below 40, and no feed is on fallback data.
- **CAUTION** for anything in between.

To keep the status from flipping back and forth around a threshold, leaving CAUTION or PAUSED takes clearer readings than entering. Going back to ACTIVE needs an overall score below 28, VIX below 18.5 and a crypto score below 35. PAUSED holds until both the overall and the crypto score are below 58. When this rule is what keeps the status where it is, `hysteresis` is `true`. The script gets the previous status from the local `weather.json` or from the live site, and ignores it if it is older than three hours.

A calm overall score can still land on CAUTION if VIX is above 20 or crypto leverage is elevated, as in this trimmed example:

```json
{
  "version": "3.5",
  "timestamp": "2026-11-09 08:36 UTC",
  "symbol": "☀️",
  "composite_score": 19,
  "status": "CLEAR SKIES",
  "fallback_flags": {
    "market_volatility": false,
    "crypto_leverage": false,
    "short_volume": false,
    "dollar_liquidity": false,
    "credit_stress": false,
    "odds_and_ends": false
  },
  "tactical_posture": {
    "grid_bots": {
      "status": "CAUTION",
      "action": "Widen grid bands by 15-25%. Reduce leverage / lot sizes.",
      "hysteresis": false
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

The other entries in `tactical_posture` (dip buying, crypto perps, short volume, collateral) are plain status labels. Their `status` values can change between versions, so don't hard-code too much around them.

## Contributing

If you have ideas for better normalization curves, cleaner weights, or historical data to calibrate against, open an issue or a PR.

## License

MIT
