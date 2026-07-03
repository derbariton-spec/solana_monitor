# JitoSOL Reward Calculation Fix

This patch fixes the JitoSOL portfolio calculation.

Do **not** calculate rewards as:

```ts
currentSolEquivalent - jitoSolTokenAmount
```

JitoSOL token quantity does not increase. Rewards are reflected in the increasing SOL value of each JitoSOL.

## Correct formula

```ts
rewardSol = currentSolEquivalent - (totalSolDeposited - totalSolWithdrawn)
```

Example from the wallet snapshot:

```txt
Bought:  281.11 SOL
Holding: 283.65 SOL
Sold:      0.00 SOL
Reward:   2.54 SOL
```

At SOL = 81.30 USD:

```txt
Reward value: about 206.50 USD
Return: about 0.90 % since entry
```

## Files to copy

```txt
src/utils/jitoRewards.ts
src/components/JitoRewardsCard.tsx
```

Optional:

```txt
src/examples/PortfolioExample.tsx
src/utils/jitoRewards.test.ts
```

## Usage

```tsx
import JitoRewardsCard from "./components/JitoRewardsCard";

export default function PortfolioPage() {
  return (
    <JitoRewardsCard
      totalSolDeposited={281.11}
      totalSolWithdrawn={0}
      currentSolEquivalent={283.65}
      solPriceUsd={81.3}
    />
  );
}
```

## Dynamic data mapping

```ts
const totalSolDeposited = jupiterPosition.boughtSol;
const totalSolWithdrawn = jupiterPosition.soldSol ?? 0;
const currentSolEquivalent = jupiterPosition.holdingSol;
```

Then pass these values into `calculateJitoRewards` or `JitoRewardsCard`.

## Test

If you use Vitest, add this to your package.json:

```json
{
  "scripts": {
    "test:jito": "vitest run src/utils/jitoRewards.test.ts"
  }
}
```

This is a portfolio display calculation, not tax advice. For taxes, every SOL → JitoSOL swap must be treated separately with FIFO and holding period.
