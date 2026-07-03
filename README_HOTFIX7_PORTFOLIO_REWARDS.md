# Solana Monitor 5.3 Hotfix 7 – Portfolio/JitoSOL-Zuwachs Plausibilitätscheck

Ersetzt nur:

- `portfolio.py`

## Problem

Die App konnte eine alte oder falsch gespeicherte `bought_sol_basis` wie `200 SOL` als Basis verwenden. Bei einem aktuellen Bestand von ca. 220 JitoSOL / 283 SOL Gegenwert erzeugt das einen absurd hohen „JitoSOL-Zuwachs“ von ca. 83 SOL.

## Fix

- Die App akzeptiert Startdaten jetzt auch im deutschen Format, z. B. `26.03.2026`.
- Eine manuelle Bought-SOL-Basis wird vor der Anzeige geprüft.
- Unplausible Werte, z. B. weniger als 1 SOL pro JitoSOL, werden nicht mehr als Rewards-Basis verwendet.
- Statt eines falschen hohen Zuwachses zeigt die App dann `n/a` plus Warnung.

## Danach

Für eine sinnvolle Berechnung bitte entweder:

1. `JitoSOL-Kauf-/Startdatum` setzen, z. B. `2026-03-26` oder `26.03.2026`, oder
2. bei `Bought / ursprünglich gestakte SOL-Basis` den Phantom-Wert `Bought` in SOL eintragen.

