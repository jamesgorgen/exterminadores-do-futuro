"""Mídia e parlamentares: emissoras de rádio e TV, jornais e revistas ligados direta ou indiretamente a senadores e deputados.

Cruzamentos (cada um é um indício, não uma prova):
 1. Universo: outorgas de radiodifusão do MCom (CNPJ) + empresas com CNAE principal ou secundário de rádio, TV, jornal,
    revista ou agência de notícias + razão social com RADIO/TV/RADIODIFUSAO/JORNAL.
 2. Quadro societário completo dessas empresas, com holdings abertas até dois níveis.
 3. Sobrenome do parlamentar entre os sócios (mesma UF, sobrenomes comuns descartados).
 4. Rede: quem é sócio do parlamentar em outra empresa e também é sócio de empresa de mídia.
 5. Parlamentar como representante legal de sócio.
 6. Dinheiro: cota parlamentar (Câmara e Senado) paga a empresa de mídia; gastos de campanha (2018 e 2022) com empresa
    de mídia; doações de sócios de empresa de mídia às campanhas.
 7. Saídas: parlamentar sócio de empresa de mídia na base mais antiga da Receita e ausente na atual.
 8. Funcionários de gabinete (Câmara) entre os sócios.
Saída no ramo analises-saida-midia, publicada ao fim de cada etapa."""
import csv, io, json, os, re, subprocess, time, zipfile, collections, unicodedata, xml.etree.ElementTree as ET
import requests

UA = {'user-agent': 'exterminadores-do-futuro (observatório; contato@exterminadores.com.br)'}
OUT = 'saida'; os.makedirs(OUT, exist_ok=True)
RFB = 'https://arquivos.receitafederal.gov.br/public.php/webdav/Dados'
TOKEN = ('gn672Ad4CF8N6TK', '')
TSE = 'https://cdn.tse.jus.br/estatistica/sead/odsele'
T0 = time.time()
csv.field_size_limit(10**9)

def log(*a): print(f'[{(time.time()-T0)/60:.0f} min]', *a, flush=True)
def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z ]', ' ', s)).strip()
def dig(s): return re.sub(r'\D', '', str(s or ''))
def salvar(nome, obj):
    # O GitHub recusa arquivos acima de 100 MB: grava compactado (.json.gz) quando passa de 20 MB
    import gzip
    txt = json.dumps(obj, ensure_ascii=False).encode()
    for x in (f'{OUT}/{nome}', f'{OUT}/{nome}.gz'):
        if os.path.exists(x): os.remove(x)
    if len(txt) > 20e6:
        with gzip.open(f'{OUT}/{nome}.gz', 'wb', 6) as f: f.write(txt)
    else:
        open(f'{OUT}/{nome}', 'wb').write(txt)
    open(f'{OUT}/progresso.txt', 'a').write(f'{(time.time()-T0)/60:.0f} min salvo {nome} {len(txt)/1e6:.0f} MB\n')
def publicar(etapa):
    log(etapa)
    if not os.environ.get('TOKEN_GH'): return
    subprocess.run(f'''cd {OUT} && rm -rf .git && git init -q -b analises-saida-midia && git add -A &&
      git -c user.name=robo -c user.email=robo@users.noreply.github.com commit -qm "{etapa}" &&
      git push -qf "https://x-access-token:$TOKEN_GH@github.com/$REPO.git" analises-saida-midia''', shell=True)
def baixar(url, destino, auth=None, tentativas=3):
    if os.path.exists(destino): return destino
    for t in range(tentativas):
        try:
            with requests.get(url, headers=UA, auth=auth, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(destino + '.part', 'wb') as f:
                    for b in r.iter_content(1 << 20): f.write(b)
            os.rename(destino + '.part', destino); return destino
        except Exception as e:
            log('falha ao baixar', url, e); time.sleep(20)
    return None
def etapa(nome, fn):
    try: fn()
    except Exception as e:
        import traceback; traceback.print_exc(); log('ETAPA FALHOU', nome, e)
    publicar(nome)

# ---------------------------------------------------------------- parlamentares (da análise do PLP 299)
subprocess.run('git fetch -q --depth 1 origin analises-saida-plp299_tudo', shell=True)
def doramo(n): return json.loads(subprocess.run(f'git show FETCH_HEAD:{n}', shell=True, capture_output=True, text=True).stdout)
PARL = {}
for arq, chave, pre in (('senadores_tse.json', 'senadores', 'S'), ('deputados_tse.json', 'deputados', 'C')):
    for c, s in doramo(arq)[chave].items():
        cpfs = {dig(t.get('cpf')) for t in s.get('tse', []) if len(dig(t.get('cpf'))) == 11} | ({dig(s.get('cpf'))} if len(dig(s.get('cpf'))) == 11 else set())
        PARL[pre + c] = {'nome': s.get('nome'), 'nomeCompleto': s.get('nomeCompleto'), 'uf': s.get('uf'), 'partido': s.get('partido'),
                         'cpfs': sorted(cpfs), 'sqs': [t['sq'] for t in s.get('tse', []) if t.get('sq')], 'ex': s.get('ex')}
CHAVES = {(norm(p['nomeCompleto']), cpf[3:9]): k for k, p in PARL.items() if p['nomeCompleto'] for cpf in p['cpfs']}
SOC_PARL = doramo('socios.json')['socios']
EMP_PARL = {s['cnpj'] for s in SOC_PARL}      # empresas (cnpj básico) de que os parlamentares são sócios
log('parlamentares', len(PARL), 'chaves', len(CHAVES), 'empresas dos parlamentares', len(EMP_PARL))
salvar('parlamentares.json', PARL)

# ---------------------------------------------------------------- 1a. outorgas do MCom
MCOM = {}   # cnpj14 -> lista de registros (serviço, município, uf, entidade)
def outorgas():
    urls = set(['https://s3.mcom.gov.br/radcom/SCR_DADOS_RADIODIFUSAO_TV_GTVD_RTV_RTVD_FM_OM.csv',
                'https://s3.mcom.gov.br/radcom/rep_srd_estacao.csv'])
    try:
        pag = requests.get('https://www.gov.br/mcom/pt-br/acesso-a-informacao/dados-abertos', headers=UA, timeout=60).text
        urls |= set(re.findall(r'https?://s3\.mcom\.gov\.br/[^"\'\s<>]+\.csv', pag))
        for pdf in set(re.findall(r'https?://www\.gov\.br/mcom/[^"\'\s<>]+metadados[^"\'\s<>]*\.pdf', pag)):
            try:
                c = requests.get(pdf, headers=UA, timeout=60).content
                urls |= {x.decode() for x in re.findall(rb'https?://s3\.mcom\.gov\.br/[A-Za-z0-9_./\-]+\.csv', c)}
            except Exception: pass
    except Exception as e: log('página de dados abertos do MCom', e)
    log('CSVs do MCom:', sorted(urls))
    amostras = {}
    for u in sorted(urls):
        try:
            b = requests.get(u, headers=UA, timeout=300).content
        except Exception as e:
            log('falha', u, e); continue
        txt = None
        for enc in ('utf-8-sig', 'latin-1'):
            try: txt = b.decode(enc); break
            except UnicodeDecodeError: pass
        sep = ';' if txt[:2000].count(';') >= txt[:2000].count(',') else ','
        linhas = list(csv.reader(io.StringIO(txt), delimiter=sep))
        if not linhas: continue
        cab = linhas[0]; amostras[u] = {'cabecalho': cab, 'linhas': linhas[1:4], 'total': len(linhas) - 1}
        for r in linhas[1:]:
            reg = dict(zip(cab, r))
            for h, v in zip(cab, r):
                d = dig(v)
                if 'CNPJ' in h.upper() and 12 <= len(d) <= 14: d = d.zfill(14)
                elif not (len(d) == 14 and re.fullmatch(r'\s*\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\s*', v)): continue
                if len(MCOM.get(d, [])) < 5:
                    MCOM.setdefault(d, []).append({'fonte': u.rsplit('/', 1)[-1], **{k: reg[k] for k in list(reg)[:40]}})
    salvar('mcom_amostras.json', amostras)
    log('CNPJs com outorga no MCom:', len(MCOM))

# ---------------------------------------------------------------- Receita: listas e leitura
def listar(caminho):
    r = requests.request('PROPFIND', f'{RFB}/{caminho}', headers={**UA, 'Depth': '1'}, auth=TOKEN, timeout=120)
    return [h.text for h in ET.fromstring(r.content).iter('{DAV:}href')]
# Cópia no Cloudflare R2 (robo/analises/receita_r2.py), muito mais rápida que o servidor da Receita
S3 = None
if os.environ.get('R2_ACCOUNT_ID'):
    subprocess.run('pip install -q boto3', shell=True)
    import boto3
    S3 = boto3.client('s3', endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID'].strip()}.r2.cloudflarestorage.com",
                      aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'].strip(), aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'].strip(), region_name='auto')
    IDX = json.loads(S3.get_object(Bucket=os.environ['R2_BUCKET'], Key='receita/cnpj/indice.json')['Body'].read())
    NO_R2 = {a[0] for a in IDX['arquivos'] if a[1]}
    MESES = [IDX['mes_antigo'], IDX['mes_atual']]
else:
    NO_R2 = set()
    MESES = sorted(h.rstrip('/').split('/')[-1] for h in listar('Cadastros/CNPJ/') if re.search(r'\d{4}-\d{2}/?$', h))
MES = MESES[-1]; log('meses', MESES[0], '...', MES, '| arquivos no R2:', len(NO_R2))
def do_r2(chave, destino):
    if chave not in NO_R2: return None
    if not os.path.exists(destino): S3.download_file(os.environ['R2_BUCKET'], chave, destino)
    return destino
os.makedirs('/tmp/rfb', exist_ok=True)
def ler(mes, nome, tratar, guardar=False):
    z = do_r2(f'receita/cnpj/{mes}/{nome}', f'/tmp/rfb/{mes}_{nome}') or baixar(f'{RFB}/Cadastros/CNPJ/{mes}/{nome}', f'/tmp/rfb/{mes}_{nome}', TOKEN)
    if not z: log('não baixou', mes, nome); return
    with zipfile.ZipFile(z) as zf:
        for n in zf.namelist():
            with zf.open(n) as f:
                for r in csv.reader(io.TextIOWrapper(f, encoding='latin-1', errors='ignore'), delimiter=';'):
                    tratar(r)
    if not guardar: os.remove(z)
    open(f'{OUT}/progresso.txt', 'a').write(f'{(time.time()-T0)/60:.0f} min {mes} {nome}\n')
    if nome[-5] in '369': publicar(f'lido {mes} {nome}')

CNAE_MIDIA = {'6010100': 'rádio', '6021700': 'TV aberta', '6022501': 'TV por assinatura (programadora)', '6022502': 'TV por assinatura',
              '5812301': 'jornal diário', '5812302': 'jornal não diário', '5822101': 'jornal diário (edição e impressão)',
              '5822102': 'jornal não diário (edição e impressão)', '5813100': 'revista', '5823900': 'revista (edição e impressão)',
              '6391700': 'agência de notícias'}
NOME_MIDIA = re.compile(r'\bRADIO\b|RADIODIFUS|RADIOFUS|\bTV\b|TELEVIS|\bJORNAL|EMISSORA|\bFM\b')
U = {}       # cnpj básico -> dados da empresa de mídia
CONTATO = collections.defaultdict(set)   # (tipo, valor) -> {cnpj básico} para empresas de mídia e empresas dos parlamentares
MUN = {}

def estabelecimentos():
    ler(MES, 'Municipios.zip', lambda r: MUN.__setitem__(r[0], r[1]) if len(r) > 1 else None, guardar=True)
    mcom8 = {c[:8] for c in MCOM}
    def t(r):
        if len(r) < 28: return
        b = r[0]; cn = r[11]; sec = [x for x in r[12].split(',') if x]
        cnaes = [c for c in [cn] + sec if c in CNAE_MIDIA]
        cnpj14 = b + r[1] + r[2]
        if b in mcom8 or cnaes or b in NOMES:
            u = U.setdefault(b, {'estab': [], 'cnaes': set(), 'mcom': False})
            if len(u['estab']) < 5: u['estab'].append({'cnpj': cnpj14, 'sit': r[5], 'cnae': cn, 'uf': r[19], 'mun': r[20]})
            u['cnaes'] |= set(cnaes); u['mcom'] = u['mcom'] or cnpj14 in MCOM
        if (b in U and r[5] == '02') or b in EMP_PARL:
            if len(r[22]) >= 8: CONTATO[('tel', r[21] + r[22])].add(b)
            if '@' in r[27]: CONTATO[('email', r[27].lower())].add(b)
            if r[14]: CONTATO[('end', norm(' '.join(r[14:16]) + ' ' + r[18]))].add(b)
    for i in range(10): ler(MES, f'Estabelecimentos{i}.zip', t)
    log('empresas no universo por CNAE/outorga', len(U))

PISTA = ('RADIO', 'RÁDIO', 'TV', 'TELEVIS', 'JORNAL', 'EMISSORA', 'FM', 'RADIOF', 'RADIOD')
NOMES = set()
def empresas_nome():
    def t(r):
        if len(r) >= 5 and any(x in r[1] for x in PISTA) and NOME_MIDIA.search(norm(r[1])): NOMES.add(r[0])
    for i in range(10): ler(MES, f'Empresas{i}.zip', t, guardar=True)
    log('empresas com nome de mídia', len(NOMES))
def empresas():
    def t(r):
        if len(r) >= 5 and r[0] in U: U[r[0]].update({'razao': r[1], 'natureza': r[2], 'capital': r[4]})
    for i in range(10): ler(MES, f'Empresas{i}.zip', t, guardar=True)
    # descarta casos "só pelo nome" que são claramente outra coisa (rádio-táxi, radiologia etc.)
    for u in U.values(): u['so_nome'] = not u['cnaes'] and not u['mcom']
    fora = re.compile(r'RADIO ?TAXI|RADIOLOG|RADIOTER|RADIADOR|TV ?A ?CABO ?E ?INTERNET|ASSISTENCIA TECNICA|CONSERTO|ELETRONIC|PECAS|ANTENA')
    for b in [b for b, u in U.items() if u.get('so_nome') and fora.search(norm(u.get('razao')))]: del U[b]
    log('universo final', len(U), 'só pelo nome', sum(1 for u in U.values() if u.get('so_nome')))

# ---------------------------------------------------------------- sócios
QSA = collections.defaultdict(list)       # cnpj básico (mídia ou holding) -> sócios
DOPARL_PJ = []                            # empresas dos parlamentares que são sócias de outras empresas
COSOCIOS = collections.defaultdict(set)   # (nome, cpf6) de quem é sócio de empresa de parlamentar -> {parlamentar}
REPRES = []                               # parlamentar como representante legal de sócio
def socios_atual():
    parl_emp = collections.defaultdict(set)
    for s in SOC_PARL: parl_emp[s['cnpj']].add(s['codigo'])
    def t(r):
        if len(r) < 11: return
        b = r[0]
        reg = {'tipo': r[1], 'nome': r[2], 'doc': r[3], 'qualif': r[4], 'entrada': r[5], 'rep_cpf': r[7], 'rep_nome': r[8]}
        if b in U: QSA[b].append(reg)
        if r[1] == '1' and r[3][:8] in EMP_PARL: DOPARL_PJ.append({'cnpj': b, 'socio_pj': r[3], 'nome': r[2], 'qualif': r[4], 'entrada': r[5]})
        if b in parl_emp and r[1] == '2': COSOCIOS[(norm(r[2]), r[3].strip('*'))] |= parl_emp[b]
        if r[8] and (norm(r[8]), r[7].strip('*')) in CHAVES:
            REPRES.append({'parl': CHAVES[(norm(r[8]), r[7].strip('*'))], 'cnpj': b, **reg})
    for i in range(10): ler(MES, f'Socios{i}.zip', t, guardar=True)
    log('sócios de empresas de mídia', sum(len(v) for v in QSA.values()))
    salvar('universo.json', {b: {**u, 'cnaes': sorted(u['cnaes'])} for b, u in U.items()}); salvar('qsa.json', QSA); publicar('sócios nível 1')
    # holdings: segundo e terceiro nível
    for nivel in (2, 3):
        alvo = {s['doc'][:8] for b in list(QSA) for s in QSA[b] if s['tipo'] == '1'} - set(QSA)
        if not alvo: break
        def t2(r):
            if len(r) >= 11 and r[0] in alvo:
                QSA[r[0]].append({'tipo': r[1], 'nome': r[2], 'doc': r[3], 'qualif': r[4], 'entrada': r[5], 'rep_cpf': r[7], 'rep_nome': r[8], 'holding': nivel})
        for i in range(10): ler(MES, f'Socios{i}.zip', t2, guardar=True)
        log('holdings nível', nivel, len(alvo))
    salvar('universo.json', {b: {**u, 'cnaes': sorted(u['cnaes'])} for b, u in U.items()})
    salvar('qsa.json', QSA)
    salvar('doparl_pj.json', DOPARL_PJ)
    salvar('representacao.json', REPRES)
    salvar('cosocios.json', [{'nome': k[0], 'cpf6': k[1], 'parl': sorted(v)} for k, v in COSOCIOS.items()])
    contatos = {f'{k[0]}|{k[1]}': sorted(v) for k, v in CONTATO.items() if len(v) > 1 and (v & set(U)) and (v & EMP_PARL)}
    salvar('contatos_compartilhados.json', contatos)
    log('contatos compartilhados entre mídia e empresas de parlamentares', len(contatos))

def socios_antigo():
    if len(MESES) < 2: return
    antigo = MESES[0]
    achados = []
    def t(r):
        if len(r) >= 6 and r[1] == '2':
            k = (norm(r[2]), r[3].strip('*'))
            if k in CHAVES: achados.append({'parl': CHAVES[k], 'cnpj': r[0], 'qualif': r[4], 'entrada': r[5]})
    for i in range(10): ler(antigo, f'Socios{i}.zip', t)
    atuais = {(s['codigo'], s['cnpj']) for s in SOC_PARL}
    saidas = [a for a in achados if (a['parl'], a['cnpj']) not in atuais]
    salvar('saidas.json', {'mes_antigo': antigo, 'mes_atual': MES, 'saidas': saidas, 'qsa_atual': {a['cnpj']: QSA.get(a['cnpj'], []) for a in saidas}})
    log('vínculos que existiam em', antigo, 'e não existem mais:', len(saidas), 'em empresas de mídia:', sum(1 for a in saidas if a['cnpj'] in U))

# ---------------------------------------------------------------- dinheiro
MIDIA8 = lambda d: dig(d)[:8] in U and len(dig(d)) == 14
def ceap():
    linhas = []
    for ano in (2023, 2024, 2025, 2026):
        z = baixar(f'https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip', f'/tmp/ceap{ano}.zip')
        if not z: continue
        with zipfile.ZipFile(z) as zf:
            with zf.open(zf.namelist()[0]) as f:
                for r in csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig', errors='ignore'), delimiter=';'):
                    if MIDIA8(r.get('txtCNPJCPF')):
                        linhas.append({'casa': 'C', 'parl': 'C' + (r.get('ideCadastro') or ''), 'nome': r.get('txNomeParlamentar'), 'ano': ano,
                                       'cnpj': dig(r['txtCNPJCPF']), 'fornecedor': r.get('txtFornecedor'), 'tipo': r.get('txtDescricao'),
                                       'valor': r.get('vlrLiquido')})
    for ano in (2023, 2024, 2025, 2026):
        try:
            b = requests.get(f'https://www.senado.gov.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv', headers=UA, timeout=300).content.decode('latin-1')
        except Exception as e:
            log('CEAPS', ano, e); continue
        corpo = b.split('\n', 1)[1] if b.upper().startswith('"ULTIMA') or b.upper().startswith('ULTIMA') else b
        for r in csv.DictReader(io.StringIO(corpo), delimiter=';'):
            if MIDIA8(r.get('CNPJ_CPF')):
                linhas.append({'casa': 'S', 'nome': r.get('SENADOR'), 'ano': ano, 'cnpj': dig(r['CNPJ_CPF']), 'fornecedor': r.get('FORNECEDOR'),
                               'tipo': r.get('TIPO_DESPESA'), 'valor': r.get('VALOR_REEMBOLSADO')})
    salvar('ceap_midia.json', linhas)
    log('pagamentos da cota parlamentar a empresas de mídia', len(linhas))

def campanhas():
    sqs = {sq: k for k, p in PARL.items() for sq in p['sqs']}
    socios_midia = {(norm(s['nome']), s['doc'].strip('*')): b for b, ss in QSA.items() for s in ss if s['tipo'] == '2'}
    desp, rec = [], []
    for ano in (2018, 2022):
        z = do_r2(f'tse/prestacao_de_contas_eleitorais_candidatos_{ano}.zip', f'/tmp/pc{ano}.zip') or baixar(f'{TSE}/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{ano}.zip', f'/tmp/pc{ano}.zip')
        if not z: continue
        with zipfile.ZipFile(z) as zf:
            nomes = zf.namelist(); log('arquivos de prestação de contas', ano, [n for n in nomes if 'BRASIL' in n])
            for n in nomes:
                if 'BRASIL' not in n or not n.endswith('.csv'): continue
                if n.startswith('despesas_contratadas'):
                    with zf.open(n) as f:
                        for r in csv.DictReader(io.TextIOWrapper(f, encoding='latin-1', errors='ignore'), delimiter=';'):
                            if r.get('SQ_CANDIDATO') in sqs and MIDIA8(r.get('NR_CPF_CNPJ_FORNECEDOR')):
                                desp.append({'parl': sqs[r['SQ_CANDIDATO']], 'ano': ano, 'cnpj': dig(r['NR_CPF_CNPJ_FORNECEDOR']), 'fornecedor': r.get('NM_FORNECEDOR'),
                                             'descricao': r.get('DS_DESPESA') or r.get('DS_ORIGEM_DESPESA'), 'valor': r.get('VR_DESPESA_CONTRATADA')})
                elif n.startswith('receitas_candidatos') and 'doador_originario' not in n:
                    with zf.open(n) as f:
                        for r in csv.DictReader(io.TextIOWrapper(f, encoding='latin-1', errors='ignore'), delimiter=';'):
                            if r.get('SQ_CANDIDATO') not in sqs: continue
                            doc = dig(r.get('NR_CPF_CNPJ_DOADOR'))
                            k = (norm(r.get('NM_DOADOR')), doc[3:9]) if len(doc) == 11 else None
                            if (k and k in socios_midia) or MIDIA8(doc):
                                rec.append({'parl': sqs[r['SQ_CANDIDATO']], 'ano': ano, 'doador': r.get('NM_DOADOR'), 'doc_tipo': len(doc),
                                            'empresa_midia': socios_midia.get(k) if k else doc[:8], 'valor': r.get('VR_RECEITA'), 'fonte': r.get('DS_FONTE_RECEITA')})
        os.remove(z)
    salvar('campanha_despesas_midia.json', desp); salvar('campanha_doacoes_socios_midia.json', rec)
    log('despesas de campanha com mídia', len(desp), 'doações de sócios de mídia', len(rec))

def gabinetes():
    out = {}
    for k, p in PARL.items():
        if k[0] != 'C': continue
        try:
            h = requests.get(f'https://www.camara.leg.br/deputados/{k[1:]}/pessoal-gabinete?ano=2026', headers=UA, timeout=60).text
            nomes = [norm(re.sub('<[^>]+>', ' ', c)) for c in re.findall(r'<tr[^>]*>\s*<td[^>]*>(.*?)</td>', h, re.S)]
            out[k] = [n for n in nomes if len(n.split()) >= 2]
        except Exception as e:
            out[k] = {'erro': str(e)}
        time.sleep(0.3)
    salvar('gabinetes_camara.json', out)
    nomes_midia = collections.defaultdict(set)
    for b, ss in QSA.items():
        for s in ss:
            if s['tipo'] == '2': nomes_midia[norm(s['nome'])].add(b)
    cruz = [{'parl': k, 'nome': n, 'empresas': sorted(nomes_midia[n])} for k, ns in out.items() if isinstance(ns, list) for n in ns if n in nomes_midia]
    salvar('gabinetes_x_midia.json', cruz)
    log('deputados com gabinete lido', sum(1 for v in out.values() if isinstance(v, list) and v), 'coincidências', len(cruz))

etapa('outorgas do MCom', outorgas)
etapa('empresas com nome de mídia', empresas_nome)
etapa('estabelecimentos', estabelecimentos)
etapa('empresas', empresas)
etapa('sócios (base atual)', socios_atual)
etapa('cota parlamentar', ceap)
etapa('campanhas', campanhas)
etapa('gabinetes da Câmara', gabinetes)
etapa('sócios (base mais antiga)', socios_antigo)
log('fim')
