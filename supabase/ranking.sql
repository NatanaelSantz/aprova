-- Aprova: ranking entre estudantes (Supabase)
-- Como usar: no painel do Supabase, abra "SQL Editor", cole este arquivo inteiro e clique em "Run".
-- Pode rodar de novo sem problema (ele não apaga dados).

-- ---------------------------------------------------------------- perfis
create table if not exists public.perfis (
    id uuid primary key references auth.users (id) on delete cascade,
    apelido text not null check (char_length(apelido) between 3 and 24),
    concurso text not null default '' check (char_length(concurso) <= 60),
    criado_em timestamptz not null default now()
);
create unique index if not exists perfis_apelido_unico on public.perfis (lower(apelido));
alter table public.perfis enable row level security;

drop policy if exists "perfis: logados veem" on public.perfis;
create policy "perfis: logados veem" on public.perfis for select to authenticated using (true);
drop policy if exists "perfis: cria o seu" on public.perfis;
create policy "perfis: cria o seu" on public.perfis for insert to authenticated with check (id = auth.uid());
drop policy if exists "perfis: edita o seu" on public.perfis;
create policy "perfis: edita o seu" on public.perfis for update to authenticated using (id = auth.uid()) with check (id = auth.uid());

-- ---------------------------------------------------------------- números da semana
-- semana = segunda-feira da semana. Limites evitam números absurdos.
create table if not exists public.estatisticas (
    usuario_id uuid not null default auth.uid() references public.perfis (id) on delete cascade,
    semana date not null,
    segundos integer not null default 0 check (segundos between 0 and 360000),
    questoes integer not null default 0 check (questoes between 0 and 10000),
    acertos integer not null default 0 check (acertos >= 0 and acertos <= questoes),
    dias integer not null default 0 check (dias between 0 and 7),
    sequencia integer not null default 0 check (sequencia between 0 and 3650),
    atualizado_em timestamptz not null default now(),
    primary key (usuario_id, semana)
);
alter table public.estatisticas enable row level security;

drop policy if exists "estatisticas: logados veem" on public.estatisticas;
create policy "estatisticas: logados veem" on public.estatisticas for select to authenticated using (true);
drop policy if exists "estatisticas: envia as suas" on public.estatisticas;
create policy "estatisticas: envia as suas" on public.estatisticas for insert to authenticated
    with check (usuario_id = auth.uid() and semana between current_date - 14 and current_date + 1);
drop policy if exists "estatisticas: atualiza as suas" on public.estatisticas;
create policy "estatisticas: atualiza as suas" on public.estatisticas for update to authenticated
    using (usuario_id = auth.uid())
    with check (usuario_id = auth.uid() and semana between current_date - 14 and current_date + 1);

-- ---------------------------------------------------------------- grupos (turmas)
create table if not exists public.grupos (
    codigo text primary key check (codigo ~ '^[A-Z0-9-]{4,24}$'),
    nome text not null check (char_length(nome) between 3 and 40),
    criado_por uuid default auth.uid() references public.perfis (id) on delete set null,
    criado_em timestamptz not null default now()
);
alter table public.grupos enable row level security;
drop policy if exists "grupos: logados veem" on public.grupos;
create policy "grupos: logados veem" on public.grupos for select to authenticated using (true);
drop policy if exists "grupos: cria" on public.grupos;
create policy "grupos: cria" on public.grupos for insert to authenticated with check (criado_por = auth.uid());

create table if not exists public.membros (
    codigo text not null references public.grupos (codigo) on delete cascade,
    usuario_id uuid not null default auth.uid() references public.perfis (id) on delete cascade,
    entrou_em timestamptz not null default now(),
    primary key (codigo, usuario_id)
);
alter table public.membros enable row level security;
drop policy if exists "membros: logados veem" on public.membros;
create policy "membros: logados veem" on public.membros for select to authenticated using (true);
drop policy if exists "membros: entra" on public.membros;
create policy "membros: entra" on public.membros for insert to authenticated with check (usuario_id = auth.uid());
drop policy if exists "membros: sai" on public.membros;
create policy "membros: sai" on public.membros for delete to authenticated using (usuario_id = auth.uid());

-- ---------------------------------------------------------------- rankings (só apelido e números; e-mail nunca aparece)
create or replace view public.ranking_semana with (security_invoker = true) as
select e.semana, p.id as usuario_id, p.apelido, p.concurso, e.segundos, e.questoes, e.acertos, e.dias, e.sequencia,
       case when e.questoes > 0 then round(e.acertos::numeric / e.questoes, 4) end as taxa
from public.estatisticas e
join public.perfis p on p.id = e.usuario_id;

create or replace view public.ranking_grupo with (security_invoker = true) as
select m.codigo, r.*
from public.membros m
join public.ranking_semana r on r.usuario_id = m.usuario_id;

grant select on public.ranking_semana, public.ranking_grupo to authenticated;

-- ---------------------------------------------------------------- apagar a própria conta (LGPD)
create or replace function public.apagar_minha_conta() returns void
language sql security definer set search_path = public as $$
    delete from auth.users where id = auth.uid();
$$;
revoke all on function public.apagar_minha_conta() from public, anon;
grant execute on function public.apagar_minha_conta() to authenticated;
