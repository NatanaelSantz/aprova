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

-- personagem (avatar): só escolhas pequenas de uma lista, ex. {"cabelo": "curto", "pele": 2, "usar_foto": false}.
-- Nada de texto livre nem link: só chaves curtas, números, sim/não e palavras simples.
create or replace function public.avatar_valido(a jsonb) returns boolean
language sql immutable set search_path = public as $$
    select a is null or (
        jsonb_typeof(a) = 'object'
        and length(a::text) <= 600
        and not exists (
            select 1 from jsonb_each(a) e
            where e.key !~ '^[a-z_]{1,16}$'
               or jsonb_typeof(e.value) not in ('number', 'string', 'boolean')
               or (jsonb_typeof(e.value) = 'string' and (e.value #>> '{}') !~ '^[a-z0-9_-]{0,24}$')
        )
    );
$$;
alter table public.perfis add column if not exists avatar jsonb;
alter table public.perfis drop constraint if exists perfis_avatar_valido;
alter table public.perfis add constraint perfis_avatar_valido check (public.avatar_valido(avatar)) not valid;

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
-- quem está no grupo vê os colegas; ninguém vê os grupos dos outros
create or replace function public.eh_membro(cod text) returns boolean
language sql stable security definer set search_path = public as $$
    select exists (select 1 from public.membros where codigo = cod and usuario_id = auth.uid());
$$;
-- 1.12: só vê o grupo quem é membro, quem criou ou o admin. Antes qualquer pessoa logada listava
-- todos os códigos e conseguia entrar em qualquer grupo; agora o código do convite é o segredo.
drop policy if exists "grupos: logados veem" on public.grupos;
drop policy if exists "grupos: membros veem" on public.grupos;
create policy "grupos: membros veem" on public.grupos for select to authenticated
    using (criado_por = auth.uid() or public.eh_admin() or public.eh_membro(codigo));
drop policy if exists "membros: logados veem" on public.membros;
drop policy if exists "membros: colegas veem" on public.membros;
create policy "membros: colegas veem" on public.membros for select to authenticated
    using (usuario_id = auth.uid() or public.eh_membro(codigo) or public.eh_admin());
-- entrar direto só quem criou o grupo; os outros entram pela função entrar_no_grupo (com o código)
drop policy if exists "membros: entra" on public.membros;
create policy "membros: entra" on public.membros for insert to authenticated
    with check (usuario_id = auth.uid() and exists (select 1 from public.grupos g where g.codigo = membros.codigo and g.criado_por = auth.uid()));
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

-- entrar no grupo com o código do convite (quem está bloqueado não entra)
create or replace function public.entrar_no_grupo(cod text) returns table (codigo text, nome text)
language plpgsql security definer set search_path = public as $$
declare
    g public.grupos%rowtype;
begin
    if auth.uid() is null or exists (select 1 from public.perfis where id = auth.uid() and bloqueado) then
        return;
    end if;
    select * into g from public.grupos where grupos.codigo = upper(trim(cod));
    if not found then
        return;
    end if;
    insert into public.membros (codigo, usuario_id) values (g.codigo, auth.uid()) on conflict do nothing;
    return query select g.codigo, g.nome;
end $$;
revoke all on function public.entrar_no_grupo(text) from public, anon;
grant execute on function public.entrar_no_grupo(text) to authenticated;

-- ---------------------------------------------------------------- rankings (só apelido e números; e-mail nunca aparece)
create or replace view public.ranking_semana with (security_invoker = true) as
select e.semana, p.id as usuario_id, p.apelido, p.concurso, e.segundos, e.questoes, e.acertos, e.dias, e.sequencia,
       case when e.questoes > 0 then round(e.acertos::numeric / e.questoes, 4) end as taxa,
       p.avatar
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
    editado_em timestamptz
);
create index if not exists forum_posts_grupo on public.forum_posts (codigo, criado_em desc);
alter table public.forum_posts enable row level security;

-- 1.10: fotos, arquivos, GIFs e figurinhas nas mensagens (as regras de conteúdo ficam mais abaixo)
alter table public.forum_posts add column if not exists anexos jsonb;
alter table public.forum_posts add column if not exists figurinha text;

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
    if new.titulo is distinct from old.titulo or new.texto is distinct from old.texto or new.plano is distinct from old.plano or new.tipo is distinct from old.tipo
       or new.anexos is distinct from old.anexos or new.figurinha is distinct from old.figurinha then
        if old.autor = auth.uid() then
            new.editado_em := now();
        else
            new.titulo := old.titulo;
            new.texto := old.texto;
            new.plano := old.plano;
            new.tipo := old.tipo;
            new.anexos := old.anexos;
            new.figurinha := old.figurinha;
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
    texto text not null default '',
    criado_em timestamptz not null default now()
);
create index if not exists forum_respostas_post on public.forum_respostas (post_id, criado_em);
alter table public.forum_respostas enable row level security;
alter table public.forum_respostas add column if not exists anexos jsonb;
alter table public.forum_respostas add column if not exists figurinha text;
alter table public.forum_respostas alter column texto set default '';

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

-- regras de conteúdo (1.10, mais rígidas na 1.12): texto, figurinha ou anexo. Anexo é arquivo do próprio
-- grupo, com extensão da lista do app (nada de .exe/.bat), ou GIF do GIPHY. Endereço só no GIF do GIPHY
-- (ninguém faz o app dos colegas carregar imagem de outro site).
create or replace function public.anexos_validos(a jsonb, cod text) returns boolean
language sql immutable as $$
    select a is null or (
        jsonb_typeof(a) = 'array' and jsonb_array_length(a) between 1 and 10 and octet_length(a::text) <= 8000
        and not exists (
            select 1 from jsonb_array_elements(a) e
            where jsonb_typeof(e) <> 'object'
               or coalesce(e->>'tipo', '') not in ('imagem', 'gif', 'arquivo')
               or char_length(coalesce(e->>'nome', '')) > 120
               or (e ? 'figurinha' and jsonb_typeof(e->'figurinha') <> 'boolean')
               or (e ? 'url' and not (e->>'tipo' = 'gif' and coalesce(e->>'url', '') ~ '^https://media[0-9]?\.giphy\.com/'))
               or (e->>'tipo' = 'arquivo' and lower(coalesce(e->>'nome', ''))
                     !~ '\.(png|jpe?g|webp|gif|pdf|txt|csv|rtf|zip|docx?|xlsx?|pptx?|od[tsp]|mp3|m4a|ogg|wav|mp4)$')
               or not (
                    (coalesce(e->>'caminho', '') ~ ('^' || cod || '/[0-9a-f-]{36}/[A-Za-z0-9._-]{1,140}$')
                       and lower(e->>'caminho') ~ '\.(png|jpe?g|webp|gif|pdf|txt|csv|rtf|zip|docx?|xlsx?|pptx?|od[tsp]|mp3|m4a|ogg|wav|mp4)$'
                       and e->>'caminho' !~ '\.\.')
                    or (e->>'tipo' = 'gif' and not (e ? 'caminho') and coalesce(e->>'url', '') ~ '^https://media[0-9]?\.giphy\.com/')
               )
        )
    )
$$;
alter table public.forum_posts drop constraint if exists forum_posts_check;
alter table public.forum_posts drop constraint if exists forum_posts_conteudo;
alter table public.forum_posts add constraint forum_posts_conteudo
    check (char_length(titulo) + char_length(texto) > 0 or anexos is not null or figurinha is not null);
alter table public.forum_posts drop constraint if exists forum_posts_anexos;
alter table public.forum_posts add constraint forum_posts_anexos check (public.anexos_validos(anexos, codigo)) not valid;
alter table public.forum_posts drop constraint if exists forum_posts_figurinha;
alter table public.forum_posts add constraint forum_posts_figurinha check (figurinha is null or figurinha ~ '^[a-z0-9-]{1,40}$');
alter table public.forum_respostas drop constraint if exists forum_respostas_texto_check;
alter table public.forum_respostas drop constraint if exists forum_respostas_texto;
alter table public.forum_respostas add constraint forum_respostas_texto check (char_length(texto) <= 2000);
alter table public.forum_respostas drop constraint if exists forum_respostas_conteudo;
alter table public.forum_respostas add constraint forum_respostas_conteudo
    check (char_length(texto) > 0 or anexos is not null or figurinha is not null);
alter table public.forum_respostas drop constraint if exists forum_respostas_anexos;
alter table public.forum_respostas add constraint forum_respostas_anexos check (public.anexos_validos(anexos, codigo)) not valid;
alter table public.forum_respostas drop constraint if exists forum_respostas_figurinha;
alter table public.forum_respostas add constraint forum_respostas_figurinha check (figurinha is null or figurinha ~ '^[a-z0-9-]{1,40}$');

-- o que o app lê: mensagens com apelido e contagens (colunas novas sempre no fim)
create or replace view public.forum_feed with (security_invoker = true) as
select f.id, f.codigo, f.autor, p.apelido, f.tipo, f.titulo, f.texto, f.plano, f.fixado, f.criado_em, f.editado_em,
       (select count(*) from public.forum_respostas r where r.post_id = f.id) as respostas,
       (select count(*) from public.forum_uteis u where u.post_id = f.id) as uteis,
       f.anexos, f.figurinha, p.avatar
from public.forum_posts f
join public.perfis p on p.id = f.autor;

create or replace view public.forum_respostas_v with (security_invoker = true) as
select r.id, r.post_id, r.codigo, r.autor, p.apelido, r.texto, r.criado_em, r.anexos, r.figurinha, p.avatar
from public.forum_respostas r
join public.perfis p on p.id = r.autor;

-- ---------------------------------------------------------------- arquivos dos grupos (Storage)
-- Pasta "anexos", privada: <código do grupo>/<quem enviou>/<arquivo>. Só quem é do grupo vê;
-- cada um envia só na própria pasta; quem enviou ou quem modera apaga. Até 20 MB por arquivo.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('anexos', 'anexos', false, 20971520, array[
    'image/png', 'image/jpeg', 'image/gif', 'image/webp',
    'application/pdf', 'text/plain', 'text/csv', 'application/rtf', 'application/zip',
    'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint', 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/vnd.oasis.opendocument.text', 'application/vnd.oasis.opendocument.spreadsheet',
    'application/vnd.oasis.opendocument.presentation',
    'audio/mpeg', 'audio/mp4', 'audio/ogg', 'audio/wav', 'video/mp4'
])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "anexos: membros leem" on storage.objects;
create policy "anexos: membros leem" on storage.objects for select to authenticated
    using (bucket_id = 'anexos' and (public.eh_membro((storage.foldername(name))[1]) or public.eh_admin()));
drop policy if exists "anexos: membros enviam" on storage.objects;
create policy "anexos: membros enviam" on storage.objects for insert to authenticated
    with check (bucket_id = 'anexos' and public.pode_escrever((storage.foldername(name))[1]) and (storage.foldername(name))[2] = auth.uid()::text);
drop policy if exists "anexos: quem enviou ou modera apaga" on storage.objects;
create policy "anexos: quem enviou ou modera apaga" on storage.objects for delete to authenticated
    using (bucket_id = 'anexos' and ((storage.foldername(name))[2] = auth.uid()::text or public.modera_grupo((storage.foldername(name))[1])));

-- ---------------------------------------------------------------- fotos de perfil (Storage)
-- Pasta "avatares", privada: um arquivo por pessoa, <id da conta>.webp (o app já manda a foto pequena, em WebP).
-- Quem está logado vê (a foto aparece nos grupos e no ranking); cada um troca ou apaga só a sua; o admin pode apagar.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('avatares', 'avatares', false, 307200, array['image/webp'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "avatares: logados veem" on storage.objects;
create policy "avatares: logados veem" on storage.objects for select to authenticated
    using (bucket_id = 'avatares');
drop policy if exists "avatares: cada um envia o seu" on storage.objects;
create policy "avatares: cada um envia o seu" on storage.objects for insert to authenticated
    with check (bucket_id = 'avatares' and name = auth.uid()::text || '.webp'
                and not exists (select 1 from public.perfis where id = auth.uid() and bloqueado));
drop policy if exists "avatares: cada um troca o seu" on storage.objects;
create policy "avatares: cada um troca o seu" on storage.objects for update to authenticated
    using (bucket_id = 'avatares' and name = auth.uid()::text || '.webp')
    with check (bucket_id = 'avatares' and name = auth.uid()::text || '.webp'
                and not exists (select 1 from public.perfis where id = auth.uid() and bloqueado));
drop policy if exists "avatares: dono ou admin apaga" on storage.objects;
create policy "avatares: dono ou admin apaga" on storage.objects for delete to authenticated
    using (bucket_id = 'avatares' and (name = auth.uid()::text || '.webp' or public.eh_admin()));

-- ---------------------------------------------------------------- configurações do app (admin)
-- Ex.: a chave do GIPHY para a busca de GIFs. Quem está logado lê; só o admin muda.
create table if not exists public.config (
    chave text primary key check (chave ~ '^[a-z_]{1,40}$'),
    valor text not null default '' check (char_length(valor) <= 500)
);
alter table public.config enable row level security;
drop policy if exists "config: logados leem" on public.config;
create policy "config: logados leem" on public.config for select to authenticated using (true);
drop policy if exists "config: admin escreve" on public.config;
create policy "config: admin escreve" on public.config for insert to authenticated with check (public.eh_admin());
drop policy if exists "config: admin muda" on public.config;
create policy "config: admin muda" on public.config for update to authenticated using (public.eh_admin()) with check (public.eh_admin());
drop policy if exists "config: admin apaga" on public.config;
create policy "config: admin apaga" on public.config for delete to authenticated using (public.eh_admin());

grant select on public.forum_feed, public.forum_respostas_v to authenticated;

-- ---------------------------------------------------------------- acesso pela API
-- Vale mesmo se o projeto foi criado sem "expor tabelas novas". Quem decide o que cada um vê são as regras acima.
grant usage on schema public to authenticated;
grant select, insert, update, delete on public.perfis, public.estatisticas, public.grupos, public.membros, public.comunicados,
    public.forum_posts, public.forum_respostas, public.forum_uteis, public.config to authenticated;

-- ---------------------------------------------------------------- apagar a própria conta (LGPD)
create or replace function public.apagar_minha_conta() returns void
language sql security definer set search_path = public as $$
    delete from auth.users where id = auth.uid();
$$;
revoke all on function public.apagar_minha_conta() from public, anon;
grant execute on function public.apagar_minha_conta() to authenticated;

-- ---------------------------------------------------------------- espaço usado (1.24, só o admin vê)
-- O plano grátis tem limite de banco e de arquivos: o Admin mostra quanto já foi usado.
create or replace function public.uso_do_servidor() returns table (item text, bytes bigint, arquivos bigint)
language sql stable security definer set search_path = public, storage as $$
    select 'banco'::text, pg_database_size(current_database())::bigint, null::bigint
    where public.eh_admin()
    union all
    select 'arquivos:' || o.bucket_id, coalesce(sum((o.metadata ->> 'size')::bigint), 0)::bigint, count(*)::bigint
    from storage.objects o
    where public.eh_admin()
    group by o.bucket_id;
$$;
revoke all on function public.uso_do_servidor() from public, anon;
grant execute on function public.uso_do_servidor() to authenticated;

-- ---------------------------------------------------------------- relatórios de erro (1.26)
-- Só quem ligou "Enviar relatórios de erro" nos Ajustes manda. Vai o erro técnico (sem estudos, sem
-- e-mail, sem o nome da pasta do usuário). Ninguém lê nem grava direto: o app envia pela função
-- reportar_erro (com trava contra enxurrada) e só o admin lê e apaga.
create table if not exists public.erros (
    id bigserial primary key,
    criado_em timestamptz not null default now(),
    versao text not null check (char_length(versao) <= 20),
    sistema text not null default '' check (char_length(sistema) <= 40),
    onde text not null default '' check (char_length(onde) <= 120),
    mensagem text not null check (char_length(mensagem) <= 300),
    detalhe text not null default '' check (char_length(detalhe) <= 4000),
    assinatura text not null check (assinatura ~ '^[a-f0-9]{12,40}$'),
    usuario_id uuid
);
create index if not exists erros_quando on public.erros (criado_em desc);
alter table public.erros enable row level security;
drop policy if exists "erros: admin lê" on public.erros;
create policy "erros: admin lê" on public.erros for select to authenticated using (public.eh_admin());
drop policy if exists "erros: admin apaga" on public.erros;
create policy "erros: admin apaga" on public.erros for delete to authenticated using (public.eh_admin());
grant select, delete on public.erros to authenticated;

create or replace function public.reportar_erro(versao_app text, sistema_op text, local text, msg text, rastro text, chave text)
returns boolean
language plpgsql security definer set search_path = public as $$
begin
    if chave is null or chave !~ '^[a-f0-9]{12,40}$' or coalesce(msg, '') = '' then
        return false;
    end if;
    -- trava: no máximo 300 relatórios por dia no total e 20 do mesmo erro
    if (select count(*) from public.erros where criado_em > now() - interval '1 day') >= 300 then
        return false;
    end if;
    if (select count(*) from public.erros e where e.assinatura = chave and e.criado_em > now() - interval '1 day') >= 20 then
        return false;
    end if;
    delete from public.erros where criado_em < now() - interval '90 days';
    insert into public.erros (versao, sistema, onde, mensagem, detalhe, assinatura, usuario_id)
    values (left(coalesce(versao_app, '?'), 20), left(coalesce(sistema_op, ''), 40), left(coalesce(local, ''), 120),
            left(msg, 300), left(coalesce(rastro, ''), 4000), chave, auth.uid());
    return true;
end $$;
revoke all on function public.reportar_erro(text, text, text, text, text, text) from public;
grant execute on function public.reportar_erro(text, text, text, text, text, text) to anon, authenticated;
