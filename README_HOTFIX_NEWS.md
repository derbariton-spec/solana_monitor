# Solana Monitor 5.3 Hotfix – News Radar

Ersetze im GitHub-Hauptverzeichnis nur:

- `app.py`
- `news_fetcher.py`

Änderungen:

- News-Tab direkt nach `Übersicht`, also deutlich weiter links.
- Breiterer News-Radar mit mehreren Feeds/Suchclustern:
  - Solana Top News
  - SOL Market
  - ETF / Institutional
  - RWA / Stablecoins
  - DeFi / Ecosystem
  - Tech / Network
  - Reddit r/solana
  - Reddit r/CryptoCurrency
- Deduplizierung ähnlicher Überschriften.
- Sortierung nach Neuigkeit.
- Filter nach Kategorie, Signal, Quelle und Suchwort.
- Mehr Artikel statt nur 1–4 Treffer.
- Native Streamlit-Karten, kein riskantes HTML.

Danach committen/pushen, Streamlit rebooten und `🔄 Werte aktualisieren` drücken.
