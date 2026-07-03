# Solana Research Terminal 5.0

Ein persönliches Solana-Research-Dashboard mit Live-Markt, Fundamentaldaten, Score-Erklärung, Wallet/JitoSOL-Auswertung, Szenario-Rechner, Risiko-Ampel, Wochenbericht und optionalen CoinGlass Liquidation Levels.

## Neu in Version 5.0

- Datenqualitäts-Panel: zeigt, welche Kennzahlen belastbar, kurz historisiert oder fehlend sind.
- Score-Erklärung: positive Treiber, Belastungsfaktoren und fehlende Daten werden direkt erklärt.
- Subscores: Fundamentals, Onchain, Economics, Market Relative und Risk Buffer.
- Besseres Scoring: Flows wie DEX/Fees/Revenue werden als 30D-Summe vs. vorherige 30D-Summe bewertet; Active Addresses werden geglättet.
- Wallet/JitoSOL: öffentliche Solana-Wallet auslesen, SOL/JitoSOL/USDC anzeigen, Staking-Ertrag gegen Bought-SOL-Basis berechnen.
- Szenario-Rechner: Portfolio-Wert bei frei wählbaren SOL-Zielpreisen, inklusive angenommener JitoSOL-APY.
- Nachkauf-/Hedge-Ampel: einfache Risikoorientierung anhand Kurszone, Score und schwacher Kennzahlen.
- These-gebrochen-Modul: Frühwarnsystem für strukturelle Schwächen.
- Wochenbericht: 7-Tage-Veränderungen der wichtigsten Kennzahlen.
- Optional: CoinGlass Liquidation Levels mit `COINGLASS_API_KEY`.

## Repository-Struktur

```text
solana_monitor_v5/
├── app.py
├── auth.py
├── backfill_history.py
├── charts.py
├── config.py
├── data_sources.py
├── fetch_data.py
├── formatting.py
├── news_fetcher.py
├── portfolio.py
├── quality.py
├── reports.py
├── risk.py
├── scenario.py
├── score.py
├── scoring.py
├── storage.py
├── thesis.py
├── wallet.py
├── requirements.txt
├── runtime.txt
├── sql/
│   └── supabase_setup.sql
└── .github/
    └── workflows/
        ├── daily-fetch.yml
        └── backfill-history.yml
```

## Setup in Streamlit Cloud

In Streamlit Secrets eintragen:

```toml
SUPABASE_URL = "https://deinprojekt.supabase.co"
SUPABASE_ANON_KEY = "dein_publishable_key"
COINGLASS_API_KEY = "optional"
DEFILLAMA_API_KEY = "optional"
SOLANA_RPC_URL = "optional"
```

Supabase SQL Editor öffnen und den Inhalt von `sql/supabase_setup.sql` ausführen. Die Datei ist idempotent und kann mehrfach ausgeführt werden.

## GitHub Actions

- `Daily Solana Monitor Update` sammelt täglich aktuelle Fundamentaldaten.
- `Backfill Solana History` kann manuell gestartet werden und füllt die Historie.

Nach dem Hochladen am besten zuerst `Backfill Solana History` unter GitHub → Actions starten.

## Hinweise

- Für die Wallet-Auswertung wird nur die öffentliche Wallet-Adresse verwendet. Private Keys oder Seed Phrases werden niemals benötigt.
- RWA und Active Addresses werden best-effort über öffentlich verfügbare Daten geladen. Wenn eine Quelle ihr Format ändert, zeigt das Datenqualitäts-Panel die Einschränkung an.
- CoinGlass ist optional und benötigt einen API-Key. Ohne Key bleibt der Liquidationen-Tab als Hinweis-/Link-Bereich aktiv.
- Die Risiko- und Nachkauf-Ampeln sind Entscheidungshilfen und keine Anlageberatung.

## Version 5.1 – Market Signals

Neu hinzugefügt:

- eigener Tab **Market Signals**
- RSI 14 auf SOL/USD Daily Candles
- MACD inklusive Bullish/Bearish Cross
- Bullish/Bearish Engulfing Pattern
- Funding Rate über Binance Futures Public API als Fallback ohne API-Key
- Open Interest und 30D-Veränderung über Binance Futures Public API
- Fear & Greed Index über alternative.me
- Altcoin Season Index, sofern öffentlicher Endpoint erreichbar; sonst Proxy aus SOL/BTC und BTC-Dominance
- Timing Score, Technical Score, Derivatives Score und Sentiment Score

Die Signale sind bewusst vom Fundamental Score getrennt. Der Fundamental Score bewertet die Solana-These; der Timing Score bewertet Marktphase, Hebel und Sentiment.
