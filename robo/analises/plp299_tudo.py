"""PLP 299/2026: senadores e deputados, empresas (CNPJ), atividade (CNAE) e benefícios (DIRBI e ECF), numa só passada.
Publica a saída parcial no ramo analises-saida-plp299_tudo ao fim de cada etapa."""
import csv, io, json, os, re, subprocess, time, zipfile, collections, xml.etree.ElementTree as ET
import requests
AQUI = os.path.dirname(os.path.abspath(__file__))
T0 = time.time()

def publicar(etapa):
    print(f'[{(time.time()-T0)/60:.0f} min] {etapa}', flush=True)
    if not os.environ.get('TOKEN_GH'): return
    cmd = f'''cd saida && rm -rf .git && git init -q -b analises-saida-plp299_tudo && git add -A &&
      git -c user.name=robo -c user.email=robo@users.noreply.github.com commit -qm "{etapa}" &&
      git push -qf "https://x-access-token:$TOKEN_GH@github.com/$REPO.git" analises-saida-plp299_tudo'''
    subprocess.run(cmd, shell=True)

# Senadores (etapa 1) e deputados
exec(open(os.path.join(AQUI, 'plp299_etapa1.py'), encoding='utf-8').read().split('# Estrutura das bases da Receita')[0])
ach_s = {'S' + c: s for c, s in achados.items()}
exec(open(os.path.join(AQUI, 'plp299_deputados.py'), encoding='utf-8').read().split('# Mesma rotina')[0].split('import requests', 1)[1])
ach_d = {'C' + c: s for c, s in achados.items()}
TODOS = {**ach_s, **ach_d}
publicar('parlamentares e bens')

def listar(caminho):
    r = requests.request('PROPFIND', f'{RFB}/{caminho}', headers={**UA, 'Depth': '1'}, auth=TOKEN, timeout=120)
    return [h.text for h in ET.fromstring(r.content).iter('{DAV:}href')]
def num(v):
    try: return float(str(v).replace('.', '').replace(',', '.')) if v not in (None, '') else 0.0
    except ValueError: return 0.0

chaves = {}
for c, s in TODOS.items():
    for t in s['tse']:
        cpf = re.sub(r'\D', '', t.get('cpf') or '')
        if len(cpf) == 11 and s.get('nomeCompleto'):
            chaves[(norm(s['nomeCompleto']), cpf[3:9])] = c
print('chaves nome+CPF:', len(chaves))
mes = sorted(h.rstrip('/').split('/')[-1] for h in listar('Cadastros/CNPJ/') if re.search(r'\d{4}-\d{2}/?$', h))[-1]

def ler_zip_rfb(nome, tratar):
    z = baixar(f'{RFB}/Cadastros/CNPJ/{mes}/{nome}', f'/tmp/{nome}', TOKEN)
    with zipfile.ZipFile(z) as zf:
        for n in zf.namelist():
            with zf.open(n) as f:
                for r in csv.reader(io.TextIOWrapper(f, encoding='latin-1', errors='ignore'), delimiter=';'):
                    tratar(r)
    os.remove(z)

socios = []
def t_soc(r):
    if len(r) > 5 and r[1] == '2':
        k = (norm(r[2]), r[3].strip('*'))
        if k in chaves: socios.append({'codigo': chaves[k], 'cnpj': r[0], 'qualif': r[4], 'entrada': r[5]})
for i in range(10): ler_zip_rfb(f'Socios{i}.zip', t_soc)
basicos = {x['cnpj'] for x in socios}
json.dump({'mes_cnpj': mes, 'socios': socios}, open(f'{OUT}/socios.json', 'w'), ensure_ascii=False)
publicar(f'sócios: {len(socios)} vínculos, {len(basicos)} empresas')

emp = {}
def t_emp(r):
    if r[0] in basicos: emp[r[0]] = {'razao': r[1], 'natureza': r[2], 'capital': num(r[4]), 'porte': r[5]}
for i in range(10): ler_zip_rfb(f'Empresas{i}.zip', t_emp)
json.dump(emp, open(f'{OUT}/empresas.json', 'w'), ensure_ascii=False)
publicar('empresas')

# Atividade e situação da matriz pela consulta pública de CNPJ (evita baixar 5 GB de estabelecimentos)
def dv(b12):
    def d(s, pesos): r = sum(int(a) * p for a, p in zip(s, pesos)) % 11; return '0' if r < 2 else str(11 - r)
    d1 = d(b12, [5,4,3,2,9,8,7,6,5,4,3,2]); d2 = d(b12 + d1, [6,5,4,3,2,9,8,7,6,5,4,3,2]); return b12 + d1 + d2
cad = {}
for n, b in enumerate(sorted(basicos)):
    cnpj = dv(b + '0001')
    for url in (f'https://minhareceita.org/{cnpj}', f'https://brasilapi.com.br/api/cnpj/v1/{cnpj}'):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 200:
                j = r.json(); cad[b] = {'cnpj': cnpj, 'cnae': str(j.get('cnae_fiscal') or ''), 'cnae_desc': j.get('cnae_fiscal_descricao'),
                    'situacao': j.get('descricao_situacao_cadastral'), 'uf': j.get('uf'), 'municipio': j.get('municipio'), 'regime': j.get('regime_tributario') or j.get('opcao_pelo_simples')}
                break
        except Exception: pass
        time.sleep(0.4)
    if n % 200 == 0: print('  cadastro', n, len(basicos), flush=True)
json.dump(cad, open(f'{OUT}/cadastro.json', 'w'), ensure_ascii=False)
publicar(f'cadastro: {len(cad)} de {len(basicos)}')

dirbi_emp = collections.defaultdict(float); setor = collections.defaultdict(float); codigo = collections.defaultdict(float); setor_cod = collections.defaultdict(float)
for ano in (2024, 2025, 2026):
    try: z = baixar(f'{RFB}/Obrigacoes_Acessorias/DIRBI/renuncia-por-regime-{ano}.zip', f'/tmp/dirbi{ano}.zip', TOKEN)
    except Exception as e: print('DIRBI', ano, e); continue
    with zipfile.ZipFile(z) as zf:
        with zf.open(zf.namelist()[0]) as f:
            for r in csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig', errors='ignore')):
                v = num(r.get('Valor')); b = re.sub(r'\D', '', r.get('CNPJ', ''))[:8]
                cn = (r.get('Cnae') or '').zfill(7)[:2]; cod = r.get('Código_IN') or r.get('Codigo_IN') or ''
                setor[(ano, cn)] += v; codigo[(ano, cod)] += v; setor_cod[(ano, cn, cod)] += v
                if b in basicos: dirbi_emp[(b, ano, cod, r.get('Tributo'), (r.get('Cnae') or ''))] += v
    os.remove(z)
json.dump({'dirbi': [[*k, round(v, 2)] for k, v in dirbi_emp.items()]}, open(f'{OUT}/dirbi_empresas.json', 'w'), ensure_ascii=False)
json.dump({'setor': [[*k, round(v, 2)] for k, v in setor.items()], 'codigo': [[*k, round(v, 2)] for k, v in codigo.items()],
           'setor_cod': [[*k, round(v, 2)] for k, v in setor_cod.items() if v > 1e6]}, open(f'{OUT}/dirbi_setores.json', 'w'), ensure_ascii=False)
publicar(f'DIRBI: {len(dirbi_emp)} linhas de empresas de parlamentares')

ecf = []
r = requests.get(f'{RFB}/Obrigacoes_Acessorias/ECF/renuncia-irpj-csll-ecf.csv', headers=UA, auth=TOKEN, stream=True, timeout=1200)
linhas = (l.decode('utf-8', 'ignore') for l in r.iter_lines())
cab = next(linhas).lstrip('﻿').split('|')
for l in linhas:
    p = l.split('|')
    if re.sub(r'\D', '', p[0])[:8] in basicos:
        d = dict(zip(cab, p))
        ecf.append({'cnpj': p[0], 'razao': d.get('razao_social'), 'ano': p[-1], 'forma': d.get('forma_trib'), 'cnae': d.get('cnae'),
                    'itens': {k: num(d[k]) for k in cab[11:] if k in d and not k.startswith('ano') and num(d[k]) > 0}})
json.dump(ecf, open(f'{OUT}/ecf.json', 'w'), ensure_ascii=False)
publicar(f'ECF: {len(ecf)} declarações; concluído')
