# Solana Research Terminal v4.0

Ein modulares Streamlit-Dashboard für Solana: Live-Markt, Candlestick-Chart, Portfolio/Login, Wallet-Auslesung, JitoSOL/Staking, Fundamentaldaten, Backfill, News und optionale CoinGlass Liquidation Levels.

## Start lokal

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python fetch_data.py
streamlit run app.py
```

## Streamlit Secrets

```toml
SUPABASE_URL = "https://deinprojekt.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_..."
COINGLASS_API_KEY = "optional"
DEFILLAMA_API_KEY = "optional"
SOLANA_RPC_URL = "optional"
```

## Supabase

Führe `sql/supabase_setup.sql` im Supabase SQL Editor aus.

## GitHub Actions

- `Daily Solana Monitor Update` läuft täglich und ruft `fetch_data.py` auf.
- `Backfill Solana History` ist manuell startbar und ruft `backfill_history.py` auf.

## Hinweis zu RWA und CoinGlass

DefiLlama RWA Chain-Daten sind als API nach DefiLlama-Dokumentation im Pro-Bereich verfügbar. Ohne `DEFILLAMA_API_KEY` nutzt die App eine öffentliche RWA-Protokoll-Schätzung als Fallback.

CoinGlass Liquidation Heatmap/Levels benötigen einen CoinGlass API-Key und einen API-Plan, der die Heatmap-Endpunkte freischaltet.

## Sicherheit

Die App liest niemals Private Keys oder Seed Phrases. Die Wallet-Auslesung nutzt ausschließlich die öffentliche Wallet-Adresse.
