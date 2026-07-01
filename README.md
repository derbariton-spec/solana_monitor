# Solana Fundamental Monitor 2.0

Persönliches Streamlit-Dashboard für eine langfristige SOL-/JitoSOL-These:

> Wird Solana wichtiger als Infrastruktur für Stablecoins, RWA, tokenisierte Aktien, Zahlungen und institutionelle Finanzanwendungen?

Der Monitor soll nicht den nächsten Trade erraten. Er soll zeigen, ob die Fundamentaldaten deiner These stärker oder schwächer werden.

---

## Neu in Version 2.0

- **Lokaler Betrieb ohne Supabase** möglich: Daten werden in `data/solana_fundamentals.csv` gespeichert.
- **Supabase optional** für Serverbetrieb und Historie.
- Zusätzliche Kennzahlen:
  - TVL in SOL
  - DEX-Volumen 24h
  - Fees 24h
  - Revenue 24h
  - BTC/USD
  - BTC-Dominanz
- Persönliche Position in der Sidebar: SOL/JitoSOL + Einstiegskurs.
- Investmentthese-Status: `intakt`, `neutral`, `geschwächt`.
- 30-Tage-Ampel je Kennzahl.
- Optionale `watchlist.json` für Ereignisse wie MoneyGram, bitFlyer, Agave, Alpenglow, ETF-Meilensteine.

---

## Schnellstart lokal

```bash
cd solana-monitor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# ersten Snapshot holen
python3 fetch_data.py

# Dashboard starten
streamlit run app.py
```

Dann im Browser öffnen:

```text
http://localhost:8501
```

Ohne `.env` nutzt der Monitor automatisch lokale CSV-Speicherung.

---

## Supabase einrichten optional

1. Kostenloses Projekt auf Supabase anlegen.
2. SQL Editor öffnen.
3. Inhalt von `supabase_schema.sql` ausführen.
4. `.env.example` nach `.env` kopieren und Werte eintragen:

```bash
cp .env.example .env
nano .env
```

Wichtig:

- `SUPABASE_SERVICE_KEY` nur serverseitig für `fetch_data.py` verwenden.
- `SUPABASE_ANON_KEY` reicht für das Streamlit-Dashboard zum Lesen.

---

## Tägliches Update per Cron

Auf einem VPS:

```bash
crontab -e
```

Beispiel täglich um 07:00 Uhr:

```cron
0 7 * * * cd /opt/solana-monitor && /opt/solana-monitor/venv/bin/python3 fetch_data.py >> /opt/solana-monitor/fetch.log 2>&1
```

---

## Streamlit als Service

`/etc/systemd/system/solana-monitor.service`:

```ini
[Unit]
Description=Solana Fundamental Monitor
After=network.target

[Service]
Type=simple
User=dein-linux-user
WorkingDirectory=/opt/solana-monitor
ExecStart=/opt/solana-monitor/venv/bin/streamlit run app.py --server.port 8501 --server.address 127.0.0.1
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Aktivieren:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now solana-monitor
sudo systemctl status solana-monitor
```

---

## Datenquellen

| Kennzahl | Quelle |
|---|---|
| SOL/USD, SOL/BTC, BTC/USD | CoinGecko public API |
| BTC-Dominanz | CoinGecko global API |
| TVL | DefiLlama Chain TVL |
| Stablecoins | DefiLlama Stablecoins |
| RWA | DefiLlama Protocols, Kategorie RWA, Chain Solana |
| DEX-Volumen | DefiLlama DEX Overview Solana |
| Fees / Revenue | DefiLlama Fees Overview Solana |
| Active Addresses | Platzhalter, optional Artemis/Flipside nachrüsten |

Hinweis zu RWA: RWA.xyz und DefiLlama können unterschiedliche Abgrenzungen verwenden. Dieser Monitor nutzt aktuell eine DefiLlama-nahe Schätzung.

---

## Fundamental Score

Der Score misst 30-Tage-Wachstum der wichtigsten Kennzahlen.

Aktuelle Gewichtung in `config.py`:

```python
WEIGHTS = {
    "rwa_usd": 0.24,
    "stablecoins_usd": 0.20,
    "tvl_sol": 0.16,
    "sol_btc": 0.14,
    "dex_volume_usd": 0.10,
    "fees_usd": 0.08,
    "active_addresses": 0.08,
}
```

Fehlende Kennzahlen werden automatisch ignoriert und die Gewichte der vorhandenen Kennzahlen neu verteilt.

Interpretation:

- **≥ 68**: These intakt
- **45–67**: neutral/gemischt
- **< 45**: geschwächt

---

## Watchlist

Optional kannst du Ereignisse manuell ergänzen:

```bash
cp watchlist.json.example watchlist.json
nano watchlist.json
```

Beispiele:

- MoneyGram wird Validator
- bitFlyer listet SOL in Japan
- Agave v4.2
- Alpenglow-Meilensteine
- ETF-Anträge/Zulassungen
- neue tokenisierte Aktien/RWA-Produkte

---

## Nächste sinnvolle Ausbaustufen

1. Artemis API für Active Addresses und Transaktionen.
2. RWA.xyz API oder Export für exaktere RWA-Daten und Holder.
3. News-Agent mit Quellenklassifizierung: positiv / neutral / Risiko.
4. Telegram- oder E-Mail-Alert nur bei echten These-Änderungen, nicht bei Kursrauschen.
5. Deployment auf Streamlit Community Cloud oder VPS mit Nginx/HTTPS.

---

## Wichtiger Hinweis

Dieses Tool ist keine Anlageberatung. Es hilft, eine persönliche Investmentthese strukturiert zu beobachten.
