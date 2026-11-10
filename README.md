# open-market-weather

A lightweight, zero-dependency Python script that aggregates unconventional public data sources (FINRA dark pool short volume, U.S. Treasury cash balances, CBP freight delays, SEC 8-K filings, and crypto perps leverage) into a single heuristic market friction index.

Designed as an external, zero-cost circuit breaker for automated trading systems (e.g., perpetual grid bots).

* **Live Dashboard:** [https://open-market-weather.hartmut-nese.workers.dev](https://open-market-weather.hartmut-nese.workers.dev)
* **Raw JSON API:** `https://open-market-weather.hartmut-nese.workers.dev/weather.json`
* **Plaintext CLI:** `curl -sL https://open-market-weather.hartmut-nese.workers.dev/weather.txt`

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Dependencies](https://img.shields.io/badge/Dependencies-Zero%20(stdlib%20only)-green.svg)]()
[![Infrastructure Cost](https://img.shields.io/badge/Hosting%20Cost-$0%20(Pages%20+%20Actions)-black.svg)]()

---

## Motivation

Most automated retail trading strategies (like grid bots or DCA algorithms) fail during structural regime shifts. They operate on L2 order books with narrow horizon visibility, making them susceptible to liquidation cascades or macro liquidity drains.

Traditional market indicators (RSI, moving averages, Bollinger Bands) are derived directly from the price action they attempt to predict. Conversely, institutional risk tools cost thousands of dollars a month and are locked behind enterprise contracts.

This project monitors operational and regulatory byproduct data that institutions and central entities cannot easily disguise:
* Physical freight gridlocks at border crossings
* Rapid drains in the U.S. Treasury General Account (TGA)
* Off-exchange short volume ratios filed with FINRA
* Statutory disclosures regarding accelerated debt covenants (SEC Form 8-K)
* 24/7 perpetual futures funding and implied volatility spikes (Deribit/Hyperliquid)

The script normalizes these disparate inputs into a single 0–100 heuristic index and serves static output files to Cloudflare Pages edge nodes via GitHub Actions.

---

## Data Sources & Mechanics

| Vector | Metric | Source | Mechanism / Endpoint |
| :--- | :--- | :--- | :--- |
| **TradFi Derivatives** | Implied volatility | CBOE / Financial APIs | S&P 500 VIX and U.S. Treasury MOVE index |
| **Crypto Leverage (24/7)** | Funding rates & implied volatility | Hyperliquid Native API & Deribit REST | BTC perpetual hourly funding (annualized APR) + Deribit DVOL index |
| **Dark Pool Shorting** | Consolidated off-exchange short ratio | FINRA Reg SHO (`cdn.finra.org`) | Line-by-line stream of daily NMS flat files filtering `$SPY` volume |
| **Dollar Plumbing** | Sovereign cash balance & FX swaps | U.S. Fiscal Data Service & NY Fed | DTS Table 1 closing balance + Central Bank Liquidity Swap line utilization |
| **Credit Stress** | Material debt accelerations | SEC EDGAR Full-Text Search | Rolling 14-day count of 8-K filings citing Item 2.04 (Covenant breaches) |
| **Friction / Logistics** | Chokepoint delays & cognitive load | U.S. Customs (CBP) & Wikimedia REST API | Real-time commercial truck wait times (Laredo, TX) + 30-day desktop user Z-score across crisis terminology |

---

## Engineering Constraints

* **Zero External Dependencies:** Built strictly using Python's standard library (`urllib.request`, `json`, `math`, `datetime`). No `pandas`, `numpy`, or `requests`.
* **Low Memory Footprint:** The 15 MB daily FINRA text file is streamed line-by-line over HTTP, isolating the target ticker without allocating the entire dataset into memory. Peak RAM consumption is `< 25 MB`.
* **Fully Static Edge Serving:** Compute is decoupled from hosting. The script outputs static artifacts (`index.html`, `weather.json`, `weather.txt`, `badge.svg`) that deploy across Cloudflare edge nodes with zero compute overhead on page load.
* **Cost:** $0. Runs entirely within the free tiers of GitHub Actions and Cloudflare.

---

## Quickstart

Run locally (requires Python 3.8+):

```bash
git clone https://github.com/hartmutnese-stack/open-market-weather.git
cd open-market-weather
python3 engine.py
```

This fetches current upstream feeds and generates `index.html`, `weather.json`, and `weather.txt` in the root directory.

---

## API & Bot Integration

The engine outputs structured operational directives targeted at automated execution engines:

```bash
curl -sL https://open-market-weather.hartmut-nese.workers.dev/weather.json
```

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
    },
    "dip_buying": {
      "status": "FAVORABLE",
      "action": "Orderly pullbacks. Liquidity supports absorption."
    },
    "crypto_perps": {
      "status": "NOMINAL",
      "action": "Healthy derivatives leverage (BTC Funding: +5.8% APR)."
    },
    "dark_pool": {
      "status": "NOMINAL",
      "action": "Balanced flow (42.7% SVR on SPY)."
    },
    "collateral": {
      "status": "STABLE",
      "action": "No central bank emergency swap usage. Conduits clear."
    }
  }
}
```

### Async Consumer Example (`aiohttp`)

```python
import aiohttp
import asyncio

async def check_macro_circuit_breaker():
    url = "https://open-market-weather.hartmut-nese.workers.dev/weather.json"
    timeout = aiohttp.ClientTimeout(total=2.0)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    bot_status = data["tactical_posture"]["grid_bots"]["status"]
                    
                    if bot_status == "PAUSED":
                        # Immediate risk reduction: cancel bids, preserve limit asks
                        await cancel_resting_bids_only()
                    elif bot_status == "CAUTION":
                        # Adapt to wider dispersion
                        apply_grid_modifiers(spread_mult=1.25, size_mult=0.6)
        except Exception:
            # Fallback safely: network issues should not halt active execution loops
            pass
```

---

## Notes on Methodology & Limitations

The composite index is a pragmatic, rule-of-thumb scoring system configured for personal risk management, **not an econometrically backtested predictive model**:

1. **Normalization:** Individual metrics are mapped to 0–100 ranges via linear and clamped scaling against historical standard levels (e.g., VIX bounded between 12 and 35, baseline FINRA short ratio centered around 45–50%).
2. **Weighting:** The 6-pillar weights (Market: 20%, Crypto: 20%, Dark Pool: 15%, Liquidity: 20%, Credit: 15%, Physical/Cognitive: 10%) are hand-tuned heuristics intended to balance slow-moving fiscal plumbing with 24/7 derivatives leverage.
3. **Data Availability:** TradFi sources update on U.S. business day cycles, while crypto metrics reflect real-time 24/7 state. The index bridges this gap by weighting crypto perpetuals and volatility continuously.

Pull requests and discussions regarding alternative normalization curves, PCA weighting, or broader historical calibration datasets are welcome.

---

## License

MIT
