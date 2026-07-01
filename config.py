"""Konfiguration fuer den Solana Fundamental Monitor."""

APP_TITLE = "Solana Fundamental Monitor"
TABLE = "solana_fundamentals"
LOCAL_CSV = "data/solana_fundamentals.csv"
WATCHLIST_JSON = "watchlist.json"

# Gewichtung der Investmentthese. Summe muss nicht exakt 1 ergeben; wird normalisiert.
WEIGHTS = {
    "rwa_usd": 0.24,
    "stablecoins_usd": 0.20,
    "tvl_sol": 0.16,
    "sol_btc": 0.14,
    "dex_volume_usd": 0.10,
    "fees_usd": 0.08,
    "active_addresses": 0.08,
}

# Grenzwerte fuer Ampeln. Fuer 30-Tage-Wachstum in Prozent.
GREEN_GROWTH = 5.0
RED_GROWTH = -5.0

# Persoenliche Position: nur Anzeige, keine Anlageberatung.
DEFAULT_SOL_HOLDINGS = 217.02
DEFAULT_AVG_ENTRY_USD = 130.0
