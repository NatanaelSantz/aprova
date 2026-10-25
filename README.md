# Aprova — estudo para concursos públicos (v1.6)

App em Python (Flet) para acompanhar concursos, baixar provas anteriores, resolver as provas no próprio app e ver onde focar os estudos.

## O que ele faz

- **Concursos abertos** por região, com prazo de inscrição, vagas, salário e nível. A estrela acompanha o prazo na tela Início.
- **Concursos já realizados**: busca por órgão ou cargo, abre o edital e leva às provas anteriores.
- **Escolha um concurso e receba a prova** (aba *Provas*): digite o concurso (ex.: `Dataprev 2026`) ou cole o link da página dele no site da banca. O Aprova procura em vários lugares ao mesmo tempo:
  - **site oficial da banca**: provas separadas por cargo e caderno, com o gabarito oficial. Toque no caderno da sua área e a prova já abre pronta, com o gabarito certo;
  - **outros sites**: PDFs de prova, gabarito e prova comentada achados na internet;
  - **PCI Concursos**: o acervo de provas anteriores.
- **Encher a biblioteca**: escolha o concurso e o Aprova baixa de uma vez as provas das últimas edições, de todos os cargos, cada uma com o gabarito oficial. Você marca quais cargos quer.
  - Entra um caderno por cargo (os outros tipos têm as mesmas questões em outra ordem).
  - Questões iguais em vários cargos (como Português) aparecem uma vez só nos simulados.
  - Onde fica: botão “Encher a biblioteca” na aba *Provas* depois da busca, em *Estudar* e em *Concursos → Nas bancas*.
  - Na biblioteca, as provas do mesmo concurso ficam juntas numa pasta, com o botão “Simulado do concurso”.
- **Nas bancas** (aba *Concursos*): a lista oficial de concursos da FGV, em andamento e realizados, com botão “Ver provas”.
- **Aviso “Saiu a prova”**: os concursos que você acompanha (estrela) e cuja prova já passou são verificados uma vez por dia. Quando aparece a prova, surge um cartão na tela Início.
- **Fazer a prova no app**:
  - *Simulado*: cronômetro e correção só no final.
  - *Modo estudo*: correção a cada questão.
  - Cartão-resposta com bolinhas, marcar para revisar e resultado por disciplina.
  - PDFs digitalizados (imagem) abrem com as páginas originais e um cartão-resposta ao lado.
- **Ajuda em cada questão**: sempre pesquisa na internet e mostra as fontes. A *dica* não revela a resposta; a *explicação completa* revela. Com a chave da API do Claude (opcional), a explicação é escrita pela IA.
- **Montar simulado**: você escolhe o número de questões e quantas de cada disciplina. Já vem o modelo da Dataprev 2026 (FGV, 70 questões).
  - As questões saem das provas anteriores do mesmo concurso ou órgão; se faltar, de outras provas da biblioteca.
  - Com a chave do Claude, a IA cria as que faltarem no estilo da banca, usando os assuntos do edital.
  - Também dá para montar a partir do edital: botão “Montar simulado” na janela do concurso.
- **Onde focar**: cruza quanto cada disciplina cai nas suas provas com quanto você ainda erra.
- **Meta semanal (tela Início)**: anel com o progresso das horas da semana, saldo em relação ao previsto, sequência de dias, horas por dia com a meta de cada dia e o cartão “Seu próximo estudo” (revisão do dia ou treino do ponto fraco).
- **Tempo de estudo**: conta sozinho enquanto você resolve questões (para depois de 8 minutos parado). Para estudo fora do app (livro, aula), use o **cronômetro** ou **lance o tempo** à mão.
- **Painel**:
  - *Desempenho*: acertos por disciplina com selo Forte / Atenção / Precisa melhorar, evolução nas últimas 8 semanas, acertos por banca e por concurso.
  - *Tempo*: meta, horas por dia, mapa das últimas 12 semanas, em que dias da semana você estuda e tempo por disciplina.
  - *Lembretes*: alarmes de atividades extras. Na hora, o app toca e leva você ao conteúdo: pesquisa na internet, vídeo-aulas, um link, a revisão, um treino ou um simulado.
  - *Livros*: indicações por disciplina, das mais fracas para as mais fortes, com material oficial gratuito (leis no Planalto).
- **Contas e login**: cada pessoa entra com e-mail e senha e tem seus estudos separados. Há dois tipos de conta: **aluno** e **administrador** (veja abaixo). Quem não quiser conta usa o app normalmente com “Usar sem conta”.
- **Tela que se ajusta ao aparelho**: no celular, menu embaixo; em tela média, menu lateral compacto; em tela grande, menu lateral completo e o conteúdo centralizado.
- **Ranking**: crie uma conta com apelido e compare horas, questões, acerto e sequência da semana com outras pessoas, no geral ou em grupos com código (a turma do concurso, os amigos). Fica em Painel → Ranking.
- **Revisão espaçada** (Estudar → Revisão): o que você erra ou marca com a bandeira volta no dia certo (1, 3, 7, 15 e 30 dias) até ficar dominado.
- **Dúvidas**: no painel de Ajuda de cada questão, escreva sua dúvida; o Aprova pesquisa na internet para responder (com a chave do Claude, a resposta vem explicada). Todas ficam guardadas em Estudar → Dúvidas.
- **Questões inéditas com IA**: a IA lê questões reais das provas do concurso na sua biblioteca, cria novas no mesmo estilo e confere o gabarito resolvendo cada uma de novo (precisa da chave do Claude). Também completa os simulados montados.
- **Conforto para os olhos**:
  - Temas claro, sépia (leitura) e escuro.
  - Fonte Atkinson Hyperlegible, com tamanho e espaçamento ajustáveis.
  - Leitura em voz alta da questão.
  - Lembrete de pausa 20-20-20.
- **Celular**: o mesmo app abre no navegador do celular, na mesma rede Wi-Fi.

## Como abrir no Windows

1. Extraia este .zip numa pasta (ex.: `Documentos\Aprova`).
2. Dê dois cliques em **`Abrir Aprova.bat`**. Na primeira vez aparece a janela **Preparando o Aprova**, com barra de progresso:
   - se o computador não tiver Python, ele é instalado antes, numa janela própria;
   - depois vêm as bibliotecas do app (de 5 a 10 minutos, precisa de internet).
3. No fim, o Aprova abre sozinho e cria o atalho **Aprova** na área de trabalho. Dali em diante, abra por ele: o app abre direto, sem janela preta.

Se algo der errado, a janela mostra o motivo e o botão **Tentar de novo**. Os detalhes ficam em `C:\Users\<você>\.aprova\instalacao.log`.
Se a instalação automática do Python falhar, instale o **Python 3.12 ou 3.13** em [python.org](https://www.python.org/downloads/), marque **“Add python.exe to PATH”** e abra o `.bat` de novo.

No macOS/Linux: `./iniciar.sh` (ou `./iniciar.sh --web` para o modo navegador).

## Usar no celular

- Jeito mais fácil: no app, vá em **Ajustes → Usar no celular → Ligar acesso pelo celular** e aponte a câmera para o QR code.
- Ou abra **`Abrir no celular.bat`** e digite no celular o endereço que aparece na janela (ex.: `http://192.168.0.10:8550`).

O celular precisa estar no mesmo Wi-Fi. Se não abrir, permita o Python no firewall do Windows em redes privadas. Para colocar um ícone na tela inicial, use “Adicionar à tela inicial” no menu do navegador do celular.

## De onde vêm as provas

| Fonte | Como funciona |
|---|---|
| Site oficial da FGV | lista de concursos e PDFs direto do site; baixa e importa sozinho |
| Página de qualquer banca | cole o link da página do concurso na aba Provas; o Aprova lê os PDFs que estiverem nela |
| Internet | busca por PDFs de prova e gabarito em outros sites |
| [PCI Concursos](https://www.pciconcursos.com.br) | acervo de provas anteriores e lista de concursos abertos |

Cebraspe e Vunesp montam as páginas com JavaScript, então o link colado nem sempre traz os PDFs; nesse caso use a busca na internet ou o PCI. O site da FCC não permite leitura automática e fica de fora.

### PCI Concursos

Hoje o PCI pede uma verificação de segurança antes de liberar os PDFs. Por isso o Aprova:

1. abre a página da prova no seu navegador;
2. você confirma a verificação e clica em “Baixar” na prova e no gabarito;
3. o Aprova encontra os arquivos na pasta **Downloads** e importa sozinho.

Se a pasta de downloads for outra, ajuste em **Ajustes → Geral**. Também dá para usar **Estudar → Importar PDF** com qualquer prova que você já tenha.

## Atalhos durante a prova (computador)

| Tecla | Ação |
|---|---|
| A, B, C, D, E | responder |
| ← → | questão anterior / próxima |
| M | marcar para revisar |
| H | abrir a ajuda |

## Contas: login, aluno e administrador

Ao abrir, o Aprova mostra a tela **Entrar / Criar conta**:

- **Entrar** ou **Criar conta** (e-mail, senha e apelido). Na próxima vez ele entra sozinho.
- **Usar sem conta**: estuda normalmente no computador, sem ranking. Dá para criar a conta depois em **Ajustes → Conta**.
- **Esqueci a senha**: o Supabase manda um e-mail para trocar a senha.

Cada conta tem os **próprios estudos** (provas, respostas, metas, tempo), então duas pessoas podem usar o mesmo computador. Na primeira vez que alguém entra, se já existirem estudos feitos sem conta, o app pergunta se quer **levar esses estudos para a conta**.

Tipos de conta:

| | Aluno | Administrador |
|---|---|---|
| Estudar, provas, painel, ranking | sim | sim |
| Ver comunicados na tela Início | sim | sim |
| Tela **Admin** (no menu) | — | sim |

A **primeira pessoa que cria conta** no servidor vira administrador sozinha. Depois disso, só um administrador transforma outra conta em administrador. Na tela **Admin**:

- *Visão geral*: contas, quem estudou na semana, horas e questões somadas, quem mais estudou e os concursos mais estudados;
- *Usuários*: procurar por apelido ou concurso, **tornar administrador**, voltar para aluno, **bloquear** (some do ranking) e desbloquear;
- *Grupos*: ver e apagar grupos;
- *Comunicados*: escrever um aviso que aparece na tela Início de todos (ex.: “Simulado coletivo no sábado”), ligar/desligar e apagar.

As regras ficam no próprio servidor (`supabase/ranking.sql`): um aluno não consegue se promover nem se desbloquear, mesmo mexendo no app.

Sem o servidor configurado, a tela de entrada mostra **Começar a estudar** (o app funciona todo, só sem contas e ranking).

## Ranking (comparar com outras pessoas)

O ranking e as contas precisam de um servidor na internet. Usamos o **Supabase**, que tem plano grátis. Quem cuida do app configura **uma vez** (uns 10 minutos):

1. Crie uma conta em [supabase.com](https://supabase.com) e um projeto novo no plano **Free**.
2. No projeto, abra **SQL Editor**, cole todo o arquivo `supabase/ranking.sql` (está na pasta do app) e clique em **Run**.
3. Opcional: em **Authentication**, nas opções do login por e-mail, desligue **Confirm email** para as pessoas entrarem sem precisar confirmar o e-mail. Se deixar ligado, cada pessoa confirma pelo e-mail antes do primeiro acesso.
4. Em **Project Settings → API Keys**, copie a **Project URL** e a chave pública (**anon public** ou **publishable**).
5. No Aprova: na tela de entrada, **Ligar as contas online** (ou **Ajustes → Ranking → Servidor do ranking**), cole as duas e salve.
6. Crie a sua conta primeiro: a primeira conta vira **administrador**.

Se você já tinha rodado o `ranking.sql` da versão 1.5, rode o arquivo novo de novo: ele acrescenta os papéis e os comunicados sem apagar nada.

O passo 5 cria o arquivo `ranking.json` na pasta do app, que vai junto no .zip para os testadores.

Nunca coloque no app a chave **service_role** / **secret** (o Aprova recusa).

Como funciona:
- No ranking aparecem só o **apelido** e os **números da semana**. O e-mail fica escondido e a senha não fica no computador.
- Os números são enviados pelo próprio app de cada pessoa (ao abrir, a cada 15 minutos e ao terminar uma prova). O servidor recusa valores absurdos, mas o ranking é de confiança, entre quem estuda junto.
- Em **Minha conta** dá para mudar o apelido, sair ou **apagar a conta** e todos os dados do ranking.
- Plano grátis do Supabase: 500 MB de banco e até 50 mil usuários por mês; o projeto pausa depois de 7 dias sem nenhum uso (reative no painel do Supabase).

## Chave do Claude (opcional)

Em **Ajustes → Explicações com IA**, cole uma chave da API do Claude (crie em [platform.claude.com](https://platform.claude.com)). Com ela:

- a ajuda explica cada questão com fontes;
- provas em PDF difíceis de ler são organizadas pela IA na importação.

O uso da API é cobrado pela Anthropic. O modelo padrão é o Haiku, o mais barato.

## Onde ficam seus dados

Tudo fica no seu computador, na pasta `.aprova` dentro da sua pasta de usuário (`C:\Users\<você>\.aprova`): provas importadas, respostas, favoritos e ajustes. Os estudos de cada conta ficam em `.aprova\contas\<conta>`; os de quem usa sem conta, direto em `.aprova`. No servidor vão só o apelido, o concurso e os números da semana.

## Limites

- A leitura automática das questões depende do layout do PDF. Quando falha, a prova abre no modo cartão-resposta com as páginas originais. Figuras e tabelas aparecem pelo botão “Ver na prova original”.
- Provas com vários tipos de caderno podem ter gabaritos diferentes. Confira em **⋮ → Gabarito**.
- Se o PCI Concursos mudar o layout do site, a leitura das listas pode precisar de ajuste no arquivo `aprova/pci.py`.
- A leitura em voz alta funciona no computador (vozes do Windows). No celular, use o recurso de leitura do próprio aparelho.
- Os alarmes tocam com o Aprova aberto no computador (pode ficar minimizado).

## Para desenvolver

```
aprova/
  pci.py          leitura do PCI Concursos (concursos, editais, provas)
  fontes.py       busca central: sites das bancas, internet e PCI
  coleta.py       "Encher a biblioteca": baixa as provas de um concurso em lote
  analise.py      números do Painel (tempo, dias da semana, desempenho)
  sessoes.py      revisão espaçada, treino e "próximo estudo"
  livros.py       indicações de livros e material oficial
  ranking.py      cliente do servidor (Supabase: login, papéis, números da semana, grupos, admin)
supabase/         ranking.sql: tabelas, papéis e regras de acesso do servidor
  pdfprova.py     texto do PDF, questões, gabarito, imagens das páginas
  importador.py   importa PDFs para o banco
  ajuda.py        pesquisa na internet + dica
  ia.py           recursos opcionais com a API do Claude
  db.py           banco SQLite local
  voz.py          leitura em voz alta
  ui/             telas (Flet); login.py = entrada e conta, admin.py = tela do administrador
iniciar.pyw       abre o app sem console; instala o que faltar com uma janela de progresso
ferramentas/      ajudantes do instalador (achar e instalar o Python)
tests/            testes com páginas e PDFs de exemplo
```

Rodar os testes: `python -m pytest -q tests`

Testar contas sem internet: `python tests/servidor_falso.py 8788` sobe um servidor falso com 6 pessoas e o grupo `DATAPREV-7A2F`; aponte o app para `http://127.0.0.1:8788` com qualquer chave.

Versões: o projeto usa git, com uma etiqueta por versão (`git tag` lista; `git log --oneline` mostra o histórico).
