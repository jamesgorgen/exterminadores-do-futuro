"""PLP 299/2026, deputados federais: identificação no TSE, bens, empresas (CNPJ) e benefícios (DIRBI e ECF)."""
import csv, io, json, os, re, sys, zipfile, unicodedata, collections, xml.etree.ElementTree as ET
import requests
AQUI = os.path.dirname(os.path.abspath(__file__))
UA = {'user-agent': 'exterminadores-do-futuro (observatório; contato@exterminadores.com.br)'}
OUT = 'saida'
TSE = 'https://cdn.tse.jus.br/estatistica/sead/odsele'
RFB = 'https://arquivos.receitafederal.gov.br/public.php/webdav/Dados'
TOKEN = ('gn672Ad4CF8N6TK', '')
def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'[^A-Z ]', ' ', re.sub(r'\s+', ' ', s)).strip()
def baixar(url, destino, auth=None):
    if os.path.exists(destino): return destino
    with requests.get(url, headers=UA, auth=auth, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(destino, 'wb') as f:
            for b in r.iter_content(1 << 20): f.write(b)
    return destino

# Todos os deputados que exerceram mandato na 57ª legislatura
API = 'https://dadosabertos.camara.leg.br/api/v2'
deps, pag = [], 1
while True:
    j = requests.get(f'{API}/deputados', params={'idLegislatura': 57, 'itens': 100, 'pagina': pag}, headers={**UA, 'accept': 'application/json'}, timeout=60).json()
    deps += j['dados']
    if not any(l['rel'] == 'next' for l in j.get('links', [])): break
    pag += 1
deps = {str(d['id']): d for d in deps}
print('deputados na legislatura:', len(deps))
sen = {}
for i, d in deps.items():
    try:
        x = requests.get(f'{API}/deputados/{i}', headers={**UA, 'accept': 'application/json'}, timeout=60).json()['dados']
        sen[i] = {'codigo': i, 'nome': d['nome'], 'partido': d['siglaPartido'], 'uf': d['siglaUf'], 'nomeCompleto': x.get('nomeCivil'), 'cpf': x.get('cpf'), 'ex': x.get('ultimoStatus', {}).get('situacao')}
    except Exception as e:
        sen[i] = {'codigo': i, 'nome': d['nome'], 'partido': d['siglaPartido'], 'uf': d['siglaUf'], 'nomeCompleto': None, 'erro': str(e)}
print('com nome civil:', sum(1 for s in sen.values() if s.get('nomeCompleto')), 'com CPF na API:', sum(1 for s in sen.values() if s.get('cpf')))

cands = {}
z = baixar(f'{TSE}/consulta_cand/consulta_cand_2022.zip', '/tmp/cand2022.zip')
with zipfile.ZipFile(z) as zf:
    with zf.open([n for n in zf.namelist() if n.endswith('BRASIL.csv')][0]) as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding='latin-1'), delimiter=';'):
            if r['DS_CARGO'].upper() != 'DEPUTADO FEDERAL': continue
            cands.setdefault(norm(r['NM_CANDIDATO']), []).append({'ano': 2022, 'sq': r['SQ_CANDIDATO'], 'cpf': r.get('NR_CPF_CANDIDATO'), 'cargo': 'SENADOR', 'uf': r['SG_UF'], 'urna': r['NM_URNA_CANDIDATO']})
achados, faltam = {}, []
for c, s in sen.items():
    lst = [x for x in cands.get(norm(s.get('nomeCompleto')), []) if x['uf'] == s['uf']]
    if not lst and s.get('cpf'):
        lst = [x for xs in cands.values() for x in xs if re.sub(r'\D', '', x['cpf'] or '') == re.sub(r'\D', '', s['cpf'])]
    if s.get('cpf') and not lst:
        lst = [{'ano': 0, 'sq': '', 'cpf': s['cpf'], 'cargo': 'SENADOR', 'uf': s['uf'], 'urna': s['nome']}]
    if lst: achados[c] = {**s, 'tse': lst}
    else: faltam.append((c, s['nome'], s.get('nomeCompleto'), s['uf']))
print('deputados identificados:', len(achados), 'faltam:', len(faltam), faltam[:20])
sqs = {x['sq']: c for c, s in achados.items() for x in s['tse'] if x['sq']}
bens = []
z = baixar(f'{TSE}/bem_candidato/bem_candidato_2022.zip', '/tmp/bem2022.zip')
with zipfile.ZipFile(z) as zf:
    with zf.open([n for n in zf.namelist() if n.endswith('BRASIL.csv')][0]) as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding='latin-1'), delimiter=';'):
            if r['SQ_CANDIDATO'] in sqs:
                bens.append({'codigo': sqs[r['SQ_CANDIDATO']], 'ano': 2022, 'tipo': r['DS_TIPO_BEM_CANDIDATO'], 'desc': r['DS_BEM_CANDIDATO'], 'valor': r['VR_BEM_CANDIDATO']})
print('bens lidos:', len(bens))
json.dump({'deputados': achados, 'faltam': faltam}, open(f'{OUT}/deputados_tse.json', 'w'), ensure_ascii=False, indent=1)
json.dump(bens, open(f'{OUT}/bens_deputados.json', 'w'), ensure_ascii=False, indent=1)

# Mesma rotina de empresas e benefícios usada para os senadores
codigo = open(os.path.join(AQUI, 'plp299.py'), encoding='utf-8').read()
codigo = codigo.split("print('chaves nome+CPF:'")[0].split('import requests', 1)[1]
codigo = re.sub(r"exec\(open\(.*\n", '', codigo)
resto = open(os.path.join(AQUI, 'plp299.py'), encoding='utf-8').read().split("print('chaves nome+CPF:', len(chaves))", 1)[1]
resto = resto.replace("f'{OUT}/empresas.json'", "f'{OUT}/empresas_deputados.json'").replace("f'{OUT}/dirbi_setores.json'", "f'{OUT}/dirbi_setores_dep.json'")
exec(codigo + "print('chaves nome+CPF:', len(chaves))" + resto)
