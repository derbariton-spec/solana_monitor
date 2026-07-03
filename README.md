# Solana Research Terminal 5.2

Multi-User-Version mit zwei Modi:

- **Public Mode**: allgemeines Solana-Research ohne Login.
- **Personal Mode**: Login, eigene Wallet, JitoSOL-Auswertung, Watch-Level, Szenarien und Notizen.

## Neu in 5.2

- Public/Personal Mode Umschalter in der Sidebar
- Profil- und Onboarding-Tab
- persönliche Watch-Level
- persönliche Szenario-Vorgaben
- tägliche persönliche Notizen
- Supabase Tabellen mit Row-Level-Security für jeden Nutzer
- Hotfixes aus 5.1 integriert: robustere Market Signals, safe_float-Fix, Daily-Fetch-Fix

## Installation

Den Inhalt dieses Ordners in das GitHub-Hauptverzeichnis kopieren, nicht den Ordner selbst als Unterordner hochladen.

Danach in Supabase ausführen:

```sql
sql/supabase_setup.sql
```

Streamlit Secrets:

```toml
SUPABASE_URL = "https://deinprojekt.supabase.co"
SUPABASE_ANON_KEY = "dein_publishable_key"
COINGLASS_API_KEY = "optional"
DEFILLAMA_API_KEY = "optional"
```

## Reihenfolge nach Upload

1. GitHub Commit/Push
2. Supabase SQL erneut ausführen
3. Streamlit App rebooten
4. GitHub Actions: Daily Solana Monitor Update manuell starten
5. Optional: Backfill Solana History starten
6. In der App oben: Werte aktualisieren

## Hinweis zu API-Keys

CoinGlass-Daten sind am stabilsten mit eigenem CoinGlass API-Key. Ohne Key nutzt die App öffentliche Börsen-Fallbacks und Proxies.

## Sicherheit

Die App speichert nur öffentliche Wallet-Adressen und persönliche Einstellungen. Keine Seed Phrase, kein Private Key. Supabase Row-Level-Security sorgt dafür, dass Nutzer nur ihre eigenen persönlichen Daten sehen.
