"""Motor do comparador de textos legislativos (sem IA).

Do PDF ao quadro comparativo:
  1. extrair(pdf)        texto do PDF (pdftotext; leitura óptica se o PDF for escaneado)
  2. articulado(texto)   limpa cabeçalhos e rodapés repetidos e acha o trecho com os artigos
  3. artigos(texto)      separa os artigos e, dentro deles, os dispositivos
  4. comparar(a, b)      emparelha artigos e dispositivos e calcula as diferenças palavra a palavra

Funciona com textos da Câmara, do Senado e com PDFs enviados, desde que tenham artigos ("Art. 1º").
"""
import re, html, difflib, shutil, subprocess, collections

# ---------------------------------------------------------------- 1. extração
def extrair(pdf_path):
    """Texto do PDF. Se quase não houver texto (PDF escaneado), roda o OCR e tenta de novo."""
    txt = _pdftotext(pdf_path)
    if len(re.sub(r'\s', '', txt)) >= 400:
        return txt, False
    if not shutil.which('ocrmypdf'):
        subprocess.run('sudo apt-get install -y -qq ocrmypdf tesseract-ocr-por >/dev/null', shell=True, check=False)
    ocr = pdf_path + '.ocr.pdf'
    subprocess.run(['ocrmypdf', '-q', '-l', 'por', '--force-ocr', '--output-type', 'pdf', pdf_path, ocr], check=False, timeout=1800)
    try:
        return _pdftotext(ocr), True
    except Exception:
        return txt, True

def _pdftotext(p):
    r = subprocess.run(['pdftotext', '-layout', p, '-'], capture_output=True, timeout=300)
    return r.stdout.decode('utf-8', 'replace')

# ---------------------------------------------------------------- 2. limpeza e trecho articulado
RUIDO = [r'^Apresentação: ?\d', r'^\*?CD\d{6,}\*?$', r'Assinad[oa] eletronicamente', r'Autenticad[oa] eletronicamente',
         r'^Para verificar a assinatura', r'^o original\.?$', r'^SF/\d', r'^temp-', r'^\d+$', r'^\d+ ?/ ?\d+$', r'^Página \d+',
         r'^Documento eletrônico assinado', r'^Senado Federal\s+\d+$', r'^C[âa]mara dos Deputados\s+\d+$', r'^https?://\S+$', r'código CRC', r'^PRLP \d+ => ', r'^Avulso d', r'^\*\d{10,}\*$']
RUIDO_RE = [re.compile(p, re.I) for p in RUIDO]
INICIO = re.compile(r'^\s*[“"]?Art\. ?1 ?[º°o]?[\s.]', re.M)
ART_LINHA = re.compile(r'^\s*[“"]?Art\. ?\d+(?:-[A-Z])?', re.M)
FIM = re.compile(r'^\s*(Sala das Sess[õo]es|Sala da Comiss[ãa]o|Bras[ií]lia, ?(em )?\d|JUSTIFICA[ÇC][ÃA]O|EXPOSI[ÇC][ÃA]O DE MOTIVOS|'
                 r'Bras[ií]lia,?\s*$|EMI n|Senado Federal, em|C[âa]mara dos Deputados, em|PARECER N|Relat[óo]ri[oa]\b|EM n[ºo°]|Deputad[oa] .{3,60}\s*$|Senador[a]? .{3,60}\s*$|'
                 r'Presidente\s*$|Relator[a]?\s*$|I\s*[-–]\s*RELAT[ÓO]RIO|II\s*[-–]\s*AN[ÁA]LISE|III\s*[-–]\s*VOTO)', re.M | re.I)

def limpar(txt):
    """Remove cabeçalhos e rodapés: linhas que se repetem em várias páginas, mas só nas bordas da página
    (as quatro primeiras e as quatro últimas linhas), para não apagar texto legal que se repete."""
    paginas = [[l.strip() for l in pg.split('\n')] for pg in txt.split('\f')]
    def bordas(pg):
        cheias = [k for k, l in enumerate(pg) if l]
        return set(cheias[:4] + cheias[-4:])
    cont = collections.Counter()
    for pg in paginas:
        for k in bordas(pg):
            cont[pg[k]] += 1
    n = max(len(paginas), 1)
    repetidas = {l for l, c in cont.items() if c >= 3 and c >= 0.25 * n and not ART_LINHA.match(l) and len(l) < 160}
    linhas = []
    for pg in paginas:
        b = bordas(pg)
        for k, s in enumerate(pg):
            if (k in b and s in repetidas) or any(r.search(s) for r in RUIDO_RE):
                continue
            linhas.append(s)
    return '\n'.join(linhas)

def articulado(txt):
    """Escolhe o trecho com mais artigos (num parecer: o substitutivo, não o relatório)."""
    t = limpar(txt)
    inicios = [m.start() for m in INICIO.finditer(t)]
    if not inicios:
        raise ValueError('O documento não tem texto articulado ("Art. 1º"). O comparador só funciona com projetos, substitutivos, emendas e leis.')
    melhor = None
    for k, ini in enumerate(inicios):
        lim = inicios[k + 1] if k + 1 < len(inicios) else len(t)
        trecho = t[ini:lim]
        # corta no primeiro marcador de fim depois do último artigo em sequência
        arts = list(ART_LINHA.finditer(trecho))
        fim = len(trecho)
        for m in FIM.finditer(trecho):
            if m.start() > (arts[-1].start() if arts else 0):
                fim = m.start(); break
            # marcador de fim antes do último artigo: só vale se vier depois de uma "vigência"
            ant = trecho[:m.start()]
            if re.search(r'entra(rá)? em vigor[^\n]*\n', ant[-400:]):
                fim = m.start(); break
        trecho = trecho[:fim]
        qtd = len(ART_LINHA.findall(trecho))
        if melhor is None or qtd >= melhor[0]:
            melhor = (qtd, trecho)
    return melhor[1].strip()

# ---------------------------------------------------------------- 3. artigos e dispositivos
TITULOS = re.compile(r'^\s*[“"]?((?:LIVRO|T[ÍI]TULO|CAP[ÍI]TULO|Se[çc][ãa]o|Subse[çc][ãa]o) [IVXLC]+(?:-[A-Z])?)\b.*$', re.M)
DISP = r'(§ ?\d+[º°o]?|Parágrafo único\.|[IVXLC]+ ?[-–] |[a-z]\) |\d+(?:\.|\)| ?[-–]) (?=[a-zà-úA-ZÀ-Ú]))'
DISP1 = re.compile(r'(?<=[.;:])\s(?=' + DISP + ')')
DISP2 = re.compile(r'(?<=; ou)\s(?=' + DISP + ')')
DISP3 = re.compile(r'(?<=; e)\s(?=' + DISP + ')')

def _hifens(t):
    """Junta palavras partidas no fim da linha só quando a forma sem hífen aparece no texto (evita estragar 'bem-estar')."""
    vocab = set(re.findall(r'[A-Za-zÀ-ú]+', t.lower()))
    def junta(m):
        w = (m.group(1) + m.group(2)).lower()
        return m.group(1) + m.group(2) if w in vocab else m.group(1) + '-' + m.group(2)
    return re.sub(r'([A-Za-zÀ-ú]+)-\n\s*([a-zà-ú]+)', junta, t)

def artigos(trecho):
    t = _hifens(trecho)
    t = TITULOS.sub('\n§§TIT\n', t)
    t = re.sub(r'\.{5,}|…{2,}', ' (...) ', t)
    t = re.sub(r'(\(\.\.\.\)\s*)+', '(...) ', t)
    t = re.sub(r'([“"]?Art\.)\s*\n\s*(\d)', r'\1 \2', t)
    t = re.sub(r'Art\.(\d)', r'Art. \1', t)
    # marca o começo de cada artigo (no começo da linha, com ou sem aspas)
    t = re.sub(r'(?m)^\s*([“"]?Art\. ?\d+(?:-[A-Z])?)', r'\n§§ART\1', t)
    blocos = t.split('\n§§ART')
    out, vistos = [], collections.Counter()
    for b in blocos[1:]:
        b = b.split('§§TIT')[0]
        b = re.sub(r'\s*\n\s*', ' ', b).strip()
        b = re.sub(r'[ \t]+', ' ', b)
        m = re.match(r'[“"]?Art\. ?(\d+(?:-[A-Z])?)', b)
        if not m:
            continue
        lab = 'Art. ' + m.group(1)
        vistos[lab] += 1
        if vistos[lab] > 1:
            lab = f'{lab} ({vistos[lab]}ª ocorrência)'
        corpo = DISP1.sub('\n', b)
        corpo = DISP2.sub('\n', corpo)
        corpo = DISP3.sub('\n', corpo)
        corpo = re.sub(r'\(\.\.\.\)\s(?=[IVXLC]+ ?[-–] )', '(...)\n', corpo)
        corpo = re.sub(r':\s*\(\.\.\.\)\s*', ':\n(...)\n', corpo)
        out.append({'label': lab, 'text': corpo.strip()})
    if len(out) < 1:
        raise ValueError('Não foi possível separar os artigos do documento.')
    return out

# ---------------------------------------------------------------- 4. comparação
PALAVRA = re.compile(r'\n|[\wÀ-ú§º°ª\-]+|[^\s\w]')
def palavras(s):
    return PALAVRA.findall(s)

def sim(a, b):
    A, B = palavras(a), palavras(b)
    if not A or not B:
        return 1.0 if A == B else 0.0
    return difflib.SequenceMatcher(None, A, B, autojunk=False).ratio()

def _sim_art(a, b):
    """Semelhança entre artigos: a razão comum ou, quando um artigo cresceu muito, quanto do menor está no maior."""
    A, B = palavras(a), palavras(b)
    if not A or not B:
        return 0.0
    sm = difflib.SequenceMatcher(None, A, B, autojunk=False)
    cobre = sum(m.size for m in sm.get_matching_blocks()) / min(len(A), len(B))
    return max(sm.ratio(), 0.85 * cobre if cobre >= 0.6 else 0)

def _qsim(a, b):
    """semelhança rápida (para filtrar candidatos antes da conta exata)"""
    A, B = set(w.lower() for w in palavras(a) if len(w) > 3), set(w.lower() for w in palavras(b) if len(w) > 3)
    if not A or not B:
        return 0.0
    return len(A & B) / max(len(A), len(B))

def alinhar_artigos(oa, ob):
    cand = []
    for i, o in enumerate(oa):
        for j, s in enumerate(ob):
            q = _qsim(o['text'], s['text'])
            same = o['label'].split(' (')[0] == s['label'].split(' (')[0]
            if q < 0.2 and not same:
                continue
            r = _sim_art(o['text'], s['text']) if q >= 0.2 else q
            cand.append((r + (0.15 if same else 0), r, i, j))
    cand.sort(reverse=True)
    ma, mb = {}, {}
    for sc, r, i, j in cand:
        if i in ma or j in mb or r < 0.35:
            continue
        ma[i] = j; mb[j] = i
    pares = []
    for j, s in enumerate(ob):
        pares.append((mb.get(j), j))
    for i in range(len(oa)):
        if i not in ma:
            # suprimido: entra depois do par anterior mais próximo
            pos = len(pares)
            for k, (pi, pj) in enumerate(pares):
                if pi is not None and pi > i:
                    pos = k; break
            pares.insert(pos, (i, None))
    return pares

ROTULO = re.compile(r'^([“"]?Art\. ?\d+(?:-[A-Z])?[º°o]?\.?|§ ?\d+[º°o]?\.?|Parágrafo único\.|[IVXLC]+ ?[-–]|[a-z]\)|\d+(?:\.|\)| ?[-–])|\(\.\.\.\))\s*')

def dispositivos(text):
    out = []
    for ln in text.split('\n'):
        ln = ln.strip()
        if not ln:
            continue
        m = ROTULO.match(ln)
        lab, body = (m.group(1), ln[m.end():]) if m else ('', ln)
        out.append({'label': lab.lstrip('“"'), 'body': body})
    return out

def _lis(seq):
    n = len(seq)
    if not n:
        return set()
    best, prev = [1] * n, [-1] * n
    for i in range(n):
        for j in range(i):
            if seq[j] < seq[i] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    k = max(range(n), key=lambda i: best[i]); keep = set()
    while k != -1:
        keep.add(k); k = prev[k]
    return keep

def norm_rotulo(l):
    return re.sub(r'\s+', '', l.replace('–', '-')).replace('º', '').replace('°', '').rstrip('.')

def alinhar_dispositivos(ua, ub):
    cand = []
    for i, a in enumerate(ua):
        for j, b in enumerate(ub):
            if a['label'].startswith('(') or b['label'].startswith('('):
                s = 1.0 if a['label'] == b['label'] else 0.0
            else:
                q = _qsim(a['body'], b['body'])
                s = sim(a['body'], b['body']) if q >= 0.15 or (len(a['body']) < 40 and len(b['body']) < 40) else q
            pos = 1 - abs(i / max(len(ua), 1) - j / max(len(ub), 1))
            cand.append((s + 0.05 * pos, s, i, j))
    cand.sort(reverse=True)
    ma, mb = {}, {}
    for sc, s, i, j in cand:
        if i in ma or j in mb or s < 0.45:
            continue
        ma[i] = j; mb[j] = i
    # divisão: um dispositivo antigo virou vários novos em sequência
    divs = {}
    for i in range(len(ua)):
        if i in ma:
            continue
        best = None
        for j0 in range(len(ub)):
            if j0 in mb:
                continue
            for n in (2, 3, 4):
                js = list(range(j0, j0 + n))
                if js[-1] >= len(ub) or any(j in mb for j in js):
                    break
                cat = ' '.join(ub[j]['label'] + ' ' + ub[j]['body'] for j in js)
                s = sim(ua[i]['body'], cat)
                if s >= 0.6 and (best is None or s > best[0]):
                    best = (s, js)
        if best:
            js = best[1]
            aw = {w.lower() for w in palavras(ua[i]['body']) if len(w) > 3}
            def contido(j):
                uw = [w.lower() for w in palavras(ub[j]['body']) if len(w) > 3]
                return uw and sum(w in aw for w in uw) / len(uw) >= 0.6
            while js[0] - 1 >= 0 and js[0] - 1 not in mb and contido(js[0] - 1):
                js = [js[0] - 1] + js
            while js[-1] + 1 < len(ub) and js[-1] + 1 not in mb and contido(js[-1] + 1):
                js = js + [js[-1] + 1]
            ma[i] = js[0]
            for j in js:
                mb[j] = i
            divs[js[0]] = js
    internos = {j for v in divs.values() for j in v[1:]}
    ordem = [j for j in range(len(ub)) if j in mb and j not in internos]
    keep = _lis([mb[j] for j in ordem])
    movidos = {ordem[p] for p in range(len(ordem)) if p not in keep}
    linhas, pend = [], sorted(i for i in range(len(ua)) if i not in ma)
    def solta(ate):
        nonlocal pend
        resto = []
        for i in pend:
            if i < ate: linhas.append(('del', i, None))
            else: resto.append(i)
        pend = resto
    for j in range(len(ub)):
        if j in internos:
            continue
        if j in mb:
            i = mb[j]
            if j not in movidos:
                solta(i)
            if j in divs:
                linhas.append(('div-mov' if j in movidos else 'div', i, divs[j]))
            else:
                linhas.append(('mov' if j in movidos else 'par', i, j))
        else:
            linhas.append(('ins', None, j))
    solta(10 ** 9)
    return linhas

def ops_palavras(a, b):
    A, B = palavras(a), palavras(b)
    sm = difflib.SequenceMatcher(None, A, B, autojunk=False)
    return [[tag, A[i1:i2], B[j1:j2]] for tag, i1, i2, j1, j2 in sm.get_opcodes()]

# ---------------------------------------------------------------- renderização (HTML escapado)
SEM_ESPACO_ANTES = set('.,;:)”!?/$')
SEM_ESPACO_DEPOIS = set('(“/')
PONTUACAO = {';', ',', '.', ':', 'e', 'ou', '”', '“', '(', ')', 'NR', '"'}

def render(seq):
    """seq: [(token, tipo)] com tipo em eq/del/ins/ren → HTML"""
    out, cur, buf = [], None, []
    prev = prev2 = None
    def flush():
        if not buf:
            return
        t = ''.join(buf)
        out.append(t if cur == 'eq' else f'<span class="{cur}">{t}</span>')
    for tok, kind in seq:
        if tok == '\n':
            sp, t = '', '<br>'
        else:
            sp = ' '
            if prev is None or prev == '\n' or tok in SEM_ESPACO_ANTES or prev in SEM_ESPACO_DEPOIS:
                sp = ''
            if prev in ('.', ',') and prev2 and prev2[-1:].isdigit() and tok[:1].isdigit():
                sp = ''
            t = html.escape(tok)
        if kind != cur:
            flush(); buf = []
            if sp:
                out.append(sp); sp = ''
            cur = kind
        buf.append(sp + t)
        prev2, prev = prev, tok
    flush()
    return ''.join(out)

def _assinatura(ops, k):
    tag, a, b = ops[k]
    esq = ops[k - 1][1][-1:] if k > 0 and ops[k - 1][0] == 'equal' else []
    dir_ = ops[k + 1][1][:1] if k + 1 < len(ops) and ops[k + 1][0] == 'equal' else []
    return (tuple(a), tuple(b), tuple(esq), tuple(dir_))

def comparar(texto_a, texto_b):
    """Recebe os textos articulados (saída de articulado) e devolve o quadro e as estatísticas."""
    oa, ob = artigos(texto_a), artigos(texto_b)
    pares = alinhar_artigos(oa, ob)
    # 1ª passada: diferenças de todos os dispositivos emparelhados, para achar trocas de nome repetidas
    base = []
    for i, j in pares:
        ua = dispositivos(oa[i]['text']) if i is not None else []
        ub = dispositivos(ob[j]['text']) if j is not None else []
        linhas = alinhar_dispositivos(ua, ub) if ua and ub else [('del', x, None) for x in range(len(ua))] + [('ins', None, x) for x in range(len(ub))]
        base.append((i, j, ua, ub, linhas))
    cont = collections.Counter()
    for i, j, ua, ub, linhas in base:
        for kind, x, y in linhas:
            if kind in ('par', 'mov'):
                ops = ops_palavras(ua[x]['body'], ub[y]['body'])
                for k, op in enumerate(ops):
                    if op[0] != 'equal':
                        cont[_assinatura(ops, k)] += 1
    renomes = {s for s, c in cont.items() if c >= 4 and max(len(s[0]), len(s[1])) >= 3
               and not all(w in PONTUACAO for w in s[0] + s[1])}
    exemplos = collections.Counter()
    itens = []
    for i, j, ua, ub, linhas in base:
        rows, st, trechos = [], collections.Counter(), []
        for kind, x, y in linhas:
            tags = []
            if kind.startswith('div'):
                a = ua[x]; js = y
                catb = '\n'.join((ub[z]['label'] + ' ' + ub[z]['body']).strip() for z in js)
                ops = ops_palavras(a['body'], catb)
                A, B = _seqs(ops, set())
                ca, cb = _rot(a['label']) + render(A), render(B)
                k = 'movido' if kind == 'div-mov' else 'alterado'
                if kind == 'div-mov': tags.append('↕ mudou de posição')
                tags.append(f'dividido em {len(js)} dispositivos · antes {html.escape(a["label"])}')
                trechos.append(('alterado', a['label'] + ' ' + a['body'], catb))
            elif kind in ('par', 'mov'):
                a, b = ua[x], ub[y]
                ops = ops_palavras(a['body'], b['body'])
                ren = _renomes(ops, renomes, cont)
                for fa, fb in _frases(ops, ren):
                    exemplos[(fa, fb)] += 1
                difs = [w for k, (t, aa, bb) in enumerate(ops) if t != 'equal' and k not in ren for w in aa + bb]
                mudou = bool(difs) and not all(w in PONTUACAO for w in difs)
                if difs and not mudou: tags.append('só pontuação ou conectivo')
                if ren and not mudou: tags.append('só troca de nome')
                A, B = _seqs(ops, ren)
                relab = norm_rotulo(a['label']) != norm_rotulo(b['label'])
                ca, cb = _rot(a['label']) + render(A), _rot(b['label']) + render(B)
                if kind == 'mov':
                    k = 'movido'; tags.insert(0, '↕ mudou de posição' + (f' · antes {html.escape(a["label"])}' if relab else ''))
                    if mudou: tags.append('texto alterado')
                elif mudou:
                    k = 'alterado'
                    if relab: tags.append(f'renumerado · antes {html.escape(a["label"])}')
                elif relab:
                    k = 'renum'; tags.append(f'só renumerado · antes {html.escape(a["label"])}')
                else:
                    k = 'igual'
                if mudou:
                    trechos.append(('alterado', a['label'] + ' ' + a['body'], b['label'] + ' ' + b['body']))
            elif kind == 'ins':
                b = ub[y]; k = 'novo'; ca = ''
                cb = _rot(b['label']) + render([(t, 'ins') for t in palavras(b['body'])]); tags.append('novo')
                trechos.append(('novo', '', b['label'] + ' ' + b['body']))
            else:
                a = ua[x]; k = 'suprimido'; cb = ''
                ca = _rot(a['label']) + render([(t, 'del') for t in palavras(a['body'])]); tags.append('suprimido')
                trechos.append(('suprimido', a['label'] + ' ' + a['body'], ''))
            st[k] += 1
            tg = ''.join(f'<span class="ut">{t}</span>' for t in tags)
            rows.append(f'<div class="row k-{k}"><div class="cell" data-v="A">{ca or "<span class=empty>—</span>"}</div>'
                        f'<div class="cell" data-v="B">{tg}{cb or "<span class=empty>—</span>"}</div></div>')
        la = oa[i]['label'] if i is not None else None
        lb = ob[j]['label'] if j is not None else None
        if i is None: cls = 'novo'
        elif j is None: cls = 'suprimido'
        elif st['alterado'] or st['novo'] or st['suprimido'] or (st['movido'] and trechos): cls = 'alterado'
        elif st['movido'] or st['renum']: cls = 'reorganizado'
        else: cls = 'igual'
        itens.append({'a': la, 'b': lb, 'cls': cls, 'rows': ''.join(rows), 'st': dict(st), 'trechos': trechos,
                      'tamanho': len((ob[j]['text'] if j is not None else oa[i]['text']))})
    renomeacoes = [{'de': a, 'para': b, 'vezes': c} for (a, b), c in exemplos.most_common(12) if max(len(a), len(b)) > 8]
    return {'itens': itens, 'renomeacoes': renomeacoes, 'artigosA': len(oa), 'artigosB': len(ob)}

def _renomes(ops, renomes, cont):
    """Trocas de nome repetidas: a troca longa e os pedaços curtos colados a ela que também se repetem."""
    ren = {k for k, op in enumerate(ops) if op[0] != 'equal' and _assinatura(ops, k) in renomes}
    mudou = True
    while mudou:
        mudou = False
        for k, op in enumerate(ops):
            if k in ren or op[0] == 'equal' or cont[_assinatura(ops, k)] < 4:
                continue
            for d in (-2, 2):
                m = k + d
                if 0 <= m < len(ops) and m in ren and ops[k + d // 2][0] == 'equal' and len(ops[k + d // 2][1]) <= 3:
                    ren.add(k); mudou = True; break
    return ren

def _frases(ops, ren):
    """Reconstrói a expressão inteira de cada troca de nome (pedaços trocados mais as palavras iguais entre eles e uma de cada lado)."""
    out, k = [], 0
    while k < len(ops):
        if k not in ren:
            k += 1; continue
        ini = fim = k
        while fim + 2 < len(ops) and (fim + 2) in ren and ops[fim + 1][0] == 'equal' and len(ops[fim + 1][1]) <= 3:
            fim += 2
        esq = ops[ini - 1][1][-1:] if ini > 0 and ops[ini - 1][0] == 'equal' else []
        dir_ = ops[fim + 1][1][:1] if fim + 1 < len(ops) and ops[fim + 1][0] == 'equal' else []
        A, B = list(esq), list(esq)
        for m in range(ini, fim + 1):
            if ops[m][0] == 'equal':
                A += ops[m][1]; B += ops[m][2]
            else:
                A += ops[m][1]; B += ops[m][2]
        A += dir_; B += dir_
        txt = lambda t: re.sub(r' ([,.;:)])', r'\1', ' '.join(t))
        out.append((txt(A), txt(B)))
        k = fim + 1
    return out

def _rot(l):
    return f'<b class="lb">{html.escape(l)}</b> ' if l else ''

def _seqs(ops, ren):
    A, B = [], []
    for k, (tag, a, b) in enumerate(ops):
        if tag == 'equal':
            A += [(t, 'eq') for t in a]; B += [(t, 'eq') for t in b]
        elif k in ren:
            A += [(t, 'ren') for t in a]; B += [(t, 'ren') for t in b]
        else:
            A += [(t, 'del') for t in a]; B += [(t, 'ins') for t in b]
    return A, B
