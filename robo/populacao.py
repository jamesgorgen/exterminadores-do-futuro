# Baixa a população dos municípios do Censo 2022 (IBGE, agregado 4714) e grava dados/populacao-municipios.json.
# Consulta estado por estado, porque a consulta única de todo o país costuma falhar.
import json, os, time, urllib.request
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UFS = [11,12,13,14,15,16,17,21,22,23,24,25,26,27,28,29,31,32,33,35,41,42,43,50,51,52,53]
BASES = ['https://servicodados.ibge.gov.br/api/v3/agregados/4714/periodos/2022/variaveis/93?localidades=N6[N3[{uf}]]',
         'https://apisidra.ibge.gov.br/values/t/4714/n6/in%20n3%20{uf}/v/93/p/2022']
def baixar(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (observatorio exterminadores-do-futuro)', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)
pop = {}
for uf in UFS:
    ok = False
    for tent in range(3):
        for i, base in enumerate(BASES):
            try:
                j = baixar(base.format(uf=uf))
                if i == 0:
                    for s in j[0]['resultados'][0]['series']:
                        v = s['serie'].get('2022')
                        if v and v.isdigit(): pop[s['localidade']['id']] = int(v)
                else:
                    for row in j[1:]:
                        if str(row.get('V', '')).isdigit(): pop[row['D1C']] = int(row['V'])
                ok = True; break
            except Exception as e:
                print('falha', uf, i, e)
        if ok: break
        time.sleep(5 * (tent + 1))
    print(uf, 'ok' if ok else 'FALHOU', len(pop))
if len(pop) < 5000:
    raise SystemExit(f'poucos municípios: {len(pop)}')
json.dump({'fonte': 'IBGE, Censo 2022, tabela 4714', 'pop': pop}, open(os.path.join(RAIZ, 'dados', 'populacao-municipios.json'), 'w'), separators=(',', ':'))
print('municípios', len(pop))
