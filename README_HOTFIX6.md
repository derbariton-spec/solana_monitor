# Solana Monitor 5.1 Hotfix 6

Fixes Market Signals reliability:

- Altcoin Season no longer parses false `100.0` from CoinGlass/HTML/gauge scales.
- Without a CoinGlass API key, Altcoin Season uses the app proxy from SOL/BTC and BTC Dominance.
- Fear & Greed uses Alternative.me JSON first and keeps Binance Square as the displayed reference/fallback.
- Funding tries Binance, Bybit and OKX.
- Open Interest tries CoinGlass API, Binance, Bybit and OKX.

Replace in repo root:

- `market_signals.py`
- `sentiment.py`

Then commit/push, reboot Streamlit and click refresh.
