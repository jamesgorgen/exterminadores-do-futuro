"""PLP 299/2026, etapa 1: identifica os senadores no TSE (CPF e bens declarados) e examina as bases da Receita."""
import csv, io, json, os, re, sys, zipfile, unicodedata
import requests

UA = {'user-agent': 'exterminadores-do-futuro (observatório; contato@exterminadores.com.br)'}
OUT = 'saida'
AQUI = os.path.dirname(os.path.abspath(__file__))
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

votos = list(csv.DictReader(open(os.path.join(AQUI, 'plp299_votos.csv'), encoding='utf-8'), delimiter=';'))

# Nome civil de cada senador pela API do Senado
sen = {}
for v in votos:
    try:
        j = requests.get(f"https://legis.senado.leg.br/dadosabertos/senador/{v['codigo']}.json", headers=UA, timeout=60).json()
        idp = j['DetalheParlamentar']['Parlamentar']['IdentificacaoParlamentar']
        dados = j['DetalheParlamentar']['Parlamentar'].get('DadosBasicosParlamentar', {})
        sen[v['codigo']] = {'nomeCompleto': idp.get('NomeCompletoParlamentar'), 'nasc': dados.get('DataNascimento'), **v}
    except Exception as e:
        sen[v['codigo']] = {'nomeCompleto': None, 'erro': str(e), **v}
print('senadores com nome civil:', sum(1 for s in sen.values() if s.get('nomeCompleto')))

# Candidatos do TSE: senadores e suplentes de 2018 e 2022
cands = {}
for ano in (2018, 2022):
    z = baixar(f'{TSE}/consulta_cand/consulta_cand_{ano}.zip', f'/tmp/cand{ano}.zip')
    with zipfile.ZipFile(z) as zf:
        nome = [n for n in zf.namelist() if n.endswith('BRASIL.csv')][0]
        with zf.open(nome) as f:
            for r in csv.DictReader(io.TextIOWrapper(f, encoding='latin-1'), delimiter=';'):
                if r['DS_CARGO'].upper() not in ('SENADOR', '1º SUPLENTE', '2º SUPLENTE'): continue
                cands.setdefault(norm(r['NM_CANDIDATO']), []).append({'ano': ano, 'sq': r['SQ_CANDIDATO'], 'cpf': r.get('NR_CPF_CANDIDATO'), 'cargo': r['DS_CARGO'], 'uf': r['SG_UF'], 'nasc': r.get('DT_NASCIMENTO'), 'urna': r['NM_URNA_CANDIDATO'], 'sit': r.get('DS_SIT_TOT_TURNO'), 'ocup': r.get('DS_OCUPACAO')})
print('candidatos ao Senado e suplentes lidos:', sum(len(v) for v in cands.values()))

achados, faltam = {}, []
for c, s in sen.items():
    alvo = norm(s.get('nomeCompleto'))
    lst = [x for x in cands.get(alvo, []) if x['uf'] == s['uf']]
    if not lst:
        urna = norm(s['nome'])
        lst = [x for n, xs in cands.items() for x in xs if x['uf'] == s['uf'] and norm(x['urna']) == urna]
    if lst:
        achados[c] = {**s, 'tse': lst}
    else:
        faltam.append((c, s['nome'], s.get('nomeCompleto'), s['uf']))
print('senadores encontrados no TSE:', len(achados), 'faltam:', faltam)

# Bens declarados
sqs = {x['sq']: c for c, s in achados.items() for x in s['tse']}
bens = []
for ano in (2018, 2022):
    z = baixar(f'{TSE}/bem_candidato/bem_candidato_{ano}.zip', f'/tmp/bem{ano}.zip')
    with zipfile.ZipFile(z) as zf:
        nome = [n for n in zf.namelist() if n.endswith('BRASIL.csv')][0]
        with zf.open(nome) as f:
            for r in csv.DictReader(io.TextIOWrapper(f, encoding='latin-1'), delimiter=';'):
                if r['SQ_CANDIDATO'] in sqs:
                    bens.append({'codigo': sqs[r['SQ_CANDIDATO']], 'ano': ano, 'tipo': r['DS_TIPO_BEM_CANDIDATO'], 'desc': r['DS_BEM_CANDIDATO'], 'valor': r['VR_BEM_CANDIDATO']})
print('bens lidos:', len(bens))
json.dump({'senadores': achados, 'faltam': faltam}, open(f'{OUT}/senadores_tse.json', 'w'), ensure_ascii=False, indent=1)
json.dump(bens, open(f'{OUT}/bens.json', 'w'), ensure_ascii=False, indent=1)

# Estrutura das bases da Receita
for caminho in ['Obrigacoes_Acessorias/DIRBI/renuncia-por-regime-dicionario.csv', 'Obrigacoes_Acessorias/ECF/renuncia-irpj-csll-ecf-dicionario.csv']:
    r = requests.get(f'{RFB}/{caminho}', headers=UA, auth=TOKEN, timeout=120)
    print('====', caminho, r.status_code); print(r.content.decode('utf-8', 'ignore')[:4000])
z = baixar(f'{RFB}/Obrigacoes_Acessorias/DIRBI/renuncia-por-regime-2025.zip', '/tmp/dirbi2025.zip', TOKEN)
with zipfile.ZipFile(z) as zf:
    print('==== conteúdo do zip DIRBI 2025', zf.namelist())
    with zf.open(zf.namelist()[0]) as f:
        for i, linha in enumerate(io.TextIOWrapper(f, encoding='utf-8', errors='ignore')):
            print(linha.rstrip()[:400])
            if i >= 5: break
r = requests.get(f'{RFB}/Obrigacoes_Acessorias/ECF/renuncia-irpj-csll-ecf.csv', headers={**UA, 'Range': 'bytes=0-2000'}, auth=TOKEN, timeout=120)
print('==== ECF renúncia, início'); print(r.content.decode('utf-8', 'ignore')[:2000])
