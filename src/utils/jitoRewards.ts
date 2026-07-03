/**
 * Correct JitoSOL reward calculation.
 *
 * JitoSOL does not pay rewards by increasing your JitoSOL token count.
 * Instead, each JitoSOL gradually represents more SOL over time.
 *
 * Wrong:
 *   current SOL equivalent - JitoSOL token amount
 *
 * Correct:
 *   rewardSol = currentSolEquivalent - (totalSolDeposited - totalSolWithdrawn)
 *
 * Andreas snapshot:
 *   Bought: 281.11 SOL
 *   Holding: 283.65 SOL
 *   Sold: 0 SOL
 *   Reward: 283.65 - 281.11 = 2.54 SOL
 */

export type CurrencyCode = "USD" | "EUR";

export interface JitoRewardsInput {
  totalSolDeposited: number;
  totalSolWithdrawn?: number;
  currentSolEquivalent: number;
  solPriceUsd?: number;
  solPriceEur?: number;
}

export interface JitoRewardsResult {
  netDepositedSol: number;
  currentSolEquivalent: number;
  rewardSol: number;
  rewardPercent: number;
  rewardUsd: number | null;
  rewardEur: number | null;
  isProfit: boolean;
}

function assertFiniteNumber(value: number, fieldName: string): void {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${fieldName} must be a finite number.`);
  }
}

export function calculateJitoRewards(input: JitoRewardsInput): JitoRewardsResult {
  const {
    totalSolDeposited,
    totalSolWithdrawn = 0,
    currentSolEquivalent,
    solPriceUsd,
    solPriceEur,
  } = input;

  assertFiniteNumber(totalSolDeposited, "totalSolDeposited");
  assertFiniteNumber(totalSolWithdrawn, "totalSolWithdrawn");
  assertFiniteNumber(currentSolEquivalent, "currentSolEquivalent");
  if (solPriceUsd !== undefined) assertFiniteNumber(solPriceUsd, "solPriceUsd");
  if (solPriceEur !== undefined) assertFiniteNumber(solPriceEur, "solPriceEur");

  const netDepositedSol = totalSolDeposited - totalSolWithdrawn;

  if (netDepositedSol <= 0) {
    return {
      netDepositedSol,
      currentSolEquivalent,
      rewardSol: 0,
      rewardPercent: 0,
      rewardUsd: solPriceUsd !== undefined ? 0 : null,
      rewardEur: solPriceEur !== undefined ? 0 : null,
      isProfit: false,
    };
  }

  const rewardSol = currentSolEquivalent - netDepositedSol;
  const rewardPercent = (rewardSol / netDepositedSol) * 100;

  return {
    netDepositedSol,
    currentSolEquivalent,
    rewardSol,
    rewardPercent,
    rewardUsd: solPriceUsd !== undefined ? rewardSol * solPriceUsd : null,
    rewardEur: solPriceEur !== undefined ? rewardSol * solPriceEur : null,
    isProfit: rewardSol >= 0,
  };
}

export function formatNumber(
  value: number,
  options: Intl.NumberFormatOptions = {},
  locale = "de-DE",
): string {
  return new Intl.NumberFormat(locale, options).format(value);
}

export function formatSol(value: number, locale = "de-DE"): string {
  return `${formatNumber(value, { minimumFractionDigits: 2, maximumFractionDigits: 4 }, locale)} SOL`;
}

export function formatPercent(value: number, locale = "de-DE"): string {
  return `${formatNumber(value, { minimumFractionDigits: 2, maximumFractionDigits: 2 }, locale)} %`;
}

export function formatFiat(value: number, currency: CurrencyCode, locale = "de-DE"): string {
  return formatNumber(value, {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }, locale);
}
