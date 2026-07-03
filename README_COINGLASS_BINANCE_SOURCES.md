# Hotfix: CoinGlass/Binance Market-Signal-Quellen

Ersetze im GitHub-Hauptverzeichnis diese Dateien:

- `market_signals.py`
- `sentiment.py`
- `formatting.py`

Änderungen:

- Fear & Greed wird zuerst von `https://www.binance.com/en/square/fear-and-greed-index` gelesen.
- Altcoin Season versucht zuerst die CoinGlass-Seite `https://www.coinglass.com/de/pro/i/alt-coin-season` und danach mögliche JSON/API-Routen. Wenn CoinGlass keine maschinenlesbaren Werte liefert, bleibt der bisherige Proxy aus SOL/BTC + BTC-Dominance aktiv.
- Open Interest versucht zuerst CoinGlass API v4 mit `COINGLASS_API_KEY`. Wenn kein Key vorhanden ist oder der Plan den Endpoint blockiert, nutzt die App Binance Futures als Fallback und zeigt CoinGlass als Referenzquelle.
- `safe_float` ist robust gegen `None`, damit die App nicht mehr wegen fehlender Werte abstürzt.

Optional für echte CoinGlass-Daten in Streamlit Secrets:

```toml
COINGLASS_API_KEY = "dein_key"
```

Danach Streamlit rebooten und den Refresh-Button drücken.
