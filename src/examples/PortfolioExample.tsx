import React from "react";
import JitoRewardsCard from "../components/JitoRewardsCard";

export function PortfolioExample() {
  return (
    <JitoRewardsCard
      totalSolDeposited={281.11}
      totalSolWithdrawn={0}
      currentSolEquivalent={283.65}
      solPriceUsd={81.3}
    />
  );
}
