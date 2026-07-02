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

alter table public.user_positions enable row level security;

drop policy if exists "Users can read own position" on public.user_positions;
create policy "Users can read own position"
on public.user_positions for select
using (auth.uid() = user_id);

drop policy if exists "Users can insert own position" on public.user_positions;
create policy "Users can insert own position"
on public.user_positions for insert
with check (auth.uid() = user_id);

drop policy if exists "Users can update own position" on public.user_positions;
create policy "Users can update own position"
on public.user_positions for update
using (auth.uid() = user_id)
with check (auth.uid() = user_id);
