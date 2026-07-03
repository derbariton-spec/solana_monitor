# Solana Monitor 5.1 Hotfix 5 — Market-Signal-Quellen robuster

Ersetzt diese Dateien im GitHub-Hauptverzeichnis:

- `market_signals.py`
- `sentiment.py`

Änderungen:

- Funding Rate: Binance Futures bleibt primär, Bybit öffentlicher API-Fallback ergänzt.
- Open Interest: CoinGlass mit API-Key bleibt primär, Binance-Fallback, danach Bybit-Fallback.
- Fear & Greed: Binance Square bleibt Zielquelle, Alternative.me als stabiler API-Fallback, wenn Binance HTML nicht maschinenlesbar ist.
- Altcoin Season: CoinGlass HTML wird nicht mehr blind numerisch geparst, weil die Seite Skalenwerte wie 100 enthält. Dadurch verschwindet der falsche `100.0`-Wert. Ohne API wird der vorhandene SOL/BTC + BTC-Dominance-Proxy genutzt.

Danach committen/pushen, Streamlit rebooten und den Refresh-Button drücken.
