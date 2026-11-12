Pillar
Weight
What it looks at
Source
Market volatility
20%
VIX and MOVE
Yahoo Finance (unofficial chart endpoint)
Crypto leverage
20%
BTC perp funding (annualized) and BTC implied volatility (DVOL)
Hyperliquid, Deribit
Short volume
15%
Short share of SPY volume
FINRA daily Reg SHO files
Dollar liquidity
20%
Treasury General Account balance and how fast it moves, Fed FX swap line usage
US Fiscal Data, NY Fed
Credit stress
15%
8-K filings mentioning Item 2.04 (debt acceleration) in the last 14 days
SEC EDGAR full-text search
Odds and ends
10%
Wikipedia crisis traffic (6%) + truck wait times in Laredo (4%)
Wikimedia, CBP
Each pillar is mapped to 0–100 with simple clamped scaling. VIX, for example, runs from 12 to 35, and BTC funding is only scored by how far it sits from Hyperliquid's baseline of about 11% APR. The six pillars are combined using the weights above. No model, no fitting. Below 25 is clear, below 50 scattered clouds, below 75 rain, above that a storm.
The daily FINRA file is around 15 MB, so the script streams it line by line instead of loading it into memory.
Things to know before you trust it
