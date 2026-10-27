# Guia completo do Aprova (v1.9)

[← voltar ao início](../README.md) · Site e download: https://natanaelsantz.github.io/aprova/

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
  - **Sem repetição**: primeiro vêm as questões que você nunca fez, depois as feitas há mais tempo e por último as que já acertou. Acerto feito em simulado, treino ou revisão conta para a questão original. A que você errou espera o dia dela na Revisão. Quando as novas acabam, o app avisa.
  - **Sem questão esquisita**: questão com texto quebrado na leitura do PDF (letras separadas), alternativa faltando ou repetida fica de fora; sem gabarito só entra se faltar.
  - Com a chave do Claude, a IA completa o que faltar **e troca as que você já fez** por questões novas no estilo da banca, usando os assuntos do edital.
- **Resultado comentado**: no fim do simulado, o Aprova diz o que foi bem, em que matéria dá para ganhar mais pontos e qual o próximo passo (com botão para treinar a matéria). Embaixo vem **O que você errou**, matéria por matéria: o que você marcou, a resposta certa e o porquê. Com a chave do Claude, dá para pedir a **análise do professor (IA)**, com os assuntos para revisar e um plano de 3 dias.
  - Também dá para montar a partir do edital: botão “Montar simulado” na janela do concurso.
- **Onde focar**: cruza quanto cada disciplina cai nas suas provas com quanto você ainda erra. **Ver todas as disciplinas** mostra a lista inteira.
  - **Mini prova**: toque numa disciplina (por exemplo, *Conhecimentos Específicos*) para fazer uma prova só dela. Você escolhe:
    - *De qual prova*: todas da biblioteca ou só uma (útil quando os Conhecimentos Específicos mudam de cargo para cargo);
    - *Quantas questões*: 5, 10, 20, 30 ou todas;
    - *Como fazer*: **Prova** (com cronômetro e nota no fim) ou **Estudo** (vê a resposta e a explicação a cada questão).
  - Vêm primeiro as questões que você nunca fez. O acerto conta para a questão original e os erros vão para a Revisão, igual ao simulado.
- **Meta semanal (tela Início)**: o painel **Sua semana** mostra as horas estudadas e a meta, o ritmo (em dia, à frente ou quanto falta), a sequência de dias, o dia de hoje e as horas de cada dia em barras, com um tracinho na altura da meta do dia. Embaixo vem “Seu próximo estudo” (revisão do dia ou treino do ponto fraco).
- **Tempo de estudo**: conta sozinho enquanto você resolve questões (para depois de 8 minutos parado). Para estudo fora do app (livro, aula), use o **cronômetro** ou **lance o tempo** à mão.
- **Painel**:
  - *Desempenho*: acertos por disciplina com selo Forte / Atenção / Precisa melhorar, evolução nas últimas 8 semanas, acertos por banca e por concurso.
  - *Tempo*: meta, horas por dia, mapa das últimas 12 semanas, em que dias da semana você estuda e tempo por disciplina.
  - *Lembretes*: alarmes de atividades extras. Na hora, o app toca e leva você ao conteúdo: pesquisa na internet, vídeo-aulas, um link, a revisão, um treino ou um simulado.
  - *Livros*: indicações por disciplina, das mais fracas para as mais fortes, com material oficial gratuito (leis no Planalto).
- **Contas e login**: cada pessoa entra com e-mail e senha e tem seus estudos separados. Há dois tipos de conta: **aluno** e **administrador** (veja abaixo). Quem não quiser conta usa o app normalmente com “Usar sem conta”.
- **Tela que se ajusta ao aparelho**: no celular, menu embaixo; em tela média, menu lateral compacto; em tela grande, menu lateral completo e o conteúdo centralizado.
- **Grupos de estudo (fórum)**: cada grupo tem a sua conversa, onde a turma combina simulados, tira dúvidas, troca materiais (fotos e arquivos do computador), manda **GIFs e figurinhas** e compartilha **planos de estudo**. Só quem tem o convite entra e só quem está no grupo vê as mensagens. Fica no menu **Grupos**.
- **Personagem (estilo RPG) ou foto**: crie o seu bonequinho em pixel art (tipo de corpo, pele, cabelo, barba, olhos, boca, óculos, roupa, acessórios na cabeça, no pescoço e nas costas, item na mão e cenário) ou use uma foto. Ele respira, pisca, acena e pula; aparece no Início, comemora no resultado do simulado e fica na **sala da turma** dos grupos, com o personagem de todo mundo.
- **Convite por link**: em **Grupos → Convidar**, mande o link do grupo pelo WhatsApp, Telegram ou e-mail, ou salve uma imagem com QR code para os Stories do Instagram e o TikTok. Quem abre o link entra no grupo com um clique, sem digitar código nem preencher cadastro.
- **Ranking**: crie uma conta com apelido e compare horas, questões, acerto e sequência da semana com outras pessoas, no geral ou em grupos com código (a turma do concurso, os amigos). Fica em Painel → Ranking.
- **Revisão espaçada** (Estudar → Revisão): o que você erra ou marca com a bandeira volta no dia certo (1, 3, 7, 15 e 30 dias) até ficar dominado.
- **Dúvidas**: no painel de Ajuda de cada questão, escreva sua dúvida; o Aprova pesquisa na internet para responder (com a chave do Claude, a resposta vem explicada). Todas ficam guardadas em Estudar → Dúvidas.
- **Questões inéditas com IA**: a IA lê questões reais das provas do concurso na sua biblioteca, cria novas no mesmo estilo e confere o gabarito resolvendo cada uma de novo (precisa da chave do Claude). Também completa os simulados montados.
- **Conforto para os olhos**:
  - **Tamanho da interface** (Ajustes): automático, 80% a 125%. No automático, tudo fica menor em notebooks com o zoom do Windows em 125% ou 150%, para caber mais coisa na tela. Atalhos: Ctrl + e Ctrl − (Ctrl 0 volta ao automático).
  - Temas claro, sépia (leitura) e escuro.
  - Fonte Atkinson Hyperlegible, com tamanho e espaçamento ajustáveis.
  - Leitura em voz alta da questão.
  - Lembrete de pausa 20-20-20.
- **Celular**: o mesmo app abre no navegador do celular, na mesma rede Wi-Fi.
- **Marcar PDF** (Estudar → Marcar PDF): marca-texto em 4 cores, sublinhado e notas em qualquer PDF, e um PDF novo com as marcações, editáveis ou fixas. Veja [Marcar PDF](#marcar-pdf).
- **Atualização automática**: o app avisa no Início quando sai versão nova e atualiza com um toque. Veja [Atualizações](#atualizações).

## Como abrir no Windows

1. Extraia este .zip numa pasta (ex.: `Documentos\Aprova`).
2. Dê dois cliques em **`Abrir Aprova.bat`**. Na primeira vez aparece a janela **Preparando o Aprova**, com barra de progresso:
   - se o computador não tiver Python, ele é instalado antes, numa janela própria;
   - depois vêm as bibliotecas do app (de 5 a 10 minutos, precisa de internet).
3. No fim, o Aprova abre sozinho e cria o atalho **Aprova** na área de trabalho. Dali em diante, abra por ele: o app abre direto, sem janela preta.

Se algo der errado, a janela mostra o motivo e o botão **Tentar de novo**. Os detalhes ficam em `C:\Users\<você>\.aprova\instalacao.log`.
Se a instalação automática do Python falhar, instale o **Python 3.12 ou 3.13** em [python.org](https://www.python.org/downloads/), marque **“Add python.exe to PATH”** e abra o `.bat` de novo.

No macOS/Linux: `./iniciar.sh` (ou `./iniciar.sh --web` para o modo navegador).

## Atualizações

O Aprova se atualiza sozinho:

1. **Toda vez que abre**, ele confere se saiu versão nova. Se saiu, aparece a telinha *Atualizando para a versão…* por alguns segundos e o app já abre na versão nova. Sem internet, abre normalmente a versão que você tem.
2. **Com o app aberto**, ele confere de novo a cada 3 horas. Quando sai versão nova, ele baixa sozinho (uns 2 MB) e avisa por uma **notificação do Windows** e por um aviso embaixo da tela: toque em **Reiniciar agora**, ou deixe para a próxima vez que abrir.
3. Se não der para baixar sozinho, o aviso e o cartão **Nova versão do Aprova** no Início levam ao botão **Atualizar**.

(Quem está na 1.13 ou anterior recebe esta atualização do jeito antigo, pelo botão **Atualizar**; dali em diante, ela passa a ser automática ao abrir.)

Para procurar na hora: **Ajustes → Atualizações → Procurar atualização**.

Seus estudos, contas, ajustes e PDFs marcados ficam na pasta `.aprova` e não mudam. Se uma biblioteca nova for necessária, a janela *Preparando o Aprova* aparece ao reabrir e instala só o que falta. Uma cópia da versão anterior fica em `.aprova\atualizacao\anterior`.

Quem tem a versão 1.8 ou anterior precisa baixar o .zip uma última vez no [site](https://natanaelsantz.github.io/aprova/) e extrair por cima da pasta antiga (substituindo os arquivos). Os estudos não se perdem, porque ficam à parte, na pasta `.aprova`.

## Usar no celular

- Jeito mais fácil: no app, vá em **Ajustes → Usar no celular → Ligar acesso pelo celular** e aponte a câmera para o QR code.
- Ou abra **`Abrir no celular.bat`** e digite no celular o endereço inteiro que aparece na janela (ex.: `http://192.168.0.10:8550/?k=...`).
- O endereço tem um **código de acesso**: sem ele, ninguém no mesmo Wi-Fi abre o seu Aprova. O código muda cada vez que você liga o acesso.

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

## Marcar PDF

Em **Estudar → Marcar PDF → Abrir um PDF para marcar** (ou no **⋮** de uma prova da biblioteca → *Marcar e anotar o PDF*):

| Ferramenta | Como usar |
|---|---|
| **Marca-texto** | arraste sobre o texto; escolha a cor (amarelo, verde, azul ou rosa) nas bolinhas |
| **Sublinhar** | arraste sobre o texto |
| **Nota** | toque onde quer o balãozinho e escreva |
| **Ver** | toque numa marcação para escrever uma nota nela, trocar a cor ou apagar |

- A lista **Marcações**, ao lado (no celular, no botão de lista), mostra cada trecho marcado com a nota; tocar leva até a página.
- **Desfazer** (ou Ctrl+Z) tira a última marcação. As setas ← → trocam de página e as teclas 1 a 4 trocam de ferramenta.
- Tudo é guardado na hora, numa cópia do PDF dentro do Aprova. O arquivo original nunca muda. Para continuar depois, volte em **Estudar → Marcar PDF**.
- PDF escaneado (imagem, sem texto): o marca-texto marca a área que você arrastar.

**Salvar PDF** cria um arquivo novo na pasta de downloads, com duas opções:

- **Marcações editáveis** (padrão): ficam como anotações do PDF. Abrem em qualquer leitor (Edge, Chrome, Acrobat, celular) e ainda dá para mudar ou apagar.
- **Marcações fixas**: viram parte da página, como se tivessem sido impressas, e ninguém consegue apagar ou mudar. O texto das notas vai para as páginas **Minhas anotações**, no fim do arquivo.

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

## Personagem e foto de perfil

Clique na sua bolinha (no menu ou no canto do celular) e escolha **Personagem e foto**. Também dá pelo **Início** (no quadro do personagem) e por **Ajustes → Conta**.

- **Corpo, Rosto, Cabelo, Óculos, Roupa, Acessórios e Cenário**: cada aba muda uma parte do bonequinho. **Sortear** cria um aleatório; **Acenar** e **Pular** mostram os gestos.
  - *Corpo*: **magro**, **médio** (o padrão), **forte** (ombro largo) ou **gordinho**, e a cor da pele. Toda roupa, capa e mochila se ajusta ao corpo.
  - *Rosto*: olhos (normal, feliz, determinado, sonolento, piscadinha) e a cor deles (9, até brancos e roxos), boca (sorriso, sorrisão, séria, língua de fora, surpresa) e detalhes (sardas, pinta, bochecha corada, curativo).
  - *Cabelo*: 13 cortes (curto, repartido de lado, espetado, moicano, longo, chanel, coque, rabo de cavalo, maria-chiquinha, tranças, cacheado, black power, careca), 11 cores e **barba e bigode** (por fazer, bigode, cavanhaque, barba cheia), na cor do cabelo.
  - *Roupa*: moletom, camiseta, regata, jaqueta, vestido, terno, toga, farda, jaleco, manto de mago e armadura, com 11 cores, e a cor da calça (7).
  - *Óculos*: redondo, quadrado, meia armação, escuro, coração, monóculo e visor, com 8 cores de armação. Combinam com qualquer chapéu.
  - *Acessórios*: na cabeça (boné, gorro, capelo de formatura, coroa, tiara, chapéu de mago, capacete viking, fone, laço, flor, orelhas de gato, auréola, faixa), no pescoço e nas costas (cachecol, medalha, gravata-borboleta, colar, capa de herói, mochila) e na mão (livro, Vade Mecum, lápis gigante, marca-texto, café, diploma, troféu, espada, cajado).
- O desenho tem o dobro de pixels: olhos grandes estilo chibi (íris em degradê, pupila, brilho e faísca), sobrancelhas, mechas de brilho no cabelo, luz de lado e sombra na roupa, punho nas mangas, brilho nos sapatos e contorno fino.
- **Foto**: escolha uma imagem do computador. O Aprova recorta em quadrado, diminui e tira os dados escondidos da foto. Ligue **Mostrar a foto** para ela aparecer no lugar do personagem nos grupos e no ranking.
- **Onde aparece**: na sua bolinha do menu, no Início (o boneco no cenário), no resultado do simulado (ele comemora quando você vai bem e dá força quando não), nas mensagens e na lista de membros dos grupos, no ranking e na **sala da turma**.
- **Sala da turma**: no topo de cada grupo, os personagens de quem está no grupo aparecem juntos, como no lobby de um jogo. Quem ainda não criou o seu aparece com um personagem sorteado. **Esconder** guarda a sala.
- Sem conta, o personagem fica só neste computador; quando você entra numa conta, ele vai junto. Com conta, ele também vai para outro computador em que você entrar.
- O servidor guarda só as escolhas do personagem (uma lista curta, sem texto livre) e a foto pequena. O administrador pode apagar uma foto imprópria em **Admin → Usuários**.

## Grupos de estudo e fórum

No menu **Grupos**:

- **Criar grupo** (quem cria vira **moderador**) e **Convidar**: o botão abre o link do grupo para mandar pelo WhatsApp, Telegram, e-mail, Instagram ou TikTok (veja abaixo). Também dá para **Entrar com código**.
- **Conversa**: escreva para a turma e escolha o tipo: *Conversa*, *Dúvida* ou *Material* (links viram o botão “Abrir link”). Cada mensagem tem **Útil** e **Responder**.
- **Planos de estudo**: em **Compartilhar um plano**, coloque as horas por semana de cada disciplina, os dias de estudo e como usar. Quem gostar toca em **Usar este plano**: a meta semanal e os dias passam a ser os do plano, e a tela **Início** mostra quanto você já estudou de cada disciplina na semana.
- **Fotos, arquivos, GIFs e figurinhas**: na caixa de mensagem (e nas respostas), o **clipe** manda fotos e arquivos do computador (PDF, Word, Excel, PowerPoint, imagens, GIF, áudio, vídeo MP4, TXT e ZIP, até 20 MB cada e 10 por mensagem; foto grande de celular é reduzida sozinha). A **carinha** abre as **figurinhas do Aprova** (Bora estudar!, Passei!, Gabaritei, Café + lei seca…) e, se o administrador ligar, a busca de **GIFs** e figurinhas animadas do GIPHY. Fotos e GIFs aparecem na conversa (clique para ampliar); arquivos têm **Abrir** e **Salvar**. Só quem é do grupo vê os arquivos.
  - *Mandar figurinha ou GIF*: o toque põe a figurinha na **prévia da mensagem** (como no Teams), sem mandar. Dá para escrever algo junto, trocar por outra ou tirar no **X**; ela vai quando você clica em **Publicar** (nas respostas, Enter ou a setinha). Só figurinha aparece na hora na conversa (“enviando…”). A aba **Recentes** guarda as últimas que você usou.
  - Mensagem que é só figurinha aparece compacta, sem moldura em volta do desenho, com **Útil** e **Responder** ao lado. Nas respostas, a figurinha também vem sem o balão.
- **Minhas figurinhas (as do WhatsApp)**: na carinha, aba **Minhas**. **Importar** aceita figurinhas soltas (.webp, .png, .gif, .jpg) e pacotes (.wastickers, ou o .zip de uma conversa exportada: o Aprova pega as figurinhas de dentro). **Colar** (ou Ctrl+V) traz a imagem que você copiou; no WhatsApp Web, clique com o botão direito na figurinha → Copiar imagem. No Android, as figurinhas ficam na pasta WhatsApp › Media › WhatsApp Stickers (no Android 11 ou mais novo, dentro de Android › media › com.whatsapp). Figurinha que alguém mandou no grupo: clique nela → **Guardar nas minhas figurinhas**; foto ampliada tem **Virar figurinha**. As figurinhas ficam no seu computador, separadas por conta; animadas continuam animadas.
- **Ranking** do grupo (horas da semana) e **Membros**.
- **Moderação**: quem criou o grupo (e o administrador) **fixa** recados no topo e **apaga** mensagens. Cada pessoa apaga as próprias. Conta bloqueada pelo admin não escreve.
- Mensagens novas aparecem num aviso na tela **Início** (“Novidades nos seus grupos”).
- O administrador vê o fórum de qualquer grupo em **Admin → Grupos → Ver fórum**, para moderar.

### Convite por link

Em **Grupos → Convidar**:

- **WhatsApp**, **Telegram** e **E-mail** abrem a mensagem pronta com o link.
- **Instagram** e **TikTok** não deixam compartilhar direto do computador. O Aprova salva na pasta Downloads uma **imagem 1080×1920 com QR code** para os Stories e o TikTok, e copia o link para você colar no adesivo de link, na bio ou no direct.
- **Copiar link** e **Copiar mensagem pronta** servem para qualquer outro lugar.

O link é assim: `https://natanaelsantz.github.io/aprova/convite/?g=CODIGO`. Quem abre:

1. Vê o nome do grupo e quantas pessoas estudam nele.
2. Clica em **Entrar no grupo**. Se já tem o Aprova, o app abre sozinho (endereço `aprova://`, registrado no Windows quando o Aprova abre pela primeira vez).
3. Se tem conta, já entra no grupo. Se não tem, só confere o apelido sugerido e toca em **Entrar no grupo** (conta rápida, sem e-mail e senha).
4. Se ainda não tem o Aprova: baixa pela própria página. O link fica copiado e, quando o app abre, ele encontra o convite e oferece entrar no grupo.

O grupo é fechado: ninguém encontra o grupo procurando, e só entra quem tem o link do convite. A conversa, as fotos e os arquivos aparecem só para quem é do grupo, então mande o link só para a sua turma.

No celular, a página explica que o Aprova é para computador e oferece copiar o link ou mandar para si mesmo no WhatsApp.

A **conta rápida** fica só naquele computador. Para entrar de outro lugar, a pessoa coloca e-mail e senha em **Minha conta → Proteger minha conta**.

No celular, a barra de baixo mostra Início, Concursos, Provas, Estudar, Grupos e Painel; **Ajustes** (e **Administração**, para o admin) ficam no menu do seu avatar, na tela Início.

## Ranking (comparar com outras pessoas)

O ranking e as contas precisam de um servidor na internet. Usamos o **Supabase**, que tem plano grátis. Quem cuida do app configura **uma vez** (uns 10 minutos):

1. Crie uma conta em [supabase.com](https://supabase.com) e um projeto novo no plano **Free**.
2. No projeto, abra **SQL Editor**, cole todo o arquivo `supabase/ranking.sql` (está na pasta do app) e clique em **Run**.
3. Em **Authentication → Sign In / Providers**: desligue **Confirm email** (as pessoas entram sem confirmar o e-mail) e ligue **Allow anonymous sign-ins** e **Allow manual linking** (conta rápida dos convites e "Proteger minha conta").
4. No botão **Connect** do projeto (ou em **Settings → API Keys**), copie a **Project URL** e a chave pública (**publishable** ou **anon**).
5. No Aprova: na tela de entrada, **Ligar as contas online** (ou **Ajustes → Ranking → Servidor do ranking**), cole as duas e salve.
6. Crie a sua conta primeiro: a primeira conta vira **administrador**.

Se você já tinha rodado o `ranking.sql` de uma versão anterior, rode o arquivo novo de novo: ele acrescenta o que falta (papéis, comunicados, fórum dos grupos) sem apagar nada.

O passo 5 cria o arquivo `ranking.json` na pasta do app. O servidor oficial do Aprova vem em `aprova/servidor.json` (endereço e chave pública), então quem baixa o app já entra nele; o `ranking.json`, quando existe, vale mais.

Nunca coloque no app a chave **service_role** / **secret** (o Aprova recusa).

Como funciona:
- No ranking aparecem só o **apelido** e os **números da semana**. O e-mail fica escondido e a senha não fica no computador.
- Os números são enviados pelo próprio app de cada pessoa (ao abrir, a cada 15 minutos e ao terminar uma prova). O servidor recusa valores absurdos, mas o ranking é de confiança, entre quem estuda junto.
- Em **Minha conta** dá para mudar o apelido, sair ou **apagar a conta** e todos os dados do ranking.
- Plano grátis do Supabase: 500 MB de banco e até 50 mil usuários por mês; o projeto pausa depois de 7 dias sem nenhum uso (reative no painel do Supabase).

## IA: sem chave (chat) ou com a chave do Claude

**Sem chave, de graça:** na ajuda de cada questão e no resultado do simulado, os botões **Perguntar ao Claude** e **Perguntar ao ChatGPT** abrem o chat no navegador com a pergunta já escrita (a questão, as alternativas e o que você marcou; no resultado, os seus erros com o pedido de um plano de 3 dias). Funciona com a conta grátis de cada um. A pergunta também vai para a área de transferência: se o chat abrir vazio, cole com Ctrl+V e envie. Durante o simulado, a pergunta não leva o gabarito (para não estragar o simulado).

**Com a chave do Claude, a IA trabalha dentro do app:** explica cada questão com fontes, cria questões novas nos simulados (no lugar das que faltam ou que você já fez), dá a **análise do professor** no resultado e organiza provas em PDF difíceis de ler.

Como conseguir a chave (também tem esse passo a passo no app, em **Ajustes → Explicações com IA → Passo a passo**):

1. Entre em [platform.claude.com](https://platform.claude.com) (o Claude Console) e crie uma conta.
2. Em **Billing**, coloque crédito com cartão. É pré-pago: você só gasta o que colocou. A assinatura do Claude Pro não inclui esse crédito; os planos Max e Team vêm com um crédito por mês.
3. Em **API keys** ([platform.claude.com/settings/keys](https://platform.claude.com/settings/keys)), clique em **Create key**, dê o nome Aprova e copie a chave (começa com `sk-ant-` e aparece uma vez só).
4. No Aprova, em **Ajustes → Explicações com IA**, cole a chave e clique em **Salvar**.

A chave é como um cartão: quem tiver a chave gasta o seu crédito, então não mande no grupo nem mostre em print. Ela fica guardada só no seu computador. A chave do ChatGPT (OpenAI) não funciona no lugar da do Claude. O modelo padrão é o Haiku, o mais barato.

## Onde ficam seus dados

Tudo fica no seu computador, na pasta `.aprova` dentro da sua pasta de usuário (`C:\Users\<você>\.aprova`): provas importadas, respostas, favoritos, ajustes e PDFs marcados (pasta `marcados`). Os estudos de cada conta ficam em `.aprova\contas\<conta>`; os de quem usa sem conta, direto em `.aprova`. No servidor vão só o apelido, o concurso e os números da semana.

## Se não abrir na primeira vez

Na primeira vez, o Aprova baixa do GitHub a janela do app (uns 30 MB). Se aparecer **CERTIFICATE_VERIFY_FAILED** (certificado), é um antivírus que inspeciona a internet, a rede da escola ou empresa, ou um Windows novo que ainda não tem o certificado do GitHub. A partir da versão 1.14.1 o Aprova verifica o certificado pelo próprio Windows, como o navegador. Quem tem uma versão mais antiga resolve assim:

1. Baixe o Aprova de novo pelo site e extraia por cima da pasta antiga (os estudos ficam guardados à parte, em `.aprova`, e não se perdem).
2. Abra o **Abrir Aprova.bat**. Ele instala o que falta e abre.
3. Se ainda falhar, tente uma vez em outra rede (por exemplo, o roteador do celular). Depois da primeira abertura, ele não precisa baixar de novo.

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
  sessoes.py      revisão espaçada, treino, mini prova e "próximo estudo"
  livros.py       indicações de livros e material oficial
  ranking.py      cliente do servidor (Supabase: login, papéis, números da semana, grupos, admin)
supabase/         ranking.sql: tabelas, papéis e regras de acesso do servidor
  pdfprova.py     texto do PDF, questões, gabarito, imagens das páginas
  importador.py   importa PDFs para o banco
  ajuda.py        pesquisa na internet + dica
  ia.py           recursos opcionais com a API do Claude
  db.py           banco SQLite local
  voz.py          leitura em voz alta
  convite.py      link de convite, endereço aprova://, imagem com QR code para Stories
  servidor.json   servidor padrão (endereço e chave pública do Supabase)
  ui/             telas (Flet); login.py = entrada e conta, admin.py = administrador, grupos.py = grupos e fórum
docs/             site no GitHub Pages: página inicial e página do convite (docs/convite)
iniciar.pyw       abre o app sem console; instala o que faltar com uma janela de progresso
ferramentas/      ajudantes do instalador (achar e instalar o Python)
tests/            testes com páginas e PDFs de exemplo
```

Rodar os testes: `python -m pytest -q tests`

Testar as regras do servidor num PostgreSQL de verdade (opcional): `APROVA_PG="host=... port=... user=postgres dbname=postgres" python -m pytest tests/test_sql_supabase.py` (o banco é recriado do zero; use um só para testes).

Testar contas sem internet: `python tests/servidor_falso.py 8788` sobe um servidor falso com 6 pessoas e o grupo `DATAPREV-7A2F` (com conversa e um plano de estudo de exemplo); aponte o app para `http://127.0.0.1:8788` com qualquer chave.

Versões: o projeto usa git, com uma etiqueta por versão (`git tag` lista; `git log --oneline` mostra o histórico).
