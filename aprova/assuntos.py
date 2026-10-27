"""Assunto de cada questão dentro da disciplina (Crase, Concordância... dentro de Português).

O Painel mostra o acerto por assunto: "Português 60%" vira "Crase 40% · Concordância 85% · ...", e dá
para saber exatamente o que estudar. O assunto é reconhecido pelas palavras do enunciado e das
alternativas (regras abaixo, da mais específica para a mais geral). Questão que não bate com nenhuma
regra fica em "Outros assuntos". Só as disciplinas mais comuns dos concursos têm regras.
"""

from __future__ import annotations

import json
import re
import unicodedata

OUTROS = "Outros assuntos"
MINIMO = 3  # com menos respostas, o assunto aparece como "poucos dados"


def _norm(t: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(ch) != "Mn")


# (assunto, padrão) por família de disciplina; o primeiro que bate vale
_R = {
    "portugues": [
        ("Crase", r"\bcrase\b|acento grave|acento indicativo"),
        ("Concordância", r"\bconcordancia\b|concorda(m|r)? (verbal|nominal)|\bconcorda(m)? com\b"),
        ("Regência", r"\bregencia\b|\brege\b|regido"),
        ("Colocação pronominal", r"colocacao (pronominal|do pronome)|\bproclise\b|\benclise\b|\bmesoclise\b|pronome obliquo atono"),
        ("Pontuação", r"\bpontuacao\b|\bpontuad|\bvirgula|ponto e virgula|\btravessao|dois[- ]pontos|sinal de pontuacao"),
        ("Acentuação e ortografia", r"\bacentua|\bortografi|\bgrafia\b|\bhifen\b|acento (agudo|circunflexo|grafico)|novo acordo"),
        ("Tempos e modos verbais", r"tempo verbal|modo (subjuntivo|indicativo|imperativo)|\bsubjuntivo\b|\bpreterito|\bfuturo do\b|locucao verbal|forma verbal|voz passiva|voz ativa"),
        ("Pronomes", r"\bpronome|\bpronominal|\bqual(quer)? pronome|\bcujo\b|\bonde\b.{0,20}\bemprego"),
        ("Orações e sintaxe", r"\boracao|\boracoes|sujeito|predicado|objeto (direto|indireto)|adjunto|aposto|vocativo|complemento nominal|\bsintatic|periodo composto|subordinad|coordenad|conjuncao|conectivo"),
        ("Classes de palavras", r"classe gramatical|\bcircunstancia\b|\bplural\b|\bsingular\b|\bflexao|\bfeminino de\b|\bmasculino de\b|\bsubstantivo|\badjetivo|\badverbio|\bpreposicao|\bartigo\b|\binterjeicao|\bnumeral|morfolog"),
        ("Semântica e vocabulário", r"\bsinonimo|\bantonimo|sentido (figurado|denotativo|conotativo|proprio)|\bsignificado\b|\bsemantic|pode ser substituid|substituicao de|polissemia|homonim|paronim"),
        ("Figuras de linguagem", r"figura de linguagem|\bmetafora|\bmetonimia|\bironia\b|\bhiperbole|\beufemismo|\bantitese|\bprosopopeia|personificacao"),
        ("Redação oficial", r"redacao oficial|manual de redacao|\boficio\b|pronome de tratamento|vossa (excelencia|senhoria)|\bmemorando\b"),
        ("Interpretação de texto", r"\btexto\b|\btrecho\b|\bautor\b|\bnarrador\b|\bparagrafo\b|\binfere-se\b|depreende|de acordo com o|segundo o texto|ideia central|tipologia|genero textual|coesao|coerencia"),
    ],
    "matematica": [
        ("Juros e matemática financeira", r"\bjuros?\b|\bmontante\b|capitaliza|taxa de .{0,15}(ao mes|ao ano|a\.m|a\.a)|desconto (simples|composto|comercial|racional)"),
        ("Porcentagem", r"porcent|percent|%"),
        ("Razão, proporção e regra de três", r"\d+ (servidores|operarios|funcionarios|pessoas|maquinas|torneiras|trabalhadores|tecnicos)\b.{0,80}\bem \d+ (dias|horas|minutos)|\brazao\b|\bproporc|regra de tres|grandezas|diretamente proporcional|inversamente proporcional|\bescala\b"),
        ("Probabilidade", r"probabilidade|\bchance\b|ao acaso|aleatoriamente"),
        ("Análise combinatória", r"de quantas (maneiras|formas)|quantos .{0,30}(diferentes|distintos) .{0,20}(podem|e possivel)|\bpermuta|\barranjo|\bcombinac|anagrama"),
        ("Estatística", r"\bmedia\b|\bmediana\b|\bmoda\b|desvio padrao|\bvariancia\b|\bfrequencia\b|\bgrafico\b|\btabela\b"),
        ("Geometria", r"\barea\b|\bperimetro\b|\bvolume\b|\btriangulo|\bquadrado\b|\bretangulo|\bcirculo\b|\bcircunferencia|\braio\b|\bangulo|\bcubo\b|\bcilindro|\bpitagoras|\bhipotenusa"),
        ("Progressões (PA e PG)", r"progressao (aritmetica|geometrica)|\bp\.?a\.?\b|\bp\.?g\.?\b|\brazao da\b"),
        ("Equações e funções", r"\bequacao|\bequacoes|\bsistema\b|\bfuncao\b|\bf\(x\)|\binequac|\braiz|\braizes|\bpolinom"),
        ("Operações e frações", r"\bfrac|\bmmc\b|\bmdc\b|\bdivis|\bmultiplica|\bpotencia|\bnumeros? (inteiros|naturais|racionais|primos?)|\bdecimal"),
    ],
    "logica": [
        ("Verdades e mentiras", r"\bmente(m)?\b|\bmentiroso|sempre dizem? a verdade|\bverdade e quem\b"),
        ("Quantificadores e silogismos", r"\btodo[s]?\b.{1,40}\b(e|sao)\b|\bnenhum\b|\balgum\b.{1,40}\b(e|sao)\b|\bsilogismo|\bargumento\b|\bconclusao valida|\bpremissa"),
        ("Proposições e conectivos", r"\bproposic|\bconectivo|tabela[- ]verdade|\bse\b.{1,60}\bentao\b|\bcondicional|\bbicondicional|\bnegacao\b|\bequivalen|\btautologia|\bcontradicao|\bconjuncao\b|\bdisjuncao\b|logicamente equivalente"),
        ("Conjuntos", r"\bconjunto|\bdiagrama|\buniao\b|\bintersec|\bvenn\b|apenas um dos|ambos os"),
        ("Análise combinatória", r"de quantas (maneiras|formas)|\bpermuta|\barranjo|\bcombinac|anagrama"),
        ("Probabilidade", r"probabilidade|ao acaso|aleatoriamente"),
        ("Sequências e padrões", r"\bsequencia|\bproximo termo|\bpadrao\b|\bseguinte termo|\bem ordem\b|\blogica (de|da) sequencia|\bfigura seguinte"),
        ("Matemática básica (%, frações, regra de três)", r"%|porcent|\bfrac|regra de tres|\brazao\b|\bproporc|\bjuros|\bmedia\b"),
        ("Problemas e raciocínio", r"\bidade|\bmesa\b|\bfila\b|\bposicao|\bcalendario|\bdia da semana|\brelogio|\bgaveta"),
    ],
    "informatica": [
        ("Segurança da informação", r"\bgolpe|\bfraud|\bimita\b|se passa por|\bvirus\b|\bmalware|\bphishing|\bransomware|\bspyware|\btrojan|cavalo de troia|\bworm\b|\bfirewall|\bbackup|\bcriptograf|\bantivirus|\bsenha\b|autenticacao|engenharia social|certificado digital|assinatura digital"),
        ("Planilhas (Excel/Calc)", r"\bexcel\b|\bcalc\b|planilha|\bcelula|\b=soma|\bprocv|\bsomase|\bformula"),
        ("Editores de texto (Word/Writer)", r"\bword\b|\bwriter\b|editor de texto|\bparagrafo\b|\bfonte\b|\brecuo|\bcabecalho|\brodape|\bmala direta"),
        ("Apresentações", r"powerpoint|\bimpress\b|\bslide"),
        ("Internet, e-mail e navegadores", r"\bnavegador|\bchrome\b|\bfirefox|\bedge\b|\burl\b|\bhttps?\b|\be-?mail\b|\bcorreio eletronico|\boutlook|\bthunderbird|\bcookies?\b|\bhistorico de navegacao|\bdownload"),
        ("Redes e protocolos", r"\bprotocolo|\btcp\b|\bip\b|\bdns\b|\bsmtp|\bpop3?\b|\bimap|\bftp\b|\brede (local|de computadores)|\blan\b|\bwan\b|\broteador|\bswitch|\bwi-?fi"),
        ("Nuvem", r"\bnuvem\b|\bcloud|\bonedrive|\bgoogle drive|\bdropbox|\bsaas\b|\biaas\b|\bpaas\b"),
        ("Sistemas operacionais", r"\bwindows\b|\blinux\b|\bpasta\b|\barquivo\b|\bexplorador de arquivos|\bwindows explorer|\bpainel de controle|\bterminal\b|\bteclas? de atalho|\bctrl\b|\blixeira"),
        ("Hardware", r"\bhardware|\bprocessador|\bcpu\b|\bmemoria ram|\bram\b|\brom\b|\bhd\b|\bssd\b|\bperiferico|\bplaca-?mae"),
    ],
    "constitucional": [
        ("Controle de constitucionalidade", r"controle de constitucionalidade|\badi\b|\badc\b|\badpf\b|acao direta|inconstitucional"),
        ("Direitos e garantias fundamentais", r"direitos? (e garantias )?fundamenta|\bart\.? ?5|habeas (corpus|data)|mandado de (seguranca|injuncao)|acao popular|\binviolab|\bliberdade de|\bigualdade\b"),
        ("Direitos sociais", r"direitos sociais|\bart\.? ?[67]\b|\btrabalhador|\bsalario minimo|\bferias\b|\bsindic"),
        ("Nacionalidade e direitos políticos", r"\bnacionalidade|\bbrasileiro nato|\bnaturaliza|direitos politicos|\belegib|\binelegib|\bvoto\b|\bsufragio|\balistamento"),
        ("Administração pública (art. 37)", r"\bart\.? ?3[789]|administracao publica|\bservidor(es)? public|\bconcurso publico|\bteto remuneratorio|\bacumulacao de cargos"),
        ("Poderes e processo legislativo", r"poderes da uniao|independentes e harmonicos|separacao (dos|de) poderes|poder (legislativo|executivo|judiciario)|\bcongresso|\bcamara dos deputados|\bsenado|\bmedida provisoria|\bemenda constitucional|\bprocesso legislativo|\bpresidente da republica|\bstf\b|\bstj\b|\bcnj\b|\btribunal de contas|\bcpi\b"),
        ("Organização do Estado", r"\buniao\b|\bestados?-membros?|\bmunicipios?\b|\bdistrito federal|\bcompetencia (privativa|comum|concorrente|exclusiva)|\bintervencao federal|\bterritorios?\b|\bfederacao"),
        ("Princípios fundamentais", r"principios fundamentais|\bart\.? ?[1-4]\b|\bfundamentos da republica|\bobjetivos fundamentais|\bsoberania|\bdignidade da pessoa"),
    ],
    "administrativo": [
        ("Licitações e contratos", r"\blicita|\bpregao|\bdispensa\b|\binexigib|\bcontrato administrativo|\b14\.?133|\b8\.?666|\bconcorrencia\b|\bata de registro"),
        ("Improbidade administrativa", r"\bimprobidade|\b8\.?429"),
        ("Processo administrativo", r"processo administrativo|\b9\.?784"),
        ("Agentes públicos e servidores", r"\b8\.?112|\bconcurso publico|\binvestidura|\bservidor(es)?\b|\bagentes? publicos?|\bestagio probatorio|\bestabilidade|\bcargo (efetivo|em comissao)|\bposse\b|\bexercicio\b|\bvacancia|\bremocao|\bredistribuicao|\bpenalidade|\bdemissao|\bsuspensao\b|\badvertencia"),
        ("Responsabilidade civil do Estado", r"responsabilidade (civil|objetiva|extracontratual)|\bart\.? ?37,? ?§ ?6|\bdano\b.{0,40}\b(estado|administracao)|direito de regresso"),
        ("Atos administrativos", r"\bato(s)? administrativo|\bvinculado|\bdiscricionari|\banulacao|\brevogacao|\bconvalidacao|\bmotivo\b|\bmotivacao|\batributos do ato|\bpresuncao de legitimidade|\bautoexecutoriedade|\bimperatividade"),
        ("Poderes administrativos", r"poder (de policia|hierarquico|disciplinar|regulamentar|normativo)|\bpoderes administrativos|\babuso de poder|\bdesvio de (poder|finalidade)|\bexcesso de poder"),
        ("Organização administrativa", r"\bautarquia|\bfundacao publica|\bempresa publica|\bsociedade de economia mista|\bdescentraliza|\bdesconcentra|\badministracao (direta|indireta)|\bagencia reguladora|\bconsorcio publico|\bterceiro setor|\boscip\b|organizac(ao|oes) socia(l|is)"),
        ("Controle da administração", r"\bcontrole (interno|externo|judicial|administrativo)|\btribunal de contas|\bautotutela|\bsumula 473"),
        ("Princípios da administração", r"\bprincipio|\blegalidade\b|\bimpessoalidade|\bmoralidade|\bpublicidade\b|\beficiencia|\blimpe\b|\brazoabilidade|\bproporcionalidade|\bsupremacia do interesse"),
    ],
}
_PADROES = {fam: [(a, re.compile(p)) for a, p in regras] for fam, regras in _R.items()}


def familia(disciplina: str) -> str | None:
    """A disciplina tem regras de assunto? Devolve a família ("portugues", "matematica"...) ou None."""
    d = _norm(disciplina)
    if "portugu" in d or "lingua patria" in d:
        return "portugues"
    if "raciocinio" in d or "logic" in d:
        return "logica"
    if "matemat" in d:
        return "matematica"
    if "informat" in d or "tecnologia da informacao" in d and "conhecimentos" not in d:
        return "informatica"
    if "constitucional" in d:
        return "constitucional"
    if "administrativ" in d and "direito" in d:
        return "administrativo"
    return None


def assunto(disciplina: str, enunciado: str, alternativas: dict | str | None = None) -> str:
    """O assunto da questão (ou OUTROS). O enunciado vale mais: só olha as alternativas se ele não decidir."""
    fam = familia(disciplina)
    if fam is None:
        return OUTROS
    if isinstance(alternativas, str):
        try:
            alternativas = json.loads(alternativas or "{}")
        except ValueError:
            alternativas = {}
    regras = _PADROES[fam]
    for texto in (_norm(enunciado), _norm(" ".join(str(v) for v in (alternativas or {}).values()))):
        if not texto:
            continue
        for nome, padrao in regras:
            if padrao.search(texto):
                return nome
    return OUTROS


def desempenho(banco, disciplina: str) -> list[dict]:
    """Acerto por assunto numa disciplina: [{"assunto", "acertos", "total", "taxa"}], o pior primeiro.

    Assuntos com menos de MINIMO respostas vão para o fim (poucos dados)."""
    if familia(disciplina) is None:
        return []
    cont: dict[str, list[int]] = {}
    for q, correta in banco.respostas_com_questao(disciplina):
        nome = assunto(disciplina, q.get("enunciado") or "", q.get("alternativas"))
        a = cont.setdefault(nome, [0, 0])
        a[0] += 1 if correta else 0
        a[1] += 1
    itens = [{"assunto": n, "acertos": a, "total": t, "taxa": a / t if t else None} for n, (a, t) in cont.items()]
    itens.sort(key=lambda i: (i["total"] < MINIMO, i["assunto"] == OUTROS, i["taxa"] if i["taxa"] is not None else 1, -i["total"]))
    return itens
