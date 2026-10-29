# Baixa a população dos municípios do Censo 2022 (IBGE, agregado 4714) e grava dados/populacao-municipios.json.
import json, os, urllib.request
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = 'https://servicodados.ibge.gov.br/api/v3/agregados/4714/periodos/2022/variaveis/93?localidades=N6[all]'
req = urllib.request.Request(URL, headers={'User-Agent': 'observatorio exterminadores-do-futuro'})
with urllib.request.urlopen(req, timeout=180) as r:
    j = json.load(r)
pop = {}
for s in j[0]['resultados'][0]['series']:
    v = s['serie'].get('2022')
    if v and v.isdigit():
        pop[s['localidade']['id']] = int(v)
if len(pop) < 5000:
    raise SystemExit(f'poucos municípios na resposta: {len(pop)}')
json.dump({'fonte': 'IBGE, Censo 2022, agregado 4714', 'pop': pop}, open(os.path.join(RAIZ, 'dados', 'populacao-municipios.json'), 'w'), separators=(',', ':'))
print('municípios', len(pop))
