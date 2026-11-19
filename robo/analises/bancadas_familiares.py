"""Vínculos indiretos dos parlamentares com empresas dos setores das bancadas (exceto mídia, que tem levantamento
próprio em midia3.py, e pauta religiosa): o mesmo método da mídia aplicado a agronegócio, segurança e armas, mineração,
setor financeiro, saúde privada, educação privada, bets e plataformas digitais.

Universo por setor: empresas ATIVAS com a atividade principal do setor (bancadas-regras.json) e capital social a partir
do mínimo do setor (capital_minimo_familiares), para não afogar a triagem em microempresas.
Vínculos procurados (indícios, a conferir pela equipe):
- possível familiar: sócio com sobrenome raro do parlamentar, ou dois sobrenomes em comum, com empresa no mesmo estado;
- sócio em comum: quem é sócio do parlamentar em outra empresa e também é sócio da empresa do setor;
- representação: o parlamentar é representante legal de um sócio;
- saída: o parlamentar era sócio da empresa na base mais antiga da Receita e não é mais.
Lê a Receita pela cópia no R2 e grava só no R2 privado: bancadas/familiares.json. Na saída pública fica só um resumo."""
import csv, io, json, os, re, subprocess, sys, time, unicodedata, zipfile, collections
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'boto3'], check=True)
import boto3

T0 = time.time()
def log(*a): print(f'[{(time.time()-T0)/60:.1f} min]', *a, flush=True)
def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z ]', ' ', s)).strip()
csv.field_size_limit(10**9)
OUT = 'saida'; os.makedirs(OUT, exist_ok=True); os.makedirs('/tmp/r2', exist_ok=True)
B = os.environ.get('R2_BUCKET', 'exterminadores-dados')
S3 = boto3.client('s3', endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID'].strip()}.r2.cloudflarestorage.com",
                  aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'].strip(), aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'].strip(), region_name='auto')
IDX = json.loads(S3.get_object(Bucket=B, Key='receita/cnpj/indice.json')['Body'].read())
MES, ANTIGO = IDX['mes_atual'], IDX['mes_antigo']
def ler(mes, nome, tratar):
    chave = f'receita/cnpj/{mes}/{nome}'; destino = '/tmp/r2/' + chave.replace('/', '_')
    if not os.path.exists(destino):
        try: S3.download_file(B, chave, destino)
        except Exception as e: log('sem', chave, e); return
    with zipfile.ZipFile(destino) as zf:
        for n in zf.namelist():
            with zf.open(n) as f:
                for r in csv.reader(io.TextIOWrapper(f, encoding='latin-1', errors='ignore'), delimiter=';'):
                    tratar(r)

REG = json.load(open('bancadas-regras.json'))
FORA = {'midia', 'religiosa'}
SET = [(b['id'], tuple(b['cnae']), float(b.get('capital_minimo_familiares', 500000))) for b in REG['bancadas'] if b['id'] not in FORA]
def setor(cnae): return [bid for bid, pref, _ in SET if cnae.startswith(pref)]
MINCAP = {bid: c for bid, _, c in SET}

# ---------------------------------------------------------------- parlamentares
def doramo(ramo, n):
    subprocess.run(f'git fetch -q --depth 1 origin {ramo}', shell=True)
    r = subprocess.run(f'git show FETCH_HEAD:{n}', shell=True, capture_output=True)
    return json.loads(r.stdout) if r.returncode == 0 else None
IND = json.load(open('dados/indice.json'))['p']
EX = {k for k, p in IND.items() if p.get('ex')}
PARL = {k: p for k, p in (doramo('analises-saida-midia3', 'parlamentares.json') or {}).items() if k in EX}
CHAVES = {(norm(p['nomeCompleto']), c[3:9]): k for k, p in PARL.items() if p.get('nomeCompleto') for c in p.get('cpfs', [])}
SOC = (doramo('analises-saida-plp299_tudo', 'socios.json') or {}).get('socios', [])
EMPP = collections.defaultdict(set)
for s in SOC:
    if s['codigo'] in EX: EMPP[s['cnpj']].add(s['codigo'])
log('parlamentares', len(PARL), 'chaves', len(CHAVES), 'empresas dos parlamentares', len(EMPP))

# ---------------------------------------------------------------- universo: estabelecimentos ativos do setor, depois capital
CAND = {}   # cnpj básico -> {'b': set(bancadas), 'uf': set()}
def t_est(r):
    if len(r) < 21 or r[5] != '02': return
    bs = setor(r[11])
    if not bs: return
    c = CAND.get(r[0])
    if c is None: c = CAND[r[0]] = {'b': set(), 'uf': set()}
    c['b'].update(bs); c['uf'].add(r[19])
for i in range(10): ler(MES, f'Estabelecimentos{i}.zip', t_est)
log('empresas ativas dos setores', len(CAND))
U = {}
def t_emp(r):
    if len(r) < 5: return
    c = CAND.get(r[0])
    if not c: return
    try: cap = float(r[4].replace('.', '').replace(',', '.'))
    except ValueError: cap = 0
    bs = {b for b in c['b'] if cap >= MINCAP[b]}
    if bs: U[r[0]] = {'b': sorted(bs), 'uf': sorted(c['uf']), 'razao': r[1], 'capital': cap}
for i in range(10): ler(MES, f'Empresas{i}.zip', t_emp)
CAND = None
log('universo com capital mínimo', len(U), collections.Counter(b for u in U.values() for b in u['b']))

# ---------------------------------------------------------------- sócios
QSA = collections.defaultdict(list); COS = collections.defaultdict(set); REP = []
def t_soc(r):
    if len(r) < 11: return
    b = r[0]
    if b in U and r[1] == '2': QSA[b].append((r[2], r[3].strip('*'), r[4], r[5]))
    if b in EMPP and r[1] == '2': COS[(norm(r[2]), r[3].strip('*'))] |= EMPP[b]
    if b in U and r[8]:
        k = CHAVES.get((norm(r[8]), r[7].strip('*')))
        if k: REP.append((k, b, r[2]))
for i in range(10): ler(MES, f'Socios{i}.zip', t_soc)
log('sócios no universo', sum(map(len, QSA.values())), 'co-sócios dos parlamentares', len(COS))
ANT = []
def t_ant(r):
    if len(r) >= 6 and r[1] == '2' and r[0] in U:
        k = CHAVES.get((norm(r[2]), r[3].strip('*')))
        if k: ANT.append((k, r[0], r[5]))
for i in range(10): ler(ANTIGO, f'Socios{i}.zip', t_ant)

# ---------------------------------------------------------------- vínculos
V = collections.defaultdict(lambda: collections.defaultdict(list))
def add(k, b, tipo, forca, det):
    u = U[b]
    for bid in u['b']:
        V[k][bid].append({'tipo': tipo, 'forca': forca, 'cnpj': b, 'razao': u['razao'], 'uf': '/'.join(u['uf']), 'capital': u['capital'], 'det': det})
QUAL = {'05': 'administrador', '10': 'diretor', '16': 'presidente', '22': 'sócio', '49': 'sócio-administrador', '65': 'titular'}
atuais = collections.defaultdict(set)
for b, ss in QSA.items():
    for nome, cpf6, q, ent in ss:
        k = CHAVES.get((norm(nome), cpf6))
        if k: atuais[k].add(b)
# sócio em comum
for b, ss in QSA.items():
    for nome, cpf6, q, ent in ss:
        for k in COS.get((norm(nome), cpf6), ()):
            if CHAVES.get((norm(nome), cpf6)) == k or b in atuais[k]: continue
            add(k, b, 'Sócio do parlamentar em outra empresa', 'forte', f"{nome.title()} ({QUAL.get(q, 'sócio')} desde {ent})")
# representação
for k, b, nome in REP: add(k, b, 'Parlamentar é representante legal de sócio', 'forte', nome.title())
# saídas
for k, b, ent in ANT:
    if b not in atuais[k]: add(k, b, f'Saiu da sociedade desde {ANTIGO}', 'forte', f"entrada {ent}; sócios atuais: " + '; '.join(n.title() for n, *_ in QSA.get(b, [])[:5]))
# possível familiar por sobrenome
PART = {'DA', 'DE', 'DO', 'DAS', 'DOS', 'E', 'JUNIOR', 'FILHO', 'NETO', 'SOBRINHO', 'JR'}
freq, prim = collections.Counter(), collections.Counter()
for ss in QSA.values():
    for nome, *_ in ss:
        t = norm(nome).split()
        if t: prim[t[0]] += 1; freq.update(set(t[1:]))
comuns = {t for t, n in freq.most_common(400)} | {t for t, n in prim.items() if n >= 20} | PART
idx = collections.defaultdict(list)
for b, ss in QSA.items():
    for nome, cpf6, q, ent in ss:
        for t in set(norm(nome).split()[1:]) - comuns: idx[t].append((b, nome, cpf6, q))
for k, p in PARL.items():
    toks = [t for t in norm(p.get('nomeCompleto')).split()[1:] if t not in comuns and len(t) > 2]
    vist = set()
    for t in toks:
        for b, nome, cpf6, q in idx.get(t, []):
            if p.get('uf') not in U[b]['uf'] or (b, nome) in vist or CHAVES.get((norm(nome), cpf6)) == k or b in atuais[k]: continue
            vist.add((b, nome))
            em_comum = set(norm(nome).split()) & set(toks)
            raro = min(freq[x] for x in em_comum)
            forca = 'sobrenome (2+)' if len(em_comum) >= 2 else ('sobrenome raro' if raro <= 15 else None)
            if forca: add(k, b, 'Possível familiar', forca, f"{nome.title()} ({QUAL.get(q, 'sócio')}); sobrenomes em comum: {', '.join(sorted(em_comum)).title()}")

out = {'gerado': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'mes_receita': MES, 'mes_antigo': ANTIGO,
       'capital_minimo': MINCAP, 'vinculos': {k: dict(v) for k, v in V.items()}}
S3.put_object(Bucket=B, Key='bancadas/familiares.json', Body=json.dumps(out, ensure_ascii=False).encode(), ContentType='application/json')
cont = collections.Counter((bid, x['forca']) for v in V.values() for bid, xs in v.items() for x in xs)
porp = collections.Counter(bid for v in V.values() for bid in v)
json.dump({'gerado': out['gerado'], 'universo': len(U), 'parlamentares_por_bancada': dict(porp), 'vinculos': {f'{b}|{f}': n for (b, f), n in sorted(cont.items())}},
          open(f'{OUT}/resumo.json', 'w'), ensure_ascii=False, indent=1)
log('gravado no R2: bancadas/familiares.json |', dict(porp))
