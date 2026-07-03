-- Solana Research Terminal 5.2
-- Safe to run repeatedly in Supabase SQL Editor.
-- Adds multi-user Public/Personal Mode tables with Row-Level Security.

create table if not exists public.user_positions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  wallet_address text,
  manual_jitosol_amount numeric default 0,
  manual_sol_equivalent numeric default 0,
  avg_entry_jitosol_usd numeric default 0,
  historical_sol_entry_usd numeric default 0,
  bought_sol_basis numeric default 0,
  staking_start_date date,
  updated_at timestamp with time zone default now(),
  unique(user_id)
);

alter table public.user_positions add column if not exists wallet_address text;
alter table public.user_positions add column if not exists manual_jitosol_amount numeric default 0;
alter table public.user_positions add column if not exists manual_sol_equivalent numeric default 0;
alter table public.user_positions add column if not exists avg_entry_jitosol_usd numeric default 0;
alter table public.user_positions add column if not exists historical_sol_entry_usd numeric default 0;
alter table public.user_positions add column if not exists bought_sol_basis numeric default 0;
alter table public.user_positions add column if not exists staking_start_date date;
alter table public.user_positions add column if not exists updated_at timestamp with time zone default now();

create table if not exists public.user_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  display_name text,
  investor_mode text default 'Public + Personal',
  risk_profile text default 'Ausgewogen',
  onboarding_completed boolean default false,
  updated_at timestamp with time zone default now(),
  unique(user_id)
);

create table if not exists public.user_watch_levels (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  accumulation_below_usd numeric default 150,
  warning_below_usd numeric default 130,
  hedge_check_above_usd numeric default 220,
  profit_check_above_usd numeric default 350,
  long_term_target_usd numeric default 950,
  updated_at timestamp with time zone default now(),
  unique(user_id)
);

create table if not exists public.user_scenarios (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  target_prices_csv text default '250, 500, 950',
  jitosol_apy_assumption numeric default 6.5,
  updated_at timestamp with time zone default now(),
  unique(user_id)
);

create table if not exists public.user_notes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  note_date date not null default current_date,
  note text,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now(),
  unique(user_id, note_date)
);

alter table public.user_positions enable row level security;
alter table public.user_profiles enable row level security;
alter table public.user_watch_levels enable row level security;
alter table public.user_scenarios enable row level security;
alter table public.user_notes enable row level security;

-- user_positions policies
drop policy if exists "Users can read own position" on public.user_positions;
create policy "Users can read own position" on public.user_positions for select to authenticated using (auth.uid() = user_id);
drop policy if exists "Users can insert own position" on public.user_positions;
create policy "Users can insert own position" on public.user_positions for insert to authenticated with check (auth.uid() = user_id);
drop policy if exists "Users can update own position" on public.user_positions;
create policy "Users can update own position" on public.user_positions for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Generic per-user policies for new 5.2 tables.
drop policy if exists "Users can read own profile" on public.user_profiles;
create policy "Users can read own profile" on public.user_profiles for select to authenticated using (auth.uid() = user_id);
drop policy if exists "Users can insert own profile" on public.user_profiles;
create policy "Users can insert own profile" on public.user_profiles for insert to authenticated with check (auth.uid() = user_id);
drop policy if exists "Users can update own profile" on public.user_profiles;
create policy "Users can update own profile" on public.user_profiles for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "Users can read own watch levels" on public.user_watch_levels;
create policy "Users can read own watch levels" on public.user_watch_levels for select to authenticated using (auth.uid() = user_id);
drop policy if exists "Users can insert own watch levels" on public.user_watch_levels;
create policy "Users can insert own watch levels" on public.user_watch_levels for insert to authenticated with check (auth.uid() = user_id);
drop policy if exists "Users can update own watch levels" on public.user_watch_levels;
create policy "Users can update own watch levels" on public.user_watch_levels for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "Users can read own scenarios" on public.user_scenarios;
create policy "Users can read own scenarios" on public.user_scenarios for select to authenticated using (auth.uid() = user_id);
drop policy if exists "Users can insert own scenarios" on public.user_scenarios;
create policy "Users can insert own scenarios" on public.user_scenarios for insert to authenticated with check (auth.uid() = user_id);
drop policy if exists "Users can update own scenarios" on public.user_scenarios;
create policy "Users can update own scenarios" on public.user_scenarios for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "Users can read own notes" on public.user_notes;
create policy "Users can read own notes" on public.user_notes for select to authenticated using (auth.uid() = user_id);
drop policy if exists "Users can insert own notes" on public.user_notes;
create policy "Users can insert own notes" on public.user_notes for insert to authenticated with check (auth.uid() = user_id);
drop policy if exists "Users can update own notes" on public.user_notes;
create policy "Users can update own notes" on public.user_notes for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

select pg_notify('pgrst', 'reload schema');
