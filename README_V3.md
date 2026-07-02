# Solana Fundamental Monitor 3.0

Version 3.0 erweitert den Monitor um eine historische Datenbasis.

## Dateien

- `app.py` – App mit Login, Candlestick-Chart, EUR-Portfolio, JitoSOL-Umrechnung und Staking-Schätzung.
- `backfill_history.py` – Einmaliger historischer Backfill für SOL, BTC, TVL, Stablecoins, DEX-Volumen, App Fees und App Revenue.
- `.github/workflows/backfill-history.yml` – Manueller GitHub-Workflow für den Backfill.
- `data_sources.py` / `fetch_data.py` – korrigierte DeFiLlama-nahe tägliche Datenlogik.
- `requirements_v3.txt` – benötigte Pakete; `plotly>=5.24.0` muss in deine echte `requirements.txt`.

## Lokaler Test

```bash
python3 backfill_history.py --days 365
```

## GitHub Action

Nach dem Push findest du unter `Actions` den Workflow `Backfill Solana History`.
Dort kannst du manuell starten, z. B. mit:

- 365 = 1 Jahr
- 1095 = 3 Jahre
- 1825 = 5 Jahre

## Hinweis

RWA Active Mcap und Active Addresses sind historisch schwerer frei abzurufen.
Sie werden künftig täglich durch `fetch_data.py` ergänzt, während der Backfill vor allem Preis, TVL, Stablecoins, DEX und App Fees/Revenue historisch füllt.
