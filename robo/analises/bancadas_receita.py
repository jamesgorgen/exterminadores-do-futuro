"""Sinais das bancadas que exigem a base inteira da Receita e as prestações de contas do TSE (cópias no R2).

Para cada parlamentar e cada bancada de bancadas-regras.json:
- empresa do próprio parlamentar com atividade SECUNDÁRIA do setor (a principal já entra em robo/bancadas.py);
- empresa controlada por uma empresa do parlamentar (holding), pela atividade principal ou secundária;
- empresa citada pelo CNPJ nos bens declarados ao TSE, pela atividade principal ou secundária;
- doações de campanha (2018, 2022, 2026) de pessoas que são sócias de empresas ativas do setor (atividade principal).
O resultado tem nomes de terceiros (doadores) e vai só para o R2 privado: bancadas/sinais_receita.json.
Na pasta de saída pública fica só um resumo com contagens. Roda pela fila das análises avulsas."""
import csv, io, json, os, re, subprocess, sys, time, unicodedata, zipfile, collections
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'boto3'], check=True)
import boto3

T0 = time.time()
def log(*a): print(f'[{(time.time()-T0)/60:.1f} min]', *a, flush=True)
def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z ]', ' ', s)).strip()
def dig(s): return re.sub(r'\D', '', str(s or ''))
csv.field_size_limit(10**9)
OUT = 'saida'; os.makedirs(OUT, exist_ok=True); os.makedirs('/tmp/r2', exist_ok=True)
B = os.environ.get('R2_BUCKET', 'exterminadores-dados')
S3 = boto3.client('s3', endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID'].strip()}.r2.cloudflarestorage.com",
                  aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'].strip(), aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'].strip(), region_name='auto')
IDX = json.loads(S3.get_object(Bucket=B, Key='receita/cnpj/indice.json')['Body'].read())
MES = IDX['mes_atual']; NO_R2 = {a[0] for a in IDX['arquivos'] if a[1]}
def baixar(chave):
    destino = '/tmp/r2/' + chave.replace('/', '_')
    if chave not in NO_R2 and not chave.startswith('tse/'): return None
    if not os.path.exists(destino):
        try: S3.download_file(B, chave, destino)
        except Exception as e: log('sem', chave, e); return None
    return destino
def ler(nome, tratar):
    z = baixar(f'receita/cnpj/{MES}/{nome}')
    if not z: log('não baixou', nome); return
    with zipfile.ZipFile(z) as zf:
        for n in zf.namelist():
            with zf.open(n) as f:
                for r in csv.reader(io.TextIOWrapper(f, encoding='latin-1', errors='ignore'), delimiter=';'):
                    tratar(r)

REG = json.load(open('bancadas-regras.json'))
BAN = [(b['id'], tuple(b['cnae'])) for b in REG['bancadas']]
def setores(cnaes):
    return {bid for bid, pref in BAN for c in cnaes if c and c.startswith(pref)}

# ---------------------------------------------------------------- parlamentares, empresas e bens (análise do PLP 299)
subprocess.run('git fetch -q --depth 1 origin analises-saida-plp299_tudo', shell=True)
def doramo(n): return json.loads(subprocess.run(f'git show FETCH_HEAD:{n}', shell=True, capture_output=True).stdout or b'null')
IND = json.load(open('dados/indice.json'))['p']
EX = {k for k, p in IND.items() if p.get('ex')}
CPF = {}; NOMES = {}
for arq, chave, pre in (('senadores_tse.json', 'senadores', 'S'), ('deputados_tse.json', 'deputados', 'C')):
    for c, s in (doramo(arq) or {}).get(chave, {}).items():
        k = pre + c
        if k not in EX: continue
        NOMES[k] = s.get('nomeCompleto')
        for t in s.get('tse', []) + [s]:
            d = dig(t.get('cpf'))
            if len(d) == 11: CPF[d] = k
SOC = (doramo('socios.json') or {}).get('socios', [])
EMPP = collections.defaultdict(set)          # cnpj básico -> parlamentares sócios
for s in SOC:
    if s['codigo'] in EX: EMPP[s['cnpj']].add(s['codigo'])
BENS_CNPJ = collections.defaultdict(set)     # cnpj básico -> parlamentares que o citam nos bens
for arq, pre in (('bens.json', 'S'), ('bens_deputados.json', 'C')):
    for x in doramo(arq) or []:
        k = pre + str(x['codigo'])
        if k not in EX: continue
        for m in re.findall(r'\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}', x.get('desc') or ''):
            d = dig(m)
            if len(d) == 14: BENS_CNPJ[d[:8]].add(k)
log('parlamentares em exercício', len(EX), 'CPFs', len(CPF), 'empresas dos parlamentares', len(EMPP), 'CNPJs citados nos bens', len(BENS_CNPJ))

# ---------------------------------------------------------------- doações de campanha (pessoas físicas)
DOA = collections.defaultdict(lambda: collections.defaultdict(float))   # (nome, cpf6) do doador -> parlamentar -> valor
TOT = collections.defaultdict(float)                                    # parlamentar -> total doado por pessoas físicas
DOADOR_NOME = {}
for ano in (2018, 2022, 2026):
    z = baixar(f'tse/prestacao_de_contas_eleitorais_candidatos_{ano}.zip')
    if not z: continue
    with zipfile.ZipFile(z) as zf:
        for n in zf.namelist():
            if not (n.startswith('receitas_candidatos') and 'BRASIL' in n and 'originario' not in n and n.endswith('.csv')): continue
            with zf.open(n) as f:
                for r in csv.DictReader(io.TextIOWrapper(f, encoding='latin-1', errors='ignore'), delimiter=';'):
                    k = CPF.get(dig(r.get('NR_CPF_CANDIDATO')))
                    if not k: continue
                    doc = dig(r.get('NR_CPF_CNPJ_DOADOR'))
                    if len(doc) != 11 or doc in CPF: continue          # só pessoas físicas, sem o próprio parlamentar
                    try: v = float((r.get('VR_RECEITA') or '0').replace('.', '').replace(',', '.'))
                    except ValueError: continue
                    chave = (norm(r.get('NM_DOADOR') or r.get('NM_DOADOR_RFB')), doc[3:9])
                    DOA[chave][(k, ano)] += v; TOT[k] += v; DOADOR_NOME[chave] = (r.get('NM_DOADOR') or '').strip().title()
    log('doações lidas', ano, 'doadores distintos', len(DOA))
    os.remove(z)

# ---------------------------------------------------------------- sócios: empresas dos doadores e empresas controladas pelos parlamentares
DOADOR_EMP = collections.defaultdict(set)   # (nome, cpf6) -> {cnpj básico}
FILHAS = collections.defaultdict(set)       # cnpj básico controlado -> {empresa do parlamentar}
def t_soc(r):
    if len(r) < 6: return
    if r[1] == '2':
        k = (norm(r[2]), r[3].strip('*'))
        if k in DOA: DOADOR_EMP[k].add(r[0])
    elif r[1] == '1' and r[3][:8] in EMPP:
        FILHAS[r[0]].add(r[3][:8])
for i in range(10): ler(f'Socios{i}.zip', t_soc)
log('doadores sócios de empresas', len(DOADOR_EMP), 'empresas controladas por empresas de parlamentares', len(FILHAS))

# ---------------------------------------------------------------- estabelecimentos: atividades e situação
ALVO = set(EMPP) | set(FILHAS) | set(BENS_CNPJ) | {b for s in DOADOR_EMP.values() for b in s}
ATV = {}   # cnpj básico -> {'p': principais, 's': secundárias, 'ativa': bool, 'uf': set}
def t_est(r):
    if len(r) < 21 or r[0] not in ALVO: return
    a = ATV.setdefault(r[0], {'p': set(), 's': set(), 'ativa': False, 'uf': set()})
    a['p'].add(r[11]); a['s'] |= {x for x in r[12].split(',') if x}
    a['ativa'] = a['ativa'] or r[5] == '02'; a['uf'].add(r[19])
for i in range(10): ler(f'Estabelecimentos{i}.zip', t_est)
RAZAO = {}
def t_emp(r):
    if len(r) >= 2 and r[0] in ALVO: RAZAO[r[0]] = r[1]
for i in range(10): ler(f'Empresas{i}.zip', t_emp)
log('empresas com atividade lida', len(ATV))

# ---------------------------------------------------------------- sinais por parlamentar e bancada
S = collections.defaultdict(lambda: collections.defaultdict(list))
def nome(b): return (RAZAO.get(b) or b).strip()
for b, ks in EMPP.items():
    a = ATV.get(b)
    if not a or not a['ativa']: continue
    for bid in setores(a['s']) - setores(a['p']):
        for k in ks: S[k][bid].append({'t': 'empresa_secundaria', 'cnpj': b, 'razao': nome(b)})
for b, maes in FILHAS.items():
    a = ATV.get(b)
    if not a or not a['ativa']: continue
    for bid in setores(a['p'] | a['s']):
        for m in maes:
            for k in EMPP[m]: S[k][bid].append({'t': 'controlada', 'cnpj': b, 'razao': nome(b), 'por': nome(m)})
for b, ks in BENS_CNPJ.items():
    a = ATV.get(b)
    if not a: continue
    for bid in setores(a['p'] | a['s']):
        for k in ks: S[k][bid].append({'t': 'bem_cnpj', 'cnpj': b, 'razao': nome(b), 'ativa': a['ativa']})
doa = collections.defaultdict(lambda: collections.defaultdict(lambda: {'v': 0.0, 'doadores': {}}))
for chave, emps in DOADOR_EMP.items():
    sets = set()
    for b in emps:
        a = ATV.get(b)
        if a and a['ativa']: sets |= {(bid, b) for bid in setores(a['p'])}
    if not sets: continue
    for (k, ano), v in DOA[chave].items():
        for bid in {s[0] for s in sets}:
            d = doa[k][bid]; d['v'] += v
            emp = next(nome(b) for x, b in sets if x == bid)
            dd = d['doadores'].setdefault(DOADOR_NOME.get(chave, ''), {'v': 0.0, 'empresa': emp, 'anos': []})
            dd['v'] += v
            if ano not in dd['anos']: dd['anos'].append(ano)
for k, bs in doa.items():
    for bid, d in bs.items():
        top = sorted(d['doadores'].items(), key=lambda x: -x[1]['v'])[:5]
        S[k][bid].append({'t': 'doacoes', 'valor': round(d['v'], 2), 'parcela': round(d['v'] / TOT[k], 3) if TOT[k] else None, 'n': len(d['doadores']),
                          'top': [{'nome': n, 'valor': round(x['v'], 2), 'empresa': x['empresa'], 'anos': x['anos']} for n, x in top]})

out = {'gerado': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'mes_receita': MES, 'sinais': {k: dict(v) for k, v in S.items()}}
S3.put_object(Bucket=B, Key='bancadas/sinais_receita.json', Body=json.dumps(out, ensure_ascii=False).encode(), ContentType='application/json')
resumo = collections.Counter((bid, x['t']) for k, v in S.items() for bid, xs in v.items() for x in xs)
json.dump({'gerado': out['gerado'], 'parlamentares_com_sinal': len(S), 'contagem': {f'{b}|{t}': n for (b, t), n in sorted(resumo.items())}},
          open(f'{OUT}/resumo.json', 'w'), ensure_ascii=False, indent=1)
log('gravado no R2: bancadas/sinais_receita.json |', len(S), 'parlamentares com algum sinal')
for (b, t), n in sorted(resumo.items()): log(f'  {b:12s} {t:20s} {n}')
