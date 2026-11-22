"""Quem votou de um jeito numa votação e que sinal tem numa bancada. Só contagens, sem nomes (a saída é pública).

Para cada deputado com o voto escolhido (padrão: "não" na urgência do PL 4675/2025), diz a situação na bancada:
membro (núcleo ou aliado pela equipe), retirado pela equipe, sinal fraco da regra (interesse, dúvida) ou nenhum sinal.
Também lista as ocupações do TSE ligadas a tecnologia e comunicação digital, para conferir se servem de critério.
Variáveis: BANCADA, VOTACAO, VOTO.
"""
import csv, glob, io, json, os, re, subprocess, sys, unicodedata, zipfile
from collections import Counter, defaultdict
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'boto3'], check=True)
import boto3

BAN = os.environ.get('BANCADA', 'plataformas')
VOT = os.environ.get('VOTACAO', 'C:2579791-17')
VOTO = os.environ.get('VOTO', 'N')
os.makedirs('saida', exist_ok=True)
s3 = boto3.client('s3', endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID'].strip()}.r2.cloudflarestorage.com",
                  aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'].strip(), aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'].strip(),
                  region_name='auto')
BUCKET = os.environ['R2_BUCKET']
norm = lambda s: unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().upper()


def ler(k, padrao=None):
    try: return json.loads(s3.get_object(Bucket=BUCKET, Key=k)['Body'].read())
    except Exception as e:
        print('não li', k, type(e).__name__); return padrao


bj = ler('bancadas/bancadas.json', {}) or {}
dec = (ler('bancadas/decisoes.json', {}) or {}).get('decisoes', {}) or {}
indice = json.load(open('dados/indice.json'))['p']
alvo = []
for f in sorted(glob.glob('dados/votacoes-20*.json')):
    for v in json.load(open(f)).get('itens', []):
        if v.get('id') == VOT: alvo = [v['k'] + str(i) for i in v.get('v', {}).get(VOTO, [])]
print('votação', VOT, 'voto', VOTO, 'deputados:', len(alvo))

sit, por_grupo, evid = Counter(), defaultdict(Counter), Counter()
for k in alvo:
    x = ((bj.get('p') or {}).get(k) or {}).get('b', {}).get(BAN)
    d = dec.get(f'{k}|{BAN}')
    if d: s = {'nucleo': 'membro (núcleo)', 'aliado': 'membro (aliado)', 'fora': 'retirado pela equipe', 'incerto': 'incerto pela equipe'}.get(d.get('d'), 'decisão ' + str(d.get('d')))
    elif x: s = f"sinal da regra sem triagem: {x.get('cat')}"
    else: s = 'nenhum sinal na bancada'
    sit[s] += 1
    por_grupo[(indice.get(k) or {}).get('cl') or 'sem grupo'][s] += 1
    if x and not (d and d.get('d') in ('nucleo', 'aliado')):
        for e in x.get('ev', []):
            if len(e) > 2: evid[f"{e[0]} · {e[2]}"] += 1

# Ocupações do TSE (todas as candidaturas a deputado federal e senador) com termos de tecnologia e comunicação digital.
TERMOS = re.compile(r'DIGITAL|INTERNET|INFORMATIC|TECNOLOG|PROGRAMAD|SOFTWARE|SISTEMAS|COMPUTA|PUBLICIT|MARKETING|INFLUENC|CONTEUDO|YOUTUB|BLOG|WEB|ANALISTA DE SIST|COMUNICA|LOCUTOR|APRESENTADOR|JORNALIST|RADIALIST')
ocup = Counter(); todas = set()
for ano in (2022, 2026):
    try: corpo = s3.get_object(Bucket=BUCKET, Key=f'tse/consulta_cand_{ano}.zip')['Body'].read()
    except Exception as e: print('sem consulta_cand', ano, e); continue
    with zipfile.ZipFile(io.BytesIO(corpo)) as z:
        nomes = [n for n in z.namelist() if n.endswith('.csv')]
        for n in ([n for n in nomes if 'BRASIL' in n.upper()] or nomes):
            with z.open(n) as f:
                for r in csv.DictReader(io.TextIOWrapper(f, encoding='latin-1', errors='ignore'), delimiter=';'):
                    if norm(r.get('DS_CARGO')) not in ('DEPUTADO FEDERAL', 'SENADOR'): continue
                    o = norm(r.get('DS_OCUPACAO')); todas.add(o)
                    if TERMOS.search(o): ocup[f'{ano} · {o}'] += 1

res = {'bancada': BAN, 'votacao': VOT, 'voto': VOTO, 'total': len(alvo), 'situacao': dict(sit.most_common()),
       'situacao_por_grupo': {g: dict(c.most_common()) for g, c in por_grupo.items()},
       'evidencias_de_quem_nao_e_membro': dict(evid.most_common(30)),
       'ocupacoes_tse_tecnologia_comunicacao': dict(sorted(ocup.items())), 'ocupacoes_distintas_no_tse': len(todas)}
txt = json.dumps(res, ensure_ascii=False, indent=1)
print(txt)
open('saida/resultado.json', 'w').write(txt + '\n')
