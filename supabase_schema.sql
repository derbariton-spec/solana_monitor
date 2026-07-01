-- Solana Fundamental Monitor 2.0
-- Supabase SQL Editor -> New Query -> Run

create table if not exists public.solana_fundamentals (
    id bigint generated always as identity primary key,
    snapshot_date date not null unique,
    sol_usd numeric,
    sol_btc numeric,
    btc_usd numeric,
    btc_dominance numeric,
    tvl_usd numeric,
    tvl_sol numeric,
    stablecoins_usd numeric,
    rwa_usd numeric,
    dex_volume_usd numeric,
    fees_usd numeric,
    revenue_usd numeric,
    active_addresses numeric,
    fundamental_score numeric,
    thesis_status text,
    note text,
    created_at timestamptz not null default now()
);

-- Fuer bestehende v1-Installationen: fehlende Spalten nachruesten.
alter table public.solana_fundamentals add column if not exists btc_usd numeric;
alter table public.solana_fundamentals add column if not exists btc_dominance numeric;
alter table public.solana_fundamentals add column if not exists tvl_sol numeric;
alter table public.solana_fundamentals add column if not exists dex_volume_usd numeric;
alter table public.solana_fundamentals add column if not exists fees_usd numeric;
alter table public.solana_fundamentals add column if not exists revenue_usd numeric;
alter table public.solana_fundamentals add column if not exists thesis_status text;

create index if not exists idx_solana_fundamentals_date
    on public.solana_fundamentals (snapshot_date desc);

alter table public.solana_fundamentals enable row level security;

drop policy if exists "Public read access" on public.solana_fundamentals;
create policy "Public read access"
    on public.solana_fundamentals
    for select
    using (true);
