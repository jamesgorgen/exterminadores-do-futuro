"""Gabinetes do Senado x sócios de empresas de mídia.
Baixa os servidores ativos (comissionados e efetivos) do Senado, separa os lotados em gabinetes de senadores,
associa cada gabinete ao senador e compara os nomes com os sócios das empresas de mídia (saída de midia3.py).
A comparação é só por nome (o Senado não publica CPF), então cada coincidência é um indício a verificar.
Saída no ramo analises-saida-midia_senado."""
import json, os, re, gzip, subprocess, unicodedata, collections, time
import requests
UA = {'user-agent': 'exterminadores-do-futuro (observatório; contato@exterminadores.com.br)'}
OUT = 'saida'; os.makedirs(OUT, exist_ok=True)
def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z ]', ' ', s)).strip()

# Saída da análise de mídia
subprocess.run('git fetch -q --depth 1 origin analises-saida-midia3', shell=True, check=True)
def doramo(n):
    b = subprocess.run(f'git show FETCH_HEAD:{n}', shell=True, capture_output=True).stdout
    return json.loads(gzip.decompress(b) if n.endswith('.gz') else b)
QSA = doramo('qsa.json.gz'); U = doramo('universo.json.gz'); PARL = doramo('parlamentares.json')
SEN = {k: p for k, p in PARL.items() if k[0] == 'S'}
print('empresas com sócios', len(QSA), 'senadores', len(SEN), flush=True)

# Servidores do Senado
BASE = 'https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores/servidores'
servidores = []
for sit in ('comissionados', 'efetivos'):
    for t in range(3):
        try:
            r = requests.get(f'{BASE}/{sit}', headers={**UA, 'accept': 'application/json'}, timeout=300)
            r.raise_for_status(); j = r.json()
            lst = j if isinstance(j, list) else next((v for v in j.values() if isinstance(v, list)), [])
            servidores += [{**x, '_sit': sit} for x in lst]
            print(sit, len(lst), flush=True); break
        except Exception as e:
            print('falha', sit, e, flush=True); time.sleep(20)

def lot(x):
    l = x.get('lotacao') or {}
    return (l.get('sigla') or '', l.get('nome') or '') if isinstance(l, dict) else ('', str(l))
gab = [x for x in servidores if re.search(r'GABINETE D[OA] SENADOR', norm(lot(x)[1]))]
print('lotados em gabinetes de senadores', len(gab), flush=True)

# Gabinete -> senador, pelo nome parlamentar no nome da lotação
nomes_sen = {k: norm(p.get('nome')) for k, p in SEN.items() if p.get('nome')}
def senador_do_gabinete(nome_lot):
    n = re.sub(r'^.*GABINETE D[OA] SENADORA? ', '', norm(nome_lot)).strip()
    exato = [k for k, s in nomes_sen.items() if s == n]
    if exato: return exato[0]
    parcial = [k for k, s in nomes_sen.items() if s and (s in n or n in s)]
    return parcial[0] if len(parcial) == 1 else None
mapa = {}
for x in gab:
    sig, nome = lot(x)
    if nome not in mapa: mapa[nome] = senador_do_gabinete(nome)
sem = sorted(n for n, k in mapa.items() if not k)
print('gabinetes', len(mapa), 'sem senador identificado', len(sem), sem[:20], flush=True)

# Sócios de mídia por nome
socios = collections.defaultdict(list)
for b, ss in QSA.items():
    if b not in U: continue
    for s in ss:
        if s.get('tipo') == '2': socios[norm(s['nome'])].append({'cnpj': b, 'qualif': s.get('qualif'), 'entrada': s.get('entrada')})
cruz = []
for x in gab:
    k = mapa.get(lot(x)[1])
    n = norm(x.get('nome'))
    if not k or len(n.split()) < 3 or n not in socios: continue
    uf = SEN[k].get('uf')
    for e in socios[n]:
        ufs = {est.get('uf') for est in U[e['cnpj']].get('estab', [])}
        cruz.append({'parl': k, 'senador': SEN[k].get('nome'), 'nome': x.get('nome'), 'cargo': (x.get('cargo') or {}).get('nome') if isinstance(x.get('cargo'), dict) else x.get('cargo'),
                     'lotacao': lot(x)[1], 'vinculo': x.get('_sit'), 'cnpj': e['cnpj'], 'razao': U[e['cnpj']].get('razao'), 'mesma_uf': uf in ufs, **e})
json.dump({'gabinetes': mapa, 'servidores_em_gabinete': len(gab)}, open(f'{OUT}/gabinetes_senado.json', 'w'), ensure_ascii=False)
json.dump(cruz, open(f'{OUT}/gabinetes_senado_x_midia.json', 'w'), ensure_ascii=False, indent=1)
print('coincidências', len(cruz), 'na mesma UF', sum(1 for c in cruz if c['mesma_uf']), flush=True)
