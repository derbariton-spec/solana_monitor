import React from "react";
import {
  calculateJitoRewards,
  formatFiat,
  formatPercent,
  formatSol,
} from "../utils/jitoRewards";

type JitoRewardsCardProps = {
  totalSolDeposited: number;
  totalSolWithdrawn?: number;
  currentSolEquivalent: number;
  solPriceUsd?: number;
  solPriceEur?: number;
  className?: string;
};

const cardStyle: React.CSSProperties = {
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 16,
  padding: 16,
  background: "rgba(255,255,255,0.04)",
};

const rowStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  gap: 16,
  padding: "8px 0",
  borderBottom: "1px solid rgba(255,255,255,0.08)",
};

const labelStyle: React.CSSProperties = { opacity: 0.72 };

export function JitoRewardsCard({
  totalSolDeposited,
  totalSolWithdrawn = 0,
  currentSolEquivalent,
  solPriceUsd,
  solPriceEur,
  className,
}: JitoRewardsCardProps) {
  const stats = calculateJitoRewards({
    totalSolDeposited,
    totalSolWithdrawn,
    currentSolEquivalent,
    solPriceUsd,
    solPriceEur,
  });

  const rewardPrefix = stats.rewardSol >= 0 ? "+" : "";
  const rewardColor = stats.rewardSol >= 0 ? "#22c55e" : "#ef4444";

  return (
    <section className={className} style={cardStyle}>
      <h3 style={{ margin: "0 0 12px" }}>JitoSOL Rewards</h3>

      <div style={rowStyle}>
        <span style={labelStyle}>Eingesetzt</span>
        <strong>{formatSol(stats.netDepositedSol)}</strong>
      </div>

      <div style={rowStyle}>
        <span style={labelStyle}>Aktueller SOL-Gegenwert</span>
        <strong>{formatSol(stats.currentSolEquivalent)}</strong>
      </div>

      <div style={rowStyle}>
        <span style={labelStyle}>Reward</span>
        <strong style={{ color: rewardColor }}>
          {rewardPrefix}{formatSol(stats.rewardSol)}
        </strong>
      </div>

      <div style={rowStyle}>
        <span style={labelStyle}>Rendite seit Einstieg</span>
        <strong style={{ color: rewardColor }}>
          {rewardPrefix}{formatPercent(stats.rewardPercent)}
        </strong>
      </div>

      {stats.rewardUsd !== null && (
        <div style={rowStyle}>
          <span style={labelStyle}>Reward-Wert USD</span>
          <strong style={{ color: rewardColor }}>
            {rewardPrefix}{formatFiat(stats.rewardUsd, "USD")}
          </strong>
        </div>
      )}

      {stats.rewardEur !== null && (
        <div style={{ ...rowStyle, borderBottom: 0 }}>
          <span style={labelStyle}>Reward-Wert EUR</span>
          <strong style={{ color: rewardColor }}>
            {rewardPrefix}{formatFiat(stats.rewardEur, "EUR")}
          </strong>
        </div>
      )}

      <p style={{ margin: "12px 0 0", fontSize: 12, opacity: 0.64 }}>
        Berechnung: aktueller SOL-Gegenwert der JitoSOL minus netto eingebrachte SOL.
      </p>
    </section>
  );
}

export default JitoRewardsCard;
