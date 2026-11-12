open-market-weather
A weather report for the markets. One Python script pulls a handful of public data feeds, squeezes them into a single score between 0 and 100, and displays it the way a weather app would: ☀️ when things look calm, ⛈️ when they don't.
I built it for my own grid bot on Hyperliquid. Before it keeps buying dips, it checks macro plumbing and crypto leverage to see if something odd is going on. It's a rough heuristic: the weights are my own guesses and I haven't backtested any of it. Please don't treat it as a trading signal.
Dashboard: https://open-market-weather.hartmut-nese.workers.dev
JSON: https://open-market-weather.hartmut-nese.workers.dev/weather.json
Plain text: curl -sL https://open-market-weather.hartmut-nese.workers.dev/weather.txt
�
Bild laden
