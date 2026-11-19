"""Enquadramento dos parlamentares em bancadas temáticas (agronegócio, pauta religiosa, segurança e armas, mídia,
mineração, setor financeiro, saúde privada, educação privada, bets e plataformas digitais).

Sem IA. Para cada parlamentar em exercício e cada bancada, soma sinais de duas dimensões:
- vínculo (V): empresas do próprio parlamentar no setor, bens declarados ao TSE, ocupação declarada e nome de urna;
- atuação (A): projetos e votos classificados nas pautas da bancada (pautas.js), projetos e relatorias sobre o tema,
  frentes parlamentares e emendas a entidades do setor.
O enquadramento sai das regras de bancadas-regras.json. A equipe confere as dúvidas em revisao-bancadas.html.

O resultado inclui vínculos de familiares e terceiros (indícios), por isso vai só para o bucket privado do R2
(bancadas/bancadas.json), lido pela página de triagem no Worker da Cloudflare (cloudflare/triagem), protegida pelo Access.
Nada disso é gravado no repositório público.

Fontes: dados/ do site; ramo analises-saida-plp299_tudo (empresas, bens e dados do TSE de cada parlamentar);
ocupação declarada nas candidaturas de 2018, 2022 e 2026 (cópia do TSE no Cloudflare R2, se houver acesso);
frentes parlamentares pela API da Câmara."""
import csv, glob, io, json, os, re, subprocess, sys, time, unicodedata, zipfile, collections
import requests

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def P(*a): return os.path.join(RAIZ, *a)
UA = {'user-agent': 'exterminadores-do-futuro (observatório; contato@exterminadores.com.br)'}
T0 = time.time()
def log(*a): print(f'[{time.time()-T0:.0f}s]', *a, flush=True)
def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9 ]', ' ', s)).strip()
def lj(p, padrao=None):
    try: return json.load(open(p))
    except Exception: return padrao

REG = lj(P('bancadas-regras.json'))
PES, LIM = REG['pesos'], REG['limites']
BAN = REG['bancadas']
for b in BAN:
    for campo in ('bens', 'ocupacao', 'urna', 'termos', 'frentes', 'favorecidos', 'comissoes'):
        b['_' + campo] = [re.compile(x) for x in b.get(campo, [])]
def casa(rx, texto): return next((r.pattern for r in rx if r.search(texto)), None)

# ---------------------------------------------------------------- parlamentares
IND = lj(P('dados', 'indice.json'))['p']
EX = {k: p for k, p in IND.items() if p.get('ex')}
log('em exercício', len(EX))

subprocess.run('git fetch -q --depth 1 origin analises-saida-plp299_tudo', shell=True, cwd=RAIZ)
def doramo(n):
    r = subprocess.run(f'git show FETCH_HEAD:{n}', shell=True, cwd=RAIZ, capture_output=True)
    return json.loads(r.stdout) if r.returncode == 0 else None
TSE = {}
for arq, chave, pre in (('senadores_tse.json', 'senadores', 'S'), ('deputados_tse.json', 'deputados', 'C')):
    for c, s in ((doramo(arq) or {}).get(chave) or {}).items(): TSE[pre + c] = s
EMP = doramo('parl.json')
if not EMP:
    # parl.json sai da análise local do PLP 299 (plp299_analise.py) sobre os arquivos do ramo
    pasta = '/tmp/plp299'; os.makedirs(pasta, exist_ok=True)
    subprocess.run(f'git archive FETCH_HEAD | tar -x -C {pasta}', shell=True, cwd=RAIZ)
    subprocess.run([sys.executable, P('robo', 'analises', 'plp299_analise.py'), pasta], cwd=RAIZ, capture_output=True)
    EMP = lj(os.path.join(pasta, 'parl.json'), {})
    if not EMP and os.path.exists(P('..', 'out', 'parl.json')): EMP = lj(P('..', 'out', 'parl.json'), {})
BENS = collections.defaultdict(list)
for arq, pre in (('bens.json', 'S'), ('bens_deputados.json', 'C')):
    for x in doramo(arq) or []: BENS[pre + str(x['codigo'])].append(x)
log('dados do TSE', len(TSE), 'empresas', len(EMP), 'bens', len(BENS))

# Ocupação declarada nas candidaturas (pelo CPF), na cópia do TSE no R2
OCUP = collections.defaultdict(set)
URNA = collections.defaultdict(set)
for k, s in TSE.items():
    for t in s.get('tse', []):
        if t.get('urna'): URNA[k].add(norm(t['urna']))
        if t.get('ocup'): OCUP[k].add(norm(t['ocup']))
S3 = None
if os.environ.get('R2_ACCOUNT_ID'):
    import boto3
    S3 = boto3.client('s3', endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID'].strip()}.r2.cloudflarestorage.com",
                      aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'].strip(), aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'].strip(), region_name='auto')
BUCKET = os.environ.get('R2_BUCKET', 'exterminadores-dados')
CPF = {}
for k, s in TSE.items():
    for t in s.get('tse', []) + [s]:
        c = re.sub(r'\D', '', str(t.get('cpf') or ''))
        if len(c) == 11: CPF[c] = k
if S3:
    try:
        s3 = S3
        for ano in (2018, 2022, 2026):
            try:
                corpo = s3.get_object(Bucket=os.environ.get('R2_BUCKET', 'exterminadores-dados'), Key=f'tse/consulta_cand_{ano}.zip')['Body'].read()
            except Exception as e:
                log('sem consulta_cand', ano, e); continue
            with zipfile.ZipFile(io.BytesIO(corpo)) as z:
                nomes = [n for n in z.namelist() if n.endswith('.csv')]
                br = [n for n in nomes if 'BRASIL' in n.upper()]
                for n in (br or nomes):
                    with z.open(n) as f:
                        for r in csv.DictReader(io.TextIOWrapper(f, encoding='latin-1', errors='ignore'), delimiter=';'):
                            k = CPF.get(re.sub(r'\D', '', r.get('NR_CPF_CANDIDATO') or ''))
                            if not k: continue
                            if r.get('DS_OCUPACAO'): OCUP[k].add(norm(r['DS_OCUPACAO']))
                            if r.get('NM_URNA_CANDIDATO'): URNA[k].add(norm(r['NM_URNA_CANDIDATO']))
            log('ocupações lidas', ano)
    except Exception as e:
        log('R2 indisponível', e)
POLITICA = re.compile(r'SENADOR|DEPUTADO|VEREADOR|PREFEITO|GOVERNADOR|MINISTRO DE ESTADO|SECRETARIO|SERVIDOR PUBLICO|OUTROS|APOSENTADO|EMPRESARIO|ADVOGADO|ADMINISTRADOR')

# ---------------------------------------------------------------- classificação das proposições e votações
CL = (lj(P('dados', 'classificacoes.json'), {}) or {}).get('c', {})
CORR = (lj(P('correcoes.json'), {}) or {}).get('correcoes', {})
def classe(chave):
    x = dict(CL.get(chave) or {})
    c = CORR.get(chave)
    if isinstance(c, dict):
        if 's' in c: x['s'] = c['s']
        if isinstance(c.get('p'), list): x['p'] = c['p']
    return x

PROPS = []
for f in sorted(glob.glob(P('dados', 'proposicoes-*.json'))):
    if re.search(r'proposicoes-\d{4}\.json$', f): PROPS += lj(f, {}).get('itens', [])
VOTS = []
for f in sorted(glob.glob(P('dados', 'votacoes-*.json'))):
    if re.search(r'votacoes-\d{4}\.json$', f): VOTS += lj(f, {}).get('itens', [])
RELS = (lj(P('dados', 'relatorias.json'), {}) or {}).get('itens', []) + (lj(P('dados', 'relatorias-camara.json'), {}) or {}).get('itens', [])
EMD = (lj(P('dados', 'emendas.json'), {}) or {}).get('parl', {})
log('proposições', len(PROPS), 'votações', len(VOTS), 'relatorias', len(RELS), 'emendas', len(EMD))

BC = {}
if S3:
    try: BC = json.loads(S3.get_object(Bucket=BUCKET, Key='bancadas/decisoes.json')['Body'].read())
    except Exception as e: log('sem decisões da equipe no R2', e)
CHAVE = BC.get('votacoes', {})      # bancada -> {id da votação: voto esperado 'S' ou 'N'}

def da_bancada(b, pautas, texto):
    """A proposição ou votação é da bancada: pauta da bancada (com termos, se exigido) ou, sem pauta, só os termos."""
    p = [x for x in pautas if x in b['pautas']]
    if not p: return False
    sem_termo = [x for x in p if x not in b.get('termos_pauta', [])]
    return bool(sem_termo) or bool(casa(b['_termos'], texto))

# ---------------------------------------------------------------- frentes parlamentares (Câmara)
FRENTES = collections.defaultdict(list)   # parlamentar -> [(id, título)]
def frentes():
    api = 'https://dadosabertos.camara.leg.br/api/v2'
    lista, pag = [], 1
    while True:
        r = requests.get(f'{api}/frentes', params={'idLegislatura': 57, 'itens': 100, 'pagina': pag}, headers={**UA, 'accept': 'application/json'}, timeout=60)
        r.raise_for_status(); d = r.json().get('dados', [])
        lista += d
        if len(d) < 100: break
        pag += 1
    log('frentes', len(lista))
    alvo = [f for f in lista if any(casa(b['_frentes'], norm(f.get('titulo'))) for b in BAN)]
    for f in alvo:
        for t in range(3):
            try:
                r = requests.get(f"{api}/frentes/{f['id']}/membros", headers={**UA, 'accept': 'application/json'}, timeout=60)
                r.raise_for_status()
                for m in r.json().get('dados', []):
                    FRENTES['C' + str(m.get('id'))].append((f['id'], f.get('titulo') or ''))
                break
            except Exception as e:
                time.sleep(3)
        time.sleep(0.2)
    log('frentes de interesse', len(alvo), 'deputados com alguma', len(FRENTES))
try: frentes()
except Exception as e: log('frentes indisponíveis', e)

# ---------------------------------------------------------------- comissões (titulares e presidências desde 2023)
COMISSOES = collections.defaultdict(list)   # parlamentar -> [(nome do órgão, cargo)]
def comissoes():
    api = 'https://dadosabertos.camara.leg.br/api/v2'
    for k in [k for k in EX if k[0] == 'C']:
        for t in range(3):
            try:
                r = requests.get(f'{api}/deputados/{k[1:]}/orgaos', params={'dataInicio': '2023-02-01', 'itens': 100}, headers={**UA, 'accept': 'application/json'}, timeout=60)
                r.raise_for_status()
                for o in r.json().get('dados', []):
                    COMISSOES[k].append((o.get('nomeOrgao') or o.get('nomePublicacao') or '', o.get('titulo') or ''))
                break
            except Exception: time.sleep(3)
        time.sleep(0.1)
    for k in [k for k in EX if k[0] == 'S']:
        try:
            r = requests.get(f'https://legis.senado.leg.br/dadosabertos/senador/{k[1:]}/comissoes.json', headers={**UA, 'accept': 'application/json'}, timeout=60)
            r.raise_for_status()
            ms = (((r.json().get('MembroComissaoParlamentar') or {}).get('Parlamentar') or {}).get('MembroComissoes') or {}).get('Comissao') or []
            for m in (ms if isinstance(ms, list) else [ms]):
                if (m.get('DataInicio') or '') < '2023-02-01' and (m.get('DataFim') or '9999') < '2023-02-01': continue
                ic = m.get('IdentificacaoComissao') or {}
                COMISSOES[k].append((ic.get('NomeComissao') or '', m.get('DescricaoParticipacao') or ''))
        except Exception: pass
        time.sleep(0.1)
    log('comissões lidas para', len(COMISSOES), 'parlamentares')
try: comissoes()
except Exception as e: log('comissões indisponíveis', e)

# ---------------------------------------------------------------- sinais
def nova(): return {'V': 0, 'A': 0, 'E': 0, 'contra': 0, 'ev': []}
GENERICOS = {'Votos', 'Emendas', 'Frentes parlamentares'}   # sinais de atuação que acompanham a ideologia ou são assinados em massa e não bastam sozinhos
S = {k: {b['id']: nova() for b in BAN} for k in EX}
def ev(k, b, dim, pts, tipo, texto, url='', privado=0):
    s = S[k][b]
    if dim == 'contra': s['contra'] += pts
    else:
        s[dim] += pts
        if dim == 'A' and tipo not in GENERICOS: s['E'] += pts
    s['ev'].append([dim, round(pts, 2), tipo, texto, url, privado])

for k in EX:
    emp = (EMP.get(k) or {}).get('emp', [])
    bens = BENS.get(k, [])
    ocup = {o for o in OCUP.get(k, set()) if not POLITICA.search(o)}
    for b in BAN:
        bid = b['id']
        # empresas do próprio parlamentar
        pts = 0
        for e in emp:
            cn = str(e.get('cnae') or '').zfill(7)
            if any(cn.startswith(p) for p in b['cnae']) and pts < PES['empresa_max']:
                ev(k, bid, 'V', PES['empresa'], 'Empresa', f"{e.get('razao')} ({e.get('desc')})", f"https://casadosdados.com.br/solucao/cnpj?q={e.get('b')}")
                pts += PES['empresa']
        # bens declarados ao TSE
        pts = 0
        for x in bens:
            t = norm(f"{x.get('tipo')} {x.get('desc')}")
            if casa(b['_bens'], t) and pts < PES['bem_max']:
                ev(k, bid, 'V', PES['bem'], f"Bem declarado ao TSE ({x.get('ano')})", f"{x.get('tipo')}: {(x.get('desc') or '').strip()[:140]} (R$ {x.get('valor')})", '')
                pts += PES['bem']
        # ocupação e nome de urna
        o = next((o for o in ocup if casa(b['_ocupacao'], o)), None)
        if o: ev(k, bid, 'V', PES['ocupacao'], 'Ocupação declarada ao TSE', o.capitalize(), '')
        u = next((u for u in URNA.get(k, set()) if casa(b['_urna'], u)), None)
        if u: ev(k, bid, 'V', PES['urna'], 'Nome de urna', u.title(), '')

# Mídia: sociedade direta do próprio parlamentar em emissoras e jornais do levantamento de mídia (outorgas do MCom e atividade principal
# ou secundária de rádio e TV), que pega emissoras registradas na Receita com outra atividade principal. Só o próprio parlamentar.
def midia_direta():
    import gzip
    r = subprocess.run('git fetch -q --depth 1 origin analises-saida-midia3', shell=True, cwd=RAIZ)
    def ler(n):
        x = subprocess.run(f'git show FETCH_HEAD:{n}', shell=True, cwd=RAIZ, capture_output=True)
        if x.returncode: return None
        return json.loads(gzip.decompress(x.stdout) if n.endswith('.gz') else x.stdout)
    qsa, uni, parl = ler('qsa.json.gz'), ler('universo.json.gz'), ler('parlamentares.json')
    if not (qsa and uni and parl): log('levantamento de mídia indisponível'); return
    chaves = {(norm(p['nomeCompleto']), c[3:9]): k for k, p in parl.items() if p.get('nomeCompleto') for c in p.get('cpfs', [])}
    RTV = {'6010100', '6021700', '6022501', '6022502'}; IMPR = {'5812301', '5812302', '5822101', '5822102'}
    QUAL = {'05': 'administrador', '10': 'diretor', '16': 'presidente', '22': 'sócio', '49': 'sócio-administrador', '65': 'titular'}
    n = 0
    for b, ss in qsa.items():
        u = uni.get(b) or {}
        cn = set(u.get('cnaes', [])) | {e.get('cnae') for e in u.get('estab', [])}
        if not (u.get('mcom') or cn & RTV or {e.get('cnae') for e in u.get('estab', [])} & IMPR): continue
        if not any(e.get('sit') == '02' for e in u.get('estab', [])): continue
        for x in ss:
            if x.get('tipo') != '2' or x.get('holding'): continue
            k = chaves.get((norm(x['nome']), str(x.get('doc', '')).strip('*')))
            if k in EX and not any(e[2] == 'Empresa' and (u.get('razao') or '') in e[3] for e in S[k]['midia']['ev']):
                ev(k, 'midia', 'V', PES['empresa'], 'Empresa', f"{u.get('razao')} ({'outorga de radiodifusão' if u.get('mcom') else 'rádio, TV ou jornal'}; {QUAL.get(x.get('qualif'), 'sócio')})",
                   f"https://casadosdados.com.br/solucao/cnpj?q={b}"); n += 1
    log('mídia: sociedades diretas acrescentadas', n)
try: midia_direta()
except Exception as e: log('mídia direta falhou', e)

# Mídia: vínculos indiretos do levantamento de mídia (familiares por sobrenome, sócios em comum, holdings, procuração,
# saídas da sociedade, pagamentos a emissora ligada e funcionários de gabinete homônimos). São indícios: vão marcados como privados.
def midia_indireta():
    pm, pp = '/tmp/midia', '/tmp/plp299'
    for pasta, ramo in ((pm, 'analises-saida-midia3'), (pm, 'analises-saida-midia_senado'), (pp, 'analises-saida-plp299_tudo')):
        os.makedirs(pasta, exist_ok=True)
        subprocess.run(f'git fetch -q --depth 1 origin {ramo} && git archive FETCH_HEAD | tar -x -C {pasta}', shell=True, cwd=RAIZ)
    if not os.path.exists(f'{pp}/parl.json'):
        subprocess.run([sys.executable, P('robo', 'analises', 'plp299_analise.py'), pp], cwd=RAIZ, capture_output=True)
    r = subprocess.run([sys.executable, P('robo', 'analises', 'midia_analise.py'), pm, pp], cwd=RAIZ, capture_output=True, text=True)
    v = lj(f'{pm}/vinculos.json')
    if not v: log('análise de mídia falhou', r.stderr[-500:]); return
    PTS = {'forte': 3, 'sobrenome (2+)': 2, 'sobrenome raro': 1, 'indício': 1}
    n = 0
    for k, x in v.items():
        if k not in EX: continue
        vist = set()
        for y in x['vinculos']:
            if y['forca'] == 'direto' or y['forca'] not in PTS: continue
            if y['forca'] == 'indício' and not y['tipo'].startswith('funcion'): continue
            chave = (y['tipo'], y.get('b'))
            if chave in vist: continue
            vist.add(chave)
            pts = PTS[y['forca']] if y.get('ativa') else min(1, PTS[y['forca']])
            ev(k, 'midia', 'V', pts, y['tipo'].capitalize(), f"{y.get('razao')} [{y.get('midia') or ''}{'' if y.get('ativa') else ', inativa'}]: {y.get('det')}"[:300],
               f"https://casadosdados.com.br/solucao/cnpj?q={y['b']}" if y.get('b') else '', 1)
            n += 1
    log('mídia: vínculos indiretos', n)
try: midia_indireta()
except Exception as e: log('mídia indireta falhou', e)

# autoria
URLP = lambda it: (f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={it['i']}" if (it.get('k') or ['C'])[0] == 'C' and it.get('i')
                   else (f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{it['i']}" if it.get('i') else ''))
alin = collections.defaultdict(list); tema = collections.defaultdict(list); contra_aut = collections.defaultdict(list)
for it in PROPS:
    autores = [a for a in (it.get('a') or [])[:1] if a in EX]   # só o primeiro autor: coautorias coletivas inflam a contagem
    if not autores: continue
    x = classe(it['c']); texto = norm(it.get('e'))
    for b in BAN:
        doban = da_bancada(b, x.get('p') or [], texto)
        for a in autores:
            if doban and x.get('s') == 'avanca': alin[(a, b['id'])].append(it)
            elif doban and x.get('s') == 'barra': contra_aut[(a, b['id'])].append(it)
            elif casa(b['_termos'], texto): tema[(a, b['id'])].append(it)
for (a, bid), its in alin.items():
    for it in its[:PES['autoria_alinhada_max']]:
        ev(a, bid, 'A', PES['autoria_alinhada'], 'Projeto alinhado à pauta', f"{it['c']}: {it.get('e', '')[:160]}", URLP(it))
    if len(its) > PES['autoria_alinhada_max']: S[a][bid]['ev'].append(['A', 0, 'Projeto alinhado à pauta', f"e mais {len(its) - PES['autoria_alinhada_max']}", ''])
for (a, bid), its in tema.items():
    pts = min(PES['autoria_tema_max'], len(its) // PES['autoria_tema_cada'])
    if pts: ev(a, bid, 'A', pts, 'Projetos sobre o tema', f"{len(its)} projetos, como {its[0]['c']}: {its[0].get('e', '')[:120]}", URLP(its[0]))
for (a, bid), its in contra_aut.items():
    ev(a, bid, 'contra', len(its), 'Projeto contra a pauta', f"{len(its)} projeto(s), como {its[0]['c']}: {its[0].get('e', '')[:120]}", URLP(its[0]))

# relatorias
rel = collections.defaultdict(list)
for it in RELS:
    if it.get('r') not in EX: continue
    texto = norm(it.get('e'))
    for b in BAN:
        if casa(b['_termos'], texto): rel[(it['r'], b['id'])].append(it)
for (a, bid), its in rel.items():
    pts = min(PES['relatoria_max'], len(its) // PES['relatoria_cada'])
    if pts: ev(a, bid, 'A', pts, 'Relatorias sobre o tema', f"{len(its)} relatorias, como {its[0]['c']}: {its[0].get('e', '')[:120]}", URLP(its[0]))

# votos nas votações da pauta da bancada
def votos_de(vt):
    for v, ids in (vt.get('v') or {}).items():
        for i in ids: yield vt['k'] + str(i), v
cont = collections.defaultdict(lambda: [0.0, 0.0])
cont_chave = collections.defaultdict(lambda: [0, 0])
CAND = collections.defaultdict(list)
for vt in VOTS:
    x = classe(vt.get('ck') or ''); texto = norm(f"{vt.get('desc')} {vt.get('me')}")
    for b in BAN:
        chave = CHAVE.get(b['id'], {}).get(vt['id'])
        doban = da_bancada(b, x.get('p') or [], texto) and x.get('s') in ('avanca', 'barra') and vt.get('bd') in ('S', 'N')
        if doban or casa(b['_termos'], texto):
            if vt.get('pl') and vt.get('disp'): CAND[b['id']].append(vt)
        if not (doban or chave): continue
        pro = chave or vt['bd']; peso = PES['votacao_chave_peso'] if chave else 1
        for k, v in votos_de(vt):
            if k not in EX or v not in ('S', 'N'): continue
            c = cont[(k, b['id'])]; c[1] += peso
            if v == pro: c[0] += peso
            if chave:
                cc = cont_chave[(k, b['id'])]; cc[1] += 1
                if v == pro: cc[0] += 1
for (k, bid), (a, n) in cont.items():
    if n < PES['votos_minimo']: continue
    sh = a / n
    txt = f"votou com a pauta em {round(100 * sh)}% de {int(n)} votos ponderados"
    if sh >= PES['votos_alto_limite']: ev(k, bid, 'A', PES['votos_alto'], 'Votos', txt)
    elif sh >= PES['votos_medio_limite']: ev(k, bid, 'A', PES['votos_medio'], 'Votos', txt)
    elif sh <= PES['votos_contra_limite']: ev(k, bid, 'contra', 2, 'Votos', txt)
    else: S[k][bid]['ev'].append(['A', 0, 'Votos', txt, ''])

# votações-chave marcadas pela equipe: atuação específica
for (k, bid), (a, n) in cont_chave.items():
    if n < PES['chave_minimo']: continue
    sh = a / n; txt = f"votou com a pauta em {round(100 * sh)}% de {n} votações-chave"
    if sh >= PES['votos_alto_limite']: ev(k, bid, 'A', PES['chave_alto'], 'Votações-chave', txt)
    elif sh <= PES['votos_contra_limite']: ev(k, bid, 'contra', 2, 'Votações-chave', txt)
    else: S[k][bid]['ev'].append(['A', 0, 'Votações-chave', txt, '', 0])

# comissões temáticas
for k, cs in COMISSOES.items():
    if k not in EX: continue
    for b in BAN:
        pts, vist = 0, []
        for nome_o, cargo in cs:
            if not casa(b['_comissoes'], norm(nome_o)) or nome_o in vist: continue
            c = norm(cargo)
            p = PES['comissao_presidencia'] if 'PRESIDENTE' in c else PES['comissao_titular'] if 'TITULAR' in c else 0
            if not p: continue
            vist.append(nome_o); pts += p
        if pts:
            ev(k, b['id'], 'A', min(PES['comissao_max'], pts), 'Comissões', '; '.join(vist)[:200])

# sinais da Receita e do TSE (robo/analises/bancadas_receita.py, no R2)
SR = {}
if S3:
    try: SR = json.loads(S3.get_object(Bucket=BUCKET, Key='bancadas/sinais_receita.json')['Body'].read()).get('sinais', {})
    except Exception as e: log('sem sinais da Receita no R2', e)
BID_ = {b['id']: b for b in BAN}
fmtv = lambda v: f"R$ {v:,.0f}".replace(',', '.')
for k, bs in SR.items():
    if k not in EX: continue
    for bid, xs in bs.items():
        if bid not in S[k]: continue
        vistos = set(); ign = set(BID_[bid].get('sinais_ignorados', []))
        for x in xs:
            if x['t'] in ign: continue
            u = f"https://casadosdados.com.br/solucao/cnpj?q={x['cnpj']}" if x.get('cnpj') else ''
            if x['t'] in ('empresa_secundaria', 'controlada', 'bem_cnpj'):
                if x['cnpj'] in vistos: continue
                vistos.add(x['cnpj'])
            if x['t'] == 'empresa_secundaria': ev(k, bid, 'V', PES['empresa_secundaria'], 'Empresa (atividade secundária)', x['razao'], u)
            elif x['t'] == 'controlada': ev(k, bid, 'V', PES['empresa_controlada'], 'Empresa com participação de empresa do parlamentar', f"{x['razao']} (por meio de {x.get('por')})", u)
            elif x['t'] == 'bem_cnpj': ev(k, bid, 'V', PES['bem_cnpj'] if x.get('ativa') else 1, 'Empresa citada nos bens declarados ao TSE', x['razao'] + ('' if x.get('ativa') else ' (inativa)'), u)
            elif x['t'] == 'doacoes':
                v, sh = x['valor'], x.get('parcela') or 0
                if v < PES['doacao_minima']: continue
                if not (v >= PES['doacao_media_valor'] or sh >= PES['doacao_media_parcela']) and not PES['doacao_baixa']: continue
                pts = PES['doacao_alta'] if (v >= PES['doacao_alta_valor'] or sh >= PES['doacao_alta_parcela']) else PES['doacao_media'] if (v >= PES['doacao_media_valor'] or sh >= PES['doacao_media_parcela']) else PES['doacao_baixa']
                top = '; '.join(f"{d['nome']} ({fmtv(d['valor'])}, sócio de {d['empresa']}, {'/'.join(map(str, d['anos']))})" for d in x['top'][:3])
                ev(k, bid, 'V', pts, 'Doações de campanha de sócios de empresas do setor',
                   f"{fmtv(v)} de {x['n']} doador(es){f', {round(100 * sh)}% das doações de pessoas físicas' if sh else ''}. Maiores: {top}"[:400], '', 1)

# familiares e terceiros nos demais setores (robo/analises/bancadas_familiares.py, no R2): indícios, marcados como privados
FAM = {}
if S3:
    try: FAM = json.loads(S3.get_object(Bucket=BUCKET, Key='bancadas/familiares.json')['Body'].read()).get('vinculos', {})
    except Exception as e: log('sem familiares no R2', e)
PTS_FAM = {'forte': 3, 'sobrenome (2+)': 2, 'sobrenome raro': 1}
nfam = 0
for k, bs in FAM.items():
    if k not in EX: continue
    for bid, xs in bs.items():
        if bid not in S[k]: continue
        vist = set()
        for x in xs:
            chave = (x['tipo'], x['cnpj'], x['det'][:40])
            if chave in vist: continue
            vist.add(chave)
            ev(k, bid, 'V', PTS_FAM.get(x['forca'], 1), x['tipo'], f"{x['razao']} ({x['uf']}): {x['det']}"[:300],
               f"https://casadosdados.com.br/solucao/cnpj?q={x['cnpj']}", 1)
            nfam += 1
log('familiares e terceiros nos demais setores:', nfam)

# frentes
for k, fs in FRENTES.items():
    if k not in EX: continue
    for b in BAN:
        m = [t for i, t in fs if casa(b['_frentes'], norm(t))]
        if m: ev(k, b['id'], 'A', min(PES['frente_max'], PES['frente'] * len(m)), 'Frentes parlamentares', '; '.join(sorted(set(m)))[:300],
                 f"https://www.camara.leg.br/deputados/{k[1:]}")

# emendas
for k, e in EMD.items():
    if k not in EX: continue
    total = e.get('emp') or 0
    for b in BAN:
        pts = 0
        for t in b.get('emendas_temas', []):
            v = (e.get('temas') or {}).get(t, 0)
            if total and v / total >= PES['emenda_tema_parcela']:
                ev(k, b['id'], 'A', PES['emenda_tema'], 'Emendas', f"{round(100 * v / total)}% das emendas para a área ({t})"); pts += 1
        fav = [f for f in e.get('favs', []) if casa(b['_favorecidos'], norm(f[0]))]
        if fav and pts < PES['emenda_max']:
            ev(k, b['id'], 'A', PES['emenda_favorecido'], 'Emendas a entidades do setor', '; '.join(f"{f[0]} (R$ {f[2]:,.0f})".replace(',', '.') for f in fav[:3]))

# ---------------------------------------------------------------- enquadramento
def enquadrar(s, lim):
    # V: vínculo; A: atuação total; E: atuação específica (sem votos e parcela de emendas, que acompanham a ideologia); C: sinais contrários
    V, A, E, C = s['V'], s['A'], s['E'], s['contra']
    if V < lim['vinculo_minimo'] and E < lim['especifica_minima']: return None, None
    if V < lim['vinculo'] and C >= E: return None, None   # atua mais contra a pauta do que a favor: não é da bancada
    LIM = lim
    if V >= LIM['vinculo'] and A >= LIM['atuacao_nucleo']: cat = 'nucleo'
    elif V < LIM['vinculo'] and E >= LIM['especifica_aliado'] and A >= LIM['atuacao_aliado']: cat = 'aliado'
    elif V >= LIM['vinculo']: cat = 'interesse'
    else: cat = 'duvida'
    # Vai para a triagem tudo que não é núcleo nem aliado claro, e quem tem sinais contrários.
    claro = (cat == 'nucleo' and E >= 1) or (cat == 'aliado' and E >= LIM['especifica_aliado_automatico'])
    triar = not claro or C >= 2
    return cat, triar
BID = {b['id']: b for b in BAN}
saida = {}
cont_cat = collections.Counter()
for k, bs in S.items():
    p = EX[k]; reg = {}
    for bid, s in bs.items():
        cat, triar = enquadrar(s, {**LIM, **(BID[bid].get('limites') or {})})
        if not cat: continue
        reg[bid] = {'cat': cat, 't': 1 if triar else 0, 'V': s['V'], 'A': s['A'], 'E': s['E'], 'C': s['contra'], 'ev': s['ev']}
        cont_cat[(bid, cat, triar)] += 1
    if reg: saida[k] = {'n': p.get('n'), 'c': p.get('c'), 's': p.get('s') or p.get('p'), 'uf': p.get('uf'), 'g': p.get('cl'), 'b': reg}

# links para as matérias das votações candidatas: a matéria votada e os projetos citados na ementa ou na descrição
SIGLAS = [('PROJETO DE LEI COMPLEMENTAR', 'PLP'), ('PROJETO DE LEI DE CONVERSAO', 'PLV'), ('PROJETO DE LEI DO CONGRESSO', 'PLN'),
          ('PROJETO DE DECRETO LEGISLATIVO', 'PDL'), ('PROJETO DE RESOLUCAO', 'PRC'), ('PROPOSTA DE EMENDA A CONSTITUICAO', 'PEC'),
          ('PROPOSTA DE EMENDA CONSTITUCIONAL', 'PEC'), ('MEDIDA PROVISORIA', 'MPV'), ('PROJETO DE LEI', 'PL')]
RX_EXT = re.compile(r'(' + '|'.join(re.escape(a) for a, _ in SIGLAS) + r')\s*(?:N[O°º.]*\s*)?(\d[\d.]*)\s*(?:/|,?\s*DE\s+)(\d{4})')
RX_SIG = re.compile(r'\b(PLP|PLV|PLN|PDL|PRC|PEC|MPV|PL|REQ|RCP|PLS|PLC|PDS)\s*(?:N[O°º.]*\s*)?(\d[\d.]*)\s*/\s*(\d{4})')
def citadas(txt):
    t = unicodedata.normalize('NFD', str(txt or '')).encode('ascii', 'ignore').decode().upper(); achou = []
    for m in RX_EXT.finditer(t): achou.append((m.start(), f"{dict(SIGLAS)[m.group(1)]} {int(m.group(2).replace('.', ''))}/{m.group(3)}"))
    for m in RX_SIG.finditer(t): achou.append((m.start(), f"{m.group(1)} {int(m.group(2).replace('.', ''))}/{m.group(3)}"))
    return [c for _, c in sorted(achou)]
IDMAT = {}
for f in glob.glob(P('dados', 'proposicoes-*.json')):
    for it in lj(f, {}).get('itens', []):
        if it.get('c') and it.get('i'): IDMAT.setdefault(((it.get('k') or ['C'])[0], it['c'].upper()), it['i'])
CACHE_MAT = {}
def id_materia(casa, cod):
    ch = (casa, cod.upper())
    if ch in IDMAT: return IDMAT[ch]
    if ch in CACHE_MAT: return CACHE_MAT[ch]
    m = re.match(r'(\S+) (\d+)/(\d{4})$', cod); i = None
    if m:
        try:
            if casa == 'C':
                r = requests.get('https://dadosabertos.camara.leg.br/api/v2/proposicoes', params={'siglaTipo': m.group(1), 'numero': m.group(2), 'ano': m.group(3)}, headers={**UA, 'accept': 'application/json'}, timeout=30)
                d = r.json().get('dados') or []
                if d: i = d[0]['id']
            else:
                r = requests.get('https://legis.senado.leg.br/dadosabertos/processo', params={'sigla': m.group(1), 'numero': m.group(2), 'ano': m.group(3)}, headers={**UA, 'accept': 'application/json'}, timeout=30)
                d = r.json() if r.ok else []
                for x in (d if isinstance(d, list) else [d]):
                    if isinstance(x, dict) and x.get('codigoMateria'): i = x['codigoMateria']; break
        except Exception as e: print('matéria', casa, cod, e)
    CACHE_MAT[ch] = i
    return i
def url_materia(casa, i):
    return (f'https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={i}' if casa == 'C'
            else f'https://www25.senado.leg.br/web/atividade/materias/-/materia/{i}')
def links_votacao(v):
    casa, out, vist = v['k'], [], set()
    cods = ([v['mat']] if v.get('mat') else []) + citadas(v.get('me')) + citadas(v.get('desc'))
    for c in cods:
        c = c.upper()
        if c in vist: continue
        vist.add(c)
        i = id_materia(casa, c); ca = casa
        if not i and c.split()[0] not in ('REQ', 'RCP'):
            ca = 'S' if casa == 'C' else 'C'; i = id_materia(ca, c)
        if not i and casa == 'C' and c == (v.get('mat') or '').upper() and re.match(r'C:\d+-', v['id']):
            ca, i = 'C', v['id'][2:].split('-')[0]
        if i: out.append({'c': c, 'u': url_materia(ca, i)})
        if len(out) >= 4: break
    return sorted(out, key=lambda x: x['c'].split()[0] in ('REQ', 'RCP'))   # o projeto antes do requerimento

cands = {}
for b in BAN:
    vs = sorted(CAND[b['id']], key=lambda v: v.get('d') or '', reverse=True)
    cands[b['id']] = [{'id': v['id'], 'd': v.get('d'), 'k': v['k'], 'mat': v.get('mat'), 'me': (v.get('me') or '')[:400], 'desc': (v.get('desc') or '')[:220],
                       'bd': v.get('bd'), 'p': classe(v.get('ck') or '').get('p') or [], 's': classe(v.get('ck') or '').get('s') or '', 'l': links_votacao(v)} for v in vs[:60]]
print('links de matérias:', len(CACHE_MAT), 'consultas às APIs,', sum(1 for i in CACHE_MAT.values() if i), 'encontradas')

out = {'gerado': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'versao_regras': REG.get('versao'),
       'bancadas': [{k: b[k] for k in ('id', 'nome', 'descricao')} for b in BAN],
       'fontes': {'empresas_e_bens': 'Receita (quadro de sócios, nov/2026) e TSE, via ramo analises-saida-plp299_tudo', 'frentes': len(FRENTES) > 0, 'ocupacao_r2': bool(os.environ.get('R2_ACCOUNT_ID'))},
       'resumo': {f'{b}|{c}|{"triagem" if t else "regra"}': n for (b, c, t), n in sorted(cont_cat.items())},
       'votacoes': cands, 'p': saida}
corpo = json.dumps(out, ensure_ascii=False, separators=(',', ':')).encode()
if S3:
    S3.put_object(Bucket=BUCKET, Key='bancadas/bancadas.json', Body=corpo, ContentType='application/json')
    log('gravado no R2: bancadas/bancadas.json', len(corpo) // 1000, 'kB')
else:
    # Sem acesso ao R2 (teste local): grava fora do repositório, porque tem vínculos de terceiros.
    open(os.path.join(RAIZ, '..', 'bancadas-privado.json'), 'wb').write(corpo)
    log('gravado em ../bancadas-privado.json (teste local)')
log('parlamentares com alguma bancada', len(saida))

# ---------------------------------------------------------------- versão pública (site)
# Só as bancadas marcadas com "publicar": true nas regras. Entra quem a equipe enquadrou como núcleo ou aliado e,
# entre os casos que não foram para a triagem, quem a regra enquadrou assim. Casos ainda não conferidos ficam de fora.
# Só evidências públicas do próprio parlamentar (nada de familiares e terceiros).
DEC = BC.get('decisoes', {}) or {}
pub = [b for b in BAN if b.get('publicar')]
if pub:
    pp, resumo = {}, {}
    for b in pub:
        bid = b['id']; pend = 0; equipe = 0
        for k, p in saida.items():
            x = p['b'].get(bid)
            if not x: continue
            d = DEC.get(f'{k}|{bid}')
            if d: final, por = d.get('d'), 'equipe'; equipe += 1
            elif not x['t']: final, por = x['cat'], 'regra'
            else: final, por = None, None; pend += 1
            if final not in ('nucleo', 'aliado'): continue
            evs = [[e[0], e[2], e[3], e[4]] for e in x['ev'] if not (len(e) > 5 and e[5]) and e[1] and e[0] in ('V', 'A')]
            evs.sort(key=lambda e: e[0] != 'V')
            reg = pp.setdefault(k, {kk: p[kk] for kk in ('n', 'c', 's', 'uf', 'g')} | {'b': {}})
            reg['b'][bid] = {'cat': final, 'por': por, 'ev': evs[:10]}
        resumo[bid] = {'pendentes': pend, 'conferidos': equipe}
    publico = {'gerado': out['gerado'], 'bancadas': [{k: b[k] for k in ('id', 'nome', 'descricao')} | resumo[b['id']] for b in pub],
               'em_preparo': [b['nome'] for b in BAN if not b.get('publicar')], 'p': pp}
    json.dump(publico, open(P('dados', 'bancadas.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    log('versão pública:', ', '.join(b['nome'] for b in pub), '|', len(pp), 'parlamentares')
for b in BAN:
    l = {c: sum(n for (bb, cc, t), n in cont_cat.items() if bb == b['id'] and cc == c) for c in ('nucleo', 'aliado', 'interesse', 'duvida')}
    tr = sum(n for (bb, cc, t), n in cont_cat.items() if bb == b['id'] and t)
    log(f"{b['nome']:22s}", l, 'para triagem:', tr)
