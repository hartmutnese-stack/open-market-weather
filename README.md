# open-market-weather

A weather report for the markets. One Python script pulls a handful of public data feeds, squeezes them into a single score between 0 and 100, and displays it the way a weather app would: ☀️ when things look calm, ⛈️ when they don't.

I built it for my own grid bot on Hyperliquid. Before it keeps buying dips, it checks macro plumbing and crypto leverage to see if something odd is going on. It's a rough heuristic: the weights are my own guesses and I haven't backtested any of it. Please don't treat it as a trading signal or as financial advice.

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
| Dollar liquidity | 20% | Treasury General Account balance and how fast it moves, Fed FX swap operations | US Fiscal Data, NY Fed |
| Credit stress | 15% | 8-K filings mentioning Item 2.04 (debt acceleration) in the last 14 days | SEC EDGAR full-text search |
| Odds and ends | 10% | Wikipedia crisis traffic (6%) + truck wait times in Laredo (4%) | Wikimedia, CBP |

Each pillar is mapped to 0–100 with simple clamped scaling. VIX, for example, runs from 12 to 35, and BTC funding is only scored by how far it sits from Hyperliquid's baseline of about 11% APR. The six pillars are combined using the weights above. No model, no fitting.

The result is `composite_raw` with two decimals. `composite_score` is the same number rounded down. Below 25 is clear, below 50 scattered clouds, below 75 rain, above that a storm.

The daily FINRA file is around 15 MB, so the script streams it line by line instead of loading it into memory.

## Things to know before you trust it

- **Thresholds are guesses.** All the scaling ranges and cutoffs are hand-picked. Short volume and credit stress in particular can sit high in normal times. Every run appends the raw values to `history.csv`, so I can calibrate against real history later. Values that came from a fallback are left empty there.
- **Short volume is noisy.** Much of it is routine market maker hedging rather than directional bets. I use it as a weak signal.
- **Treasury cash moves both ways.** The liquidity score goes up on large swings in either direction, whether the government is draining or injecting reserves. Swap operations below $1B count as noise.
- **Wikipedia is experimental.** I compare the last 7 days of page views with the three weeks before, aligned by calendar day. Articles with very little traffic are skipped, so you may see something like `5/6 articles usable` in `feed_health`. It still follows school terms and news cycles, which is why it only gets 6% of the total (60% of a pillar worth 10%).
- **Border waits disappear at night.** The Laredo bridges report no delay times while they are closed. That counts as no border stress, shows up as `CLOSED` in `feed_health`, and `border_wait_m` is `null`. It is not treated as a failure.
- **Different clocks.** Crypto data is real-time. FINRA and Treasury numbers arrive once a day with a lag.
- **Unofficial endpoints.** Yahoo, CBP and SEC search aren't stable APIs and can break without notice.

## When a feed fails

Every feed in `feed_health` has one of four statuses:

- `OK`: all good.
- `FALLBACK`: the request failed. The script retried once, then used a hard-coded default (VIX 16.5, for example).
- `STALE`: the data arrived, but the newest point is older than it should be.
- `CLOSED`: the Laredo case from above.

Fallbacks are listed in `fallback_flags` and marked on the dashboard, with the feed named, like `[fallback: tga, ny fed]`. `data_quality` rolls everything up into `HIGH`, `MEDIUM` or `LOW`, and `run_status` says `COMPLETE` or `DEGRADED`.

While any feed is on fallback or stale data, the grid bot status can't be ACTIVE and dip buying stays DEFENSIVE. Files are written atomically, and if a run crashes, the previous files stay in place.

## Run it

```bash
git clone https://github.com/hartmutnese-stack/open-market-weather.git
cd open-market-weather
python3 engine.py
```

Python 3.8+, standard library only. It writes `index.html`, `weather.json`, `weather.txt` and `badge.svg` into the current folder and appends a row to `history.csv`. I run it hourly via GitHub Actions and serve the files from Cloudflare for free. `history.csv` only keeps growing if your workflow commits it back to the repo.

Optional environment variables:

- `OMW_CONTACT`: a contact string for the User-Agent sent to SEC EDGAR and Wikimedia, ideally an e-mail address. Both ask for one and may block requests without it. Set this if you fork it.
- `OMW_BASE_URL`: the public URL of your deployment. The script reads the previous state from there when there is no recent local `weather.json`.
- `OMW_REPO_URL`: the repository link shown on the dashboard.
- `OMW_VALID_FOR_HOURS` (default 2.5): how long a result counts as valid. This sets `valid_until`.
- `OMW_STATE_MAX_AGE_HOURS` (default 4): a previous state older than this is ignored.
- `OMW_RECOVERY_CONFIRMATIONS` (default 2): how many runs in a row must look calmer before the grid status steps down.
- `OMW_COLD_START_STATUS` (default `CAUTION`): the grid status assumed when there is no recent previous state. `ACTIVE`, `CAUTION` or `PAUSED`.

## Using it in a bot

`weather.json` includes a `tactical_posture` block with plain-language suggestions. For grid bots it works like this:

- **PAUSED** if the crypto score or the overall score is 65 or higher. It stays PAUSED until both are below 58.
- **ACTIVE** if the overall score is below 35, VIX is below 20, the crypto score is below 40, and the data quality is clean.
- **CAUTION** for anything in between.

Getting worse takes effect immediately. Getting better takes more. Going back from CAUTION or PAUSED needs an overall score below 28, VIX below 18.5 and a crypto score below 35, and that has to hold for two runs in a row. This keeps the status from flipping back and forth around a threshold. When it is holding the status back, `hysteresis` is `true`, and `transition` shows where the countdown stands.

The script gets the previous status from the local `weather.json` or from the live site, and ignores it if it is older than four hours. Without one, it assumes `CAUTION`.

So a sunny score can still land on CAUTION, as in this trimmed example:

```json
{
  "schema_version": 1,
  "version": "3.6.3",
  "generated_at": "2026-11-11T11:33:24Z",
  "valid_until": "2026-11-11T14:03:24Z",
  "run_status": "COMPLETE",
  "symbol": "☀️",
  "composite_score": 24,
  "composite_raw": 24.25,
  "status": "CLEAR SKIES",
  "data_quality": {
    "status": "HIGH",
    "score": 100,
    "fallback_count": 0,
    "stale_count": 0,
    "degraded_feeds": []
  },
  "tactical_posture": {
    "grid_bots": {
      "status": "CAUTION",
      "action": "Widen grid bands by 15-25%. Return band active (VIX 18.58 >= 18.5).",
      "hysteresis": true,
      "confirmed_runs": 0
    }
  }
}
```

The `pillars` object still repeats the old key names (`market_implied`, `crypto_247` and so on) next to the new ones, for anyone who reads them. Use the new ones, the old ones will go away.

Here is how my bot reads it. If the request fails or the result is past `valid_until`, it carries on as usual:

```python
import aiohttp
from datetime import datetime, timezone

async def check_macro_circuit_breaker():
    url = "https://open-market-weather.hartmut-nese.workers.dev/weather.json"
    timeout = aiohttp.ClientTimeout(total=2.0)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                data = await resp.json()
        valid_until = datetime.fromisoformat(data["valid_until"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > valid_until:
            return                                # stale result, ignore it
        status = data["tactical_posture"]["grid_bots"]["status"]
        if status == "PAUSED":
            await cancel_resting_bids_only()      # your own implementation
        elif status == "CAUTION":
            apply_grid_modifiers(spread_mult=1.25, size_mult=0.6)
    except Exception:
        pass
```

The other entries in `tactical_posture` (dip buying, crypto perps, short volume, collateral) are plain status labels. Their `status` values can change between versions, so don't hard-code too much around them.

## Disclaimer

This is a hobby project that reads public data. Nothing here is investment advice, a trading signal or an offer of any kind. The numbers can be late or wrong, so use it at your own risk.

## Contributing

If you have ideas for better normalization curves, cleaner weights, or historical data to calibrate against, open an issue or a PR.

## License

MIT
