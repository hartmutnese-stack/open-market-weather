# ⛅ Open Market Weather Observatory (OMWO)

> **A decentralized, non-commercial systemic friction barometer tracking physical, bureaucratic, and off-exchange exhaust data.**

[![Market Weather Status](https://open-market-weather.hartmut-nese.workers.dev/badge.svg)](https://open-market-weather.hartmut-nese.workers.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Dependencies](https://img.shields.io/badge/Dependencies-Zero%20(Stdlib%20Only)-brightgreen.svg)]()
[![Cost](https://img.shields.io/badge/Infrastructure%20Cost-$0%20(Always%20Free)-black.svg)]()

**Live Terminal & Dashboard:** [https://open-market-weather.hartmut-nese.workers.dev](https://open-market-weather.hartmut-nese.workers.dev)  
**Machine-Readable API:** [https://open-market-weather.hartmut-nese.workers.dev/weather.json](https://open-market-weather.hartmut-nese.workers.dev/weather.json)

---

## 🏛️ The Thesis: Exhaust Data vs. Noise

Most retail traders and quantitative algorithms rely on **lagging or circular indicators**: historical price action, RSI, standard moving averages, or media sentiment. By the time a systemic shock surfaces on retail exchanges, institutional capital has already de-risked.

Large institutional actors, central banks, and sovereign entities leave **unavoidable physical and bureaucratic footprints** days before public market dislocations occur. They cannot fake:
1. **Thermodynamic & Physical Constraints:** Land freight delays at critical trade chokepoints.
2. **Statutory Obligations:** SEC Form 8-K disclosures triggered when lenders formally accelerate debt covenants.
3. **Off-Exchange Order Routing:** FINRA Reg SHO Dark Pool short-sale accumulation before major downward trends.
4. **Sovereign Liquidity Plumbing:** Rapid drains or injections into the U.S. Treasury General Account (TGA) and Fed Liquidity Swaps.

The **Open Market Weather Observatory** monitors these raw operational exhaust feeds every 4 hours, translates structural friction into a standardized Z-score (0–100), and provides an automated circuit-breaker signal for algorithmic trading bots.

---

## ⚡ Instant Terminal Access (CLI)

No browser required. Stream the current macro posture directly into your shell or `.bashrc`:

```bash
curl -sL https://open-market-weather.hartmut-nese.workers.dev/weather.txt
```

---

## 🧬 The 5 Operational Pillars

| Pillar | Underlying Exhaust Data | Data Source | Metric Captured |
| :--- | :--- | :--- | :--- |
| **1. Market Derivatives** | S&P 500 VIX + U.S. Treasury MOVE Index | CBOE / Financial Chart API | Equity options implied volatility vs. bond market volatility. |
| **2. Dark Pool Flow** | FINRA Reg SHO Daily Short Volume | `cdn.finra.org` (NMS Consolidated) | Off-exchange institutional short-sale ratio on `$SPY`. |
| **3. Dollar Plumbing** | U.S. Treasury General Account (TGA) + NY Fed Central Bank Swaps | U.S. Fiscal Data Service / NY Fed Markets API | Net liquidity absorption & sovereign cross-currency dollar strains. |
| **4. Statutory Credit Risk** | SEC Form 8-K (Item 2.04: Acceleration of Direct Financial Obligations) | SEC EDGAR Full-Text Search (14-Day Window) | Corporate debt covenant breaches across publicly traded U.S. firms. |
| **5. Cognitive & Physical Friction** | Wikimedia Crisis Desks + CBP Land Border Waits | Wikimedia REST API (`agent=user`) + U.S. Customs & Border Protection | Institutional analyst panic research vs. physical truck bottlenecks (Laredo). |

---

## 🎯 Tactical Posture: Automated Bot Integration

The engine translates the 5-pillar composite index into direct, machine-readable operational directives for automated execution (e.g., Grid Bots, Market Makers, and DCA strategies).

### Machine-Readable Endpoint

```bash
curl -sL https://open-market-weather.hartmut-nese.workers.dev/weather.json
```

```json
{
  "timestamp": "2026-11-06 17:16 UTC",
  "symbol": "⛅",
  "composite_score": 34,
  "status": "SCATTERED CLOUDS",
  "tactical_posture": {
    "grid_bots": {
      "status": "CAUTION",
      "action": "Widen grid bands by 15-25%. Reduce leverage."
    },
    "dip_buying": {
      "status": "DEFENSIVE",
      "action": "Support lines fragile. Do not catch falling knives."
    },
    "dark_pool": {
      "status": "ELEVATED",
      "action": "Elevated institutional downside hedging (56.0% SVR on SPY)."
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
                
                if bot_status == "PAUSED":
                    # Cancel resting bids immediately, retain profit-taking asks
                    await cancel_open_buys_only()
                elif bot_status == "CAUTION":
                    # Widen spacing, decrease lot size
                    adjust_grid_spread(multiplier=1.25, size_factor=0.6)
        except Exception as e:
            # Fail-safe: Never crash bot on network hiccups
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
