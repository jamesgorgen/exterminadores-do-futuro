"""PLP 299/2026, etapa 2: empresas dos senadores (CNPJ), benefícios declarados (DIRBI e ECF) e setores."""
import csv, io, json, os, re, zipfile, collections, xml.etree.ElementTree as ET
import requests
AQUI = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(AQUI, 'plp299_etapa1.py'), encoding='utf-8').read().split('# Estrutura das bases da Receita')[0])

def listar(caminho):
    r = requests.request('PROPFIND', f'{RFB}/{caminho}', headers={**UA, 'Depth': '1'}, auth=TOKEN, timeout=120)
    return [h.text for h in ET.fromstring(r.content).iter('{DAV:}href')]

def num(v):
    try: return float(str(v).replace('.', '').replace(',', '.')) if v not in (None, '') else 0.0
    except ValueError: return 0.0

# Chave de cada senador para os sócios: nome civil + seis dígitos centrais do CPF
chaves = {}
for c, s in achados.items():
    for t in s['tse']:
        cpf = re.sub(r'\D', '', t.get('cpf') or '')
        if len(cpf) == 11 and t['cargo'].upper() == 'SENADOR' or (len(cpf) == 11 and norm(s.get('nomeCompleto')) and True):
            chaves[(norm(s['nomeCompleto']), cpf[3:9])] = c
print('chaves nome+CPF:', len(chaves))

meses = sorted(h.rstrip('/').split('/')[-1] for h in listar('Cadastros/CNPJ/') if re.search(r'\d{4}-\d{2}/?$', h))
mes = meses[-1]; print('CNPJ, mês', mes)

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
    if len(r) > 3 and r[1] == '2' and (norm(r[2]), r[3].strip('*')) in chaves:
        socios.append({'codigo': chaves[(norm(r[2]), r[3].strip('*'))], 'cnpj': r[0], 'qualif': r[4], 'entrada': r[5]})
for i in range(10): ler_zip_rfb(f'Socios{i}.zip', t_soc)
print('vínculos societários:', len(socios))
basicos = {x['cnpj'] for x in socios}

emp, est = {}, collections.defaultdict(list)
def t_emp(r):
    if r[0] in basicos: emp[r[0]] = {'razao': r[1], 'natureza': r[2], 'capital': num(r[4]), 'porte': r[5]}
def t_est(r):
    if r[0] in basicos: est[r[0]].append({'cnpj': r[0] + r[1] + r[2], 'matriz': r[3] == '1', 'fantasia': r[4], 'situacao': r[5], 'cnae': r[11], 'uf': r[19] if len(r) > 19 else '', 'mun': r[20] if len(r) > 20 else ''})
for i in range(10): ler_zip_rfb(f'Empresas{i}.zip', t_emp)
for i in range(10): ler_zip_rfb(f'Estabelecimentos{i}.zip', t_est)

# DIRBI: benefícios declarados mês a mês, por empresa e por setor (divisão CNAE) e código do benefício
dirbi_emp = collections.defaultdict(float)
setor = collections.defaultdict(float); codigo = collections.defaultdict(float); setor_cod = collections.defaultdict(float)
for ano in (2024, 2025, 2026):
    try: z = baixar(f'{RFB}/Obrigacoes_Acessorias/DIRBI/renuncia-por-regime-{ano}.zip', f'/tmp/dirbi{ano}.zip', TOKEN)
    except Exception as e: print('DIRBI', ano, e); continue
    with zipfile.ZipFile(z) as zf:
        with zf.open(zf.namelist()[0]) as f:
            for r in csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig', errors='ignore')):
                v = num(r.get('Valor')); b = re.sub(r'\D', '', r.get('CNPJ', ''))[:8]
                cn = (r.get('Cnae') or '').zfill(7)[:2]; cod = r.get('Código_IN') or r.get('Codigo_IN') or ''
                setor[(ano, cn)] += v; codigo[(ano, cod)] += v; setor_cod[(ano, cn, cod)] += v
                if b in basicos: dirbi_emp[(b, ano, cod, r.get('Tributo'))] += v
print('linhas DIRBI de empresas dos senadores:', len(dirbi_emp))

# ECF: renúncias de IRPJ e CSLL e forma de tributação das empresas dos senadores
ecf = []
r = requests.get(f'{RFB}/Obrigacoes_Acessorias/ECF/renuncia-irpj-csll-ecf.csv', headers=UA, auth=TOKEN, stream=True, timeout=1200)
linhas = (l.decode('utf-8', 'ignore') for l in r.iter_lines())
cab = next(linhas).lstrip('﻿').split('|')
for l in linhas:
    p = l.split('|')
    if re.sub(r'\D', '', p[0])[:8] in basicos:
        d = dict(zip(cab, p)); tot = sum(num(d[k]) for k in cab[11:] if k not in ('ano', 'ano_calendario'))
        ecf.append({'cnpj': p[0], 'razao': d['razao_social'], 'ano': p[-1], 'forma': d['forma_trib'], 'cnae': d['cnae'], 'total': tot,
                    'itens': {k: num(d[k]) for k in cab[11:] if num(d[k]) > 0 and not k.startswith('ano')}})
print('declarações ECF das empresas dos senadores:', len(ecf))

# Listas de lucro presumido e real
regime = {}
for nome in ('entidades-lucro-presumido.zip', 'entidades-lucro-real.zip'):
    try:
        z = baixar(f'{RFB}/Obrigacoes_Acessorias/ECF/{nome}', f'/tmp/{nome}', TOKEN)
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                with zf.open(n) as f:
                    cabec = None
                    for i, l in enumerate(io.TextIOWrapper(f, encoding='utf-8-sig', errors='ignore')):
                        if i == 0: print(nome, n, 'cabeçalho:', l.strip()[:200])
                        b = re.sub(r'\D', '', l.split(';')[0].split(',')[0].split('|')[0])[:8]
                        if b in basicos: regime.setdefault(b, []).append((nome.split('-')[-1][:-4], l.strip()[:200]))
    except Exception as e: print(nome, e)

json.dump({'mes_cnpj': mes, 'socios': socios, 'empresas': emp, 'estabelecimentos': est, 'regime': regime,
           'dirbi': [[*k, round(v, 2)] for k, v in dirbi_emp.items()], 'ecf': ecf}, open(f'{OUT}/empresas.json', 'w'), ensure_ascii=False, indent=1)
json.dump({'setor': [[*k, round(v, 2)] for k, v in setor.items()], 'codigo': [[*k, round(v, 2)] for k, v in codigo.items()],
           'setor_cod': [[*k, round(v, 2)] for k, v in setor_cod.items() if v > 1e6]}, open(f'{OUT}/dirbi_setores.json', 'w'), ensure_ascii=False)
print('concluído')
