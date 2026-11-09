# ⛅ Open Market Weather Observatory (OMWO)

> **A decentralized, non-commercial systemic friction barometer tracking TradFi macro plumbing and 24/7 crypto leverage exhaust data.**

[![Market Weather Status](https://open-market-weather.hartmut-nese.workers.dev/badge.svg)](https://open-market-weather.hartmut-nese.workers.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Dependencies](https://img.shields.io/badge/Dependencies-Zero%20(Stdlib%20Only)-brightgreen.svg)]()
[![Cost](https://img.shields.io/badge/Infrastructure%20Cost-$0%20(Always%20Free)-black.svg)]()
[![Coverage](https://img.shields.io/badge/Market%20Coverage-24%2F7%20Hybrid%20(TradFi%20%2B%20Crypto)-orange.svg)]()

**Live Terminal & Dashboard:** [https://open-market-weather.hartmut-nese.workers.dev](https://open-market-weather.hartmut-nese.workers.dev)  
**Machine-Readable API:** [https://open-market-weather.hartmut-nese.workers.dev/weather.json](https://open-market-weather.hartmut-nese.workers.dev/weather.json)

---

## 🏛️ The Thesis: Operational Exhaust vs. Lagging Noise

Most retail traders and quantitative algorithms rely on **lagging or circular indicators**: historical price action, RSI, standard moving averages, or media sentiment. By the time a systemic shock surfaces on retail exchanges, institutional capital has already de-risked.

Large institutional actors, central banks, and market makers leave **unavoidable physical, bureaucratic, and on-chain footprints** days before public market dislocations occur:
1. **Thermodynamic & Physical Constraints:** Real-world commercial freight delays at critical trade chokepoints (U.S. Customs Laredo).
2. **Statutory Obligations:** SEC Form 8-K disclosures legally mandated when corporate debt covenants are accelerated.
3. **Off-Exchange Order Routing:** FINRA Reg SHO Dark Pool short-sale accumulation before major downward trends.
4. **Sovereign Liquidity Plumbing:** Rapid drains or injections into the U.S. Treasury General Account (TGA) and Fed Liquidity Swaps.
5. **24/7 Crypto Derivative Leverage:** Hyperliquid perps funding rate spikes and Deribit Bitcoin Volatility (DVOL) anticipating weekend liquidation cascades.

The **Open Market Weather Observatory** aggregates these raw operational exhaust feeds every few hours, standardizes structural friction into a composite score (0–100), and provides an automated circuit-breaker signal for algorithmic trading bots.

---

## ⚡ Instant Terminal Access (CLI)

No browser required. Stream the current macro posture directly into your shell or terminal status bar:

```bash
curl -sL https://open-market-weather.hartmut-nese.workers.dev/weather.txt
```

---

## 🧬 The 6 Operational Pillars

| Pillar | Underlying Exhaust Feed | Live Data Source | Operational Metric Captured |
| :--- | :--- | :--- | :--- |
| **1. TradFi Derivatives** | S&P 500 VIX + U.S. Treasury MOVE Index | CBOE / Financial Chart API | Equity options implied volatility vs. bond market volatility. |
| **2. Crypto 24/7 Leverage** | Hyperliquid BTC Funding + Deribit DVOL | Hyperliquid Native API + Deribit Public REST | Perpetual futures funding pressure (APR) & 24/7 Bitcoin implied volatility. |
| **3. Dark Pool Flow** | FINRA Reg SHO Daily Short Volume | `cdn.finra.org` (NMS Consolidated) | Off-exchange institutional short-sale ratio on `$SPY`. |
| **4. Dollar Plumbing** | U.S. Treasury General Account (TGA) + NY Fed Swaps | U.S. Fiscal Data Service / NY Fed Markets API | Net liquidity absorption & sovereign cross-currency dollar strains. |
| **5. Statutory Credit Risk** | SEC Form 8-K (Item 2.04: Acceleration of Direct Obligations) | SEC EDGAR Full-Text Search (14-Day Window) | Corporate debt covenant breaches across publicly traded U.S. firms. |
| **6. Cognitive & Logistics** | Wikimedia Crisis Desks + CBP Land Border Waits | Wikimedia REST API (`agent=user`) + U.S. Customs & Border Protection | Institutional analyst panic research vs. physical truck bottlenecks (Laredo). |

---

## 🎯 Tactical Posture: Automated Bot Integration

The engine translates the 6-pillar composite index into direct, machine-readable operational directives for automated execution (e.g., Grid Bots, Market Makers, and DCA strategies).

### Machine-Readable Endpoint

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

### Python Circuit Breaker (Async / Hyperliquid / CCXT)

Safely integrate the weather engine as an asynchronous background sentinel without blocking your event loop or order execution:

```python
import aiohttp
import asyncio

async def check_weather_circuit_breaker():
    url = "https://open-market-weather.hartmut-nese.workers.dev/weather.json"
    timeout = aiohttp.ClientTimeout(total=2.0)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url) as resp:
                data = await resp.json()
                bot_status = data["tactical_posture"]["grid_bots"]["status"]
                crypto_status = data["tactical_posture"]["crypto_perps"]["status"]
                
                # Emergency: Halt buys during macro squalls or crypto liquidation cascades
                if bot_status == "PAUSED" or crypto_status == "OVERHEATED":
                    # Cancel resting bids immediately, retain profit-taking asks (Regel B)
                    await cancel_open_buys_only()
                elif bot_status == "CAUTION":
                    # Widen spacing, decrease lot size
                    adjust_grid_spread(multiplier=1.25, size_factor=0.6)
        except Exception as e:
            # Fail-safe: Never crash bot on transient network hiccups
            pass
```

---

## 🛠️ Zero-Cost, Edge-Native Architecture

This repository is designed under strict resource-efficiency constraints:
* **Zero Dependencies:** Built exclusively on the Python standard library (`urllib`, `json`, `math`, `datetime`). Memory footprint is `< 25 MB`.
* **Zero Server Maintenance:** Compute runs via automated **GitHub Actions** cron schedules.
* **Global Edge Distribution:** Output files (`index.html`, `weather.json`, `weather.txt`, `badge.svg`) are deployed globally across **Cloudflare Pages** edge nodes with `< 50ms` latency and 100/100 Google Lighthouse scores.
* **Zero Tracking / Non-Commercial:** No analytics, no cookies, no affiliate trackers, no monetized paywalls.

---

## 🛡️ Embeddable Badge

Add the live dynamic weather badge to your own open-source trading bots or repository READMEs:

```markdown
[![Market Weather](https://open-market-weather.hartmut-nese.workers.dev/badge.svg)](https://open-market-weather.hartmut-nese.workers.dev)
```

---

## ⚖️ License & Disclaimer

Released under the [MIT License](LICENSE).  
*Disclaimer: This observatory is an open-source technical research tool aggregating public agency and market data. It does not constitute financial or investment advice.*
