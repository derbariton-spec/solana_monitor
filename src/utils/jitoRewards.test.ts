import { describe, expect, it } from "vitest";
import { calculateJitoRewards } from "./jitoRewards";

describe("calculateJitoRewards", () => {
  it("calculates Andreas' JitoSOL reward correctly", () => {
    const result = calculateJitoRewards({
      totalSolDeposited: 281.11,
      totalSolWithdrawn: 0,
      currentSolEquivalent: 283.65,
      solPriceUsd: 81.3,
    });

    expect(result.netDepositedSol).toBeCloseTo(281.11, 6);
    expect(result.rewardSol).toBeCloseTo(2.54, 6);
    expect(result.rewardPercent).toBeCloseTo(0.9032, 4);
    expect(result.rewardUsd).toBeCloseTo(206.502, 3);
  });

  it("subtracts withdrawn SOL", () => {
    const result = calculateJitoRewards({
      totalSolDeposited: 100,
      totalSolWithdrawn: 10,
      currentSolEquivalent: 95,
    });

    expect(result.netDepositedSol).toBe(90);
    expect(result.rewardSol).toBe(5);
    expect(result.rewardPercent).toBeCloseTo(5.555555, 6);
  });

  it("does not divide by zero", () => {
    const result = calculateJitoRewards({
      totalSolDeposited: 0,
      currentSolEquivalent: 0,
    });

    expect(result.rewardSol).toBe(0);
    expect(result.rewardPercent).toBe(0);
  });
});
