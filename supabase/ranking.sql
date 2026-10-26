-- Aprova: contas, papéis (admin/aluno), ranking, grupos e fórum dos grupos (Supabase)
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
alter table public.perfis add column if not exists papel text not null default 'aluno' check (papel in ('aluno', 'admin'));
alter table public.perfis add column if not exists bloqueado boolean not null default false;
alter table public.perfis enable row level security;

-- quem chama é administrador?
create or replace function public.eh_admin() returns boolean
language sql stable security definer set search_path = public as $$
    select exists (select 1 from public.perfis where id = auth.uid() and papel = 'admin');
$$;
grant execute on function public.eh_admin() to authenticated;

-- ninguém muda o próprio papel nem se desbloqueia: só um administrador muda isso
create or replace function public.proteger_perfil() returns trigger
language plpgsql security definer set search_path = public as $$
begin
    if coalesce(current_setting('aprova.primeiro_admin', true), '') = '1' or public.eh_admin() then
        return new;
    end if;
    if tg_op = 'INSERT' then
        new.papel := 'aluno';
        new.bloqueado := false;
    else
        new.papel := old.papel;
        new.bloqueado := old.bloqueado;
    end if;
    return new;
end $$;
drop trigger if exists proteger_perfil on public.perfis;
create trigger proteger_perfil before insert or update on public.perfis
    for each row execute function public.proteger_perfil();

-- o primeiro a chamar esta função (quando ainda não há nenhum admin) vira administrador.
-- Conta rápida (anônima, dos convites) nunca vira admin: só conta com e-mail e senha.
create or replace function public.virar_primeiro_admin() returns boolean
language plpgsql security definer set search_path = public as $$
begin
    if coalesce((auth.jwt() ->> 'is_anonymous')::boolean, false) then
        return false;
    end if;
    if exists (select 1 from public.perfis where papel = 'admin') then
        return false;
    end if;
    perform set_config('aprova.primeiro_admin', '1', true);
    update public.perfis set papel = 'admin' where id = auth.uid();
    return found;
end $$;
revoke all on function public.virar_primeiro_admin() from public, anon;
grant execute on function public.virar_primeiro_admin() to authenticated;

drop policy if exists "perfis: logados veem" on public.perfis;
create policy "perfis: logados veem" on public.perfis for select to authenticated using (true);
drop policy if exists "perfis: cria o seu" on public.perfis;
create policy "perfis: cria o seu" on public.perfis for insert to authenticated with check (id = auth.uid());
drop policy if exists "perfis: edita o seu" on public.perfis;
create policy "perfis: edita o seu" on public.perfis for update to authenticated using (id = auth.uid()) with check (id = auth.uid());
drop policy if exists "perfis: admin edita" on public.perfis;
create policy "perfis: admin edita" on public.perfis for update to authenticated using (public.eh_admin()) with check (public.eh_admin());

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
drop policy if exists "grupos: apaga" on public.grupos;
create policy "grupos: apaga" on public.grupos for delete to authenticated using (criado_por = auth.uid() or public.eh_admin());

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

-- convite por link: nome do grupo e número de membros, para a página do convite (funciona sem conta)
create or replace function public.convite_info(cod text) returns table (codigo text, nome text, membros bigint)
language sql stable security definer set search_path = public as $$
    select g.codigo, g.nome, (select count(*) from public.membros m where m.codigo = g.codigo)
    from public.grupos g
    where g.codigo = upper(trim(cod));
$$;
revoke all on function public.convite_info(text) from public;
grant execute on function public.convite_info(text) to anon, authenticated;

-- ---------------------------------------------------------------- rankings (só apelido e números; e-mail nunca aparece)
create or replace view public.ranking_semana with (security_invoker = true) as
select e.semana, p.id as usuario_id, p.apelido, p.concurso, e.segundos, e.questoes, e.acertos, e.dias, e.sequencia,
       case when e.questoes > 0 then round(e.acertos::numeric / e.questoes, 4) end as taxa
from public.estatisticas e
join public.perfis p on p.id = e.usuario_id
where not p.bloqueado;

create or replace view public.ranking_grupo with (security_invoker = true) as
select m.codigo, r.*
from public.membros m
join public.ranking_semana r on r.usuario_id = m.usuario_id;

grant select on public.ranking_semana, public.ranking_grupo to authenticated;

-- ---------------------------------------------------------------- comunicados (o admin escreve, todos leem na tela Início)
create table if not exists public.comunicados (
    id bigint generated always as identity primary key,
    titulo text not null check (char_length(titulo) between 3 and 80),
    texto text not null check (char_length(texto) between 1 and 1000),
    ativo boolean not null default true,
    criado_por uuid default auth.uid() references public.perfis (id) on delete set null,
    criado_em timestamptz not null default now()
);
alter table public.comunicados enable row level security;
drop policy if exists "comunicados: leem" on public.comunicados;
create policy "comunicados: leem" on public.comunicados for select to authenticated using (ativo or public.eh_admin());
drop policy if exists "comunicados: admin cria" on public.comunicados;
create policy "comunicados: admin cria" on public.comunicados for insert to authenticated with check (public.eh_admin());
drop policy if exists "comunicados: admin muda" on public.comunicados;
create policy "comunicados: admin muda" on public.comunicados for update to authenticated using (public.eh_admin()) with check (public.eh_admin());
drop policy if exists "comunicados: admin apaga" on public.comunicados;
create policy "comunicados: admin apaga" on public.comunicados for delete to authenticated using (public.eh_admin());

-- ---------------------------------------------------------------- fórum dos grupos
-- Só quem é do grupo lê e escreve. Quem criou o grupo (e o admin) modera: fixa e apaga mensagens.
create or replace function public.eh_membro(cod text) returns boolean
language sql stable security definer set search_path = public as $$
    select exists (select 1 from public.membros where codigo = cod and usuario_id = auth.uid());
$$;
create or replace function public.modera_grupo(cod text) returns boolean
language sql stable security definer set search_path = public as $$
    select public.eh_admin() or exists (select 1 from public.grupos where codigo = cod and criado_por = auth.uid());
$$;
create or replace function public.pode_escrever(cod text) returns boolean
language sql stable security definer set search_path = public as $$
    select public.eh_membro(cod) and not exists (select 1 from public.perfis where id = auth.uid() and bloqueado);
$$;
grant execute on function public.eh_membro(text), public.modera_grupo(text), public.pode_escrever(text) to authenticated;

create table if not exists public.forum_posts (
    id bigint generated always as identity primary key,
    codigo text not null references public.grupos (codigo) on delete cascade,
    autor uuid not null default auth.uid() references public.perfis (id) on delete cascade,
    tipo text not null default 'conversa' check (tipo in ('conversa', 'duvida', 'material', 'plano')),
    titulo text not null default '' check (char_length(titulo) <= 120),
    texto text not null default '' check (char_length(texto) <= 4000),
    plano jsonb check (plano is null or (jsonb_typeof(plano) = 'object' and octet_length(plano::text) <= 4000)),
    fixado boolean not null default false,
    criado_em timestamptz not null default now(),
    editado_em timestamptz,
    check (char_length(titulo) + char_length(texto) > 0)
);
create index if not exists forum_posts_grupo on public.forum_posts (codigo, criado_em desc);
alter table public.forum_posts enable row level security;

-- só quem modera fixa; ninguém troca o grupo nem o autor; o texto só o autor muda
create or replace function public.proteger_post() returns trigger
language plpgsql security definer set search_path = public as $$
begin
    if tg_op = 'INSERT' then
        if not public.modera_grupo(new.codigo) then
            new.fixado := false;
        end if;
        new.criado_em := now();
        new.editado_em := null;
        return new;
    end if;
    new.codigo := old.codigo;
    new.autor := old.autor;
    new.criado_em := old.criado_em;
    if not public.modera_grupo(old.codigo) then
        new.fixado := old.fixado;
    end if;
    if new.titulo is distinct from old.titulo or new.texto is distinct from old.texto or new.plano is distinct from old.plano or new.tipo is distinct from old.tipo then
        if old.autor = auth.uid() then
            new.editado_em := now();
        else
            new.titulo := old.titulo;
            new.texto := old.texto;
            new.plano := old.plano;
            new.tipo := old.tipo;
        end if;
    end if;
    return new;
end $$;
drop trigger if exists proteger_post on public.forum_posts;
create trigger proteger_post before insert or update on public.forum_posts
    for each row execute function public.proteger_post();

drop policy if exists "forum: membros leem" on public.forum_posts;
create policy "forum: membros leem" on public.forum_posts for select to authenticated using (public.eh_membro(codigo) or public.eh_admin());
drop policy if exists "forum: membros escrevem" on public.forum_posts;
create policy "forum: membros escrevem" on public.forum_posts for insert to authenticated with check (autor = auth.uid() and public.pode_escrever(codigo));
drop policy if exists "forum: autor ou moderador muda" on public.forum_posts;
create policy "forum: autor ou moderador muda" on public.forum_posts for update to authenticated
    using ((autor = auth.uid() and public.pode_escrever(codigo)) or public.modera_grupo(codigo))
    with check ((autor = auth.uid() and public.pode_escrever(codigo)) or public.modera_grupo(codigo));
drop policy if exists "forum: autor ou moderador apaga" on public.forum_posts;
create policy "forum: autor ou moderador apaga" on public.forum_posts for delete to authenticated using (autor = auth.uid() or public.modera_grupo(codigo));

create table if not exists public.forum_respostas (
    id bigint generated always as identity primary key,
    post_id bigint not null references public.forum_posts (id) on delete cascade,
    codigo text not null default '',
    autor uuid not null default auth.uid() references public.perfis (id) on delete cascade,
    texto text not null check (char_length(texto) between 1 and 2000),
    criado_em timestamptz not null default now()
);
create index if not exists forum_respostas_post on public.forum_respostas (post_id, criado_em);
alter table public.forum_respostas enable row level security;

create table if not exists public.forum_uteis (
    post_id bigint not null references public.forum_posts (id) on delete cascade,
    usuario_id uuid not null default auth.uid() references public.perfis (id) on delete cascade,
    codigo text not null default '',
    primary key (post_id, usuario_id)
);
alter table public.forum_uteis enable row level security;

-- respostas e "útil" herdam o grupo da mensagem (ninguém escolhe o grupo à mão)
create or replace function public.grupo_do_post() returns trigger
language plpgsql security definer set search_path = public as $$
begin
    select codigo into new.codigo from public.forum_posts where id = new.post_id;
    if new.codigo is null then
        raise exception 'mensagem não encontrada';
    end if;
    if tg_table_name = 'forum_respostas' then
        new.criado_em := now();
    end if;
    return new;
end $$;
drop trigger if exists grupo_do_post on public.forum_respostas;
create trigger grupo_do_post before insert or update on public.forum_respostas
    for each row execute function public.grupo_do_post();
drop trigger if exists grupo_do_post on public.forum_uteis;
create trigger grupo_do_post before insert or update on public.forum_uteis
    for each row execute function public.grupo_do_post();

drop policy if exists "respostas: membros leem" on public.forum_respostas;
create policy "respostas: membros leem" on public.forum_respostas for select to authenticated using (public.eh_membro(codigo) or public.eh_admin());
drop policy if exists "respostas: membros escrevem" on public.forum_respostas;
create policy "respostas: membros escrevem" on public.forum_respostas for insert to authenticated with check (autor = auth.uid() and public.pode_escrever(codigo));
drop policy if exists "respostas: autor ou moderador apaga" on public.forum_respostas;
create policy "respostas: autor ou moderador apaga" on public.forum_respostas for delete to authenticated using (autor = auth.uid() or public.modera_grupo(codigo));

drop policy if exists "uteis: membros leem" on public.forum_uteis;
create policy "uteis: membros leem" on public.forum_uteis for select to authenticated using (public.eh_membro(codigo) or public.eh_admin());
drop policy if exists "uteis: marca" on public.forum_uteis;
create policy "uteis: marca" on public.forum_uteis for insert to authenticated with check (usuario_id = auth.uid() and public.pode_escrever(codigo));
drop policy if exists "uteis: desmarca" on public.forum_uteis;
create policy "uteis: desmarca" on public.forum_uteis for delete to authenticated using (usuario_id = auth.uid());

-- o que o app lê: mensagens com apelido e contagens
create or replace view public.forum_feed with (security_invoker = true) as
select f.id, f.codigo, f.autor, p.apelido, f.tipo, f.titulo, f.texto, f.plano, f.fixado, f.criado_em, f.editado_em,
       (select count(*) from public.forum_respostas r where r.post_id = f.id) as respostas,
       (select count(*) from public.forum_uteis u where u.post_id = f.id) as uteis
from public.forum_posts f
join public.perfis p on p.id = f.autor;

create or replace view public.forum_respostas_v with (security_invoker = true) as
select r.id, r.post_id, r.codigo, r.autor, p.apelido, r.texto, r.criado_em
from public.forum_respostas r
join public.perfis p on p.id = r.autor;

grant select on public.forum_feed, public.forum_respostas_v to authenticated;

-- ---------------------------------------------------------------- acesso pela API
-- Vale mesmo se o projeto foi criado sem "expor tabelas novas". Quem decide o que cada um vê são as regras acima.
grant usage on schema public to authenticated;
grant select, insert, update, delete on public.perfis, public.estatisticas, public.grupos, public.membros, public.comunicados,
    public.forum_posts, public.forum_respostas, public.forum_uteis to authenticated;

-- ---------------------------------------------------------------- apagar a própria conta (LGPD)
create or replace function public.apagar_minha_conta() returns void
language sql security definer set search_path = public as $$
    delete from auth.users where id = auth.uid();
$$;
revoke all on function public.apagar_minha_conta() from public, anon;
grant execute on function public.apagar_minha_conta() to authenticated;
