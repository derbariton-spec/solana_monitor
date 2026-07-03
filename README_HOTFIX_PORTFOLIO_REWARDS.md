# Hotfix: JitoSOL-Zuwachs korrekt berechnen

Ersetzt:
- `app.py`
- `portfolio.py`

Änderung:
- Der angezeigte Wert heißt jetzt `JitoSOL-Zuwachs` statt pauschal `Staking-Ertrag`.
- Wenn ein `JitoSOL-Kauf-/Startdatum` eingetragen ist, wird der historische JitoSOL/SOL-Kurs an diesem Datum über CoinGecko geschätzt.
- Der Zuwachs wird dann berechnet als:

```text
aktueller SOL-Gegenwert der JitoSOL
- JitoSOL-Bestand × historischer JitoSOL/SOL-Kurs am Startdatum
```

Damit wird nicht mehr fälschlich gegen 1.0 SOL oder gegen eine alte/falsche Standardbasis wie 200 SOL gerechnet.

Falls zusätzlich ein Phantom-Bought-Wert eingetragen ist, zeigt die App eine Warnung, wenn dieser stark von der historischen Schätzung abweicht.
