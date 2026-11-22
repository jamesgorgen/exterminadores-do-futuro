"""Totais de uma bancada temática para um card, sem nomes (a saída desta análise é pública).

Lê no R2 privado o enquadramento (bancadas/bancadas.json) e as decisões da equipe (bancadas/decisoes.json).
Quem conta: decisão da equipe "nucleo" ou "aliado"; sem decisão, o enquadramento da regra, só nos casos que
não foram para a triagem. Cruza com o voto na votação escolhida e com o grupo político do site.
Variáveis: BANCADA (padrão plataformas) e VOTACAO (padrão C:2579791-17, urgência do PL 4675/2025).
"""
import json, os, subprocess, sys
from collections import Counter, defaultdict
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'boto3'], check=True)
import boto3

BAN = os.environ.get('BANCADA', 'plataformas')
VOT = os.environ.get('VOTACAO', 'C:2579791-17')
os.makedirs('saida', exist_ok=True)
s3 = boto3.client('s3', endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID'].strip()}.r2.cloudflarestorage.com",
                  aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'].strip(), aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'].strip(),
                  region_name='auto')
BUCKET = os.environ['R2_BUCKET']


def ler(k, padrao=None):
    try: return json.loads(s3.get_object(Bucket=BUCKET, Key=k)['Body'].read())
    except Exception as e:
        print('não li', k, type(e).__name__); return padrao


bj = ler('bancadas/bancadas.json', {})
dec = (ler('bancadas/decisoes.json', {}) or {}).get('decisoes', {}) or {}
indice = json.load(open('dados/indice.json'))['p']
voto_de = {}
import glob
for f in sorted(glob.glob('dados/votacoes-20*.json')):
    for v in json.load(open(f)).get('itens', []):
        if v.get('id') == VOT:
            for op, ids in v.get('v', {}).items():
                for i in ids: voto_de[v['k'] + str(i)] = op
            print('votação:', VOT, v.get('d'), v.get('mat'), (v.get('desc') or '')[:80])

# Decisões da equipe sobre quem já não aparece no enquadramento atual (a regra deixou de apontar a pessoa).
sem_entrada = Counter(d.get('d') for kk, d in dec.items() if kk.endswith('|' + BAN) and not (((bj.get('p') or {}).get(kk.split('|')[0]) or {}).get('b') or {}).get(BAN))
print('decisões sem entrada no enquadramento atual:', dict(sem_entrada))
membros, pend, por_dec, por_regra = {}, 0, 0, 0
for kk, d in dec.items():
    k, b = kk.split('|', 1)
    if b == BAN and d.get('d') in ('nucleo', 'aliado') and not (((bj.get('p') or {}).get(k) or {}).get('b') or {}).get(BAN):
        membros[k] = d['d']; por_dec += 1
cats_equipe = Counter()
for k, p in (bj.get('p') or {}).items():
    x = (p.get('b') or {}).get(BAN)
    if not x: continue
    d = dec.get(f'{k}|{BAN}')
    if d:
        cats_equipe[d.get('d')] += 1
        if d.get('d') in ('nucleo', 'aliado'): membros[k] = d['d']; por_dec += 1
    elif not x.get('t'):
        if x.get('cat') in ('nucleo', 'aliado'): membros[k] = x['cat']; por_regra += 1
    else:
        pend += 1

res = {'decisoes_sem_entrada_atual': dict(sem_entrada), 'bancada': BAN, 'votacao': VOT, 'gerado': bj.get('gerado'),
       'decisoes_da_equipe': dict(cats_equipe), 'pendentes_de_triagem': pend,
       'membros': {'total': len(membros), 'por_decisao_da_equipe': por_dec, 'pela_regra_sem_triagem': por_regra,
                   'por_categoria': dict(Counter(membros.values())),
                   'por_casa': dict(Counter(k[0] for k in membros))}}
VOTO = {'S': 'sim', 'N': 'não', 'A': 'abstenção', 'O': 'obstrução', '-': 'presente sem voto'}
cat_voto, grupo_voto = defaultdict(Counter), defaultdict(Counter)
for k, c in membros.items():
    if k[0] != VOT[0]: continue
    vv = VOTO.get(voto_de.get(k), 'sem voto registrado')
    g = (indice.get(k) or {}).get('cl') or 'sem grupo'
    cat_voto[c][vv] += 1; grupo_voto[g][vv] += 1
res['deputados_na_votacao'] = {'por_categoria': {c: dict(n) for c, n in cat_voto.items()}, 'por_grupo': {g: dict(n) for g, n in grupo_voto.items()}}
al = (bj.get('alinhados') or {}).get(BAN) or []
res['alinhados_sem_pertencer'] = {'total': len(al), 'por_casa': dict(Counter(x.get('c') for x in al)), 'por_grupo': dict(Counter(x.get('g') or 'sem grupo' for x in al)),
                                  'voto_na_votacao': dict(Counter(VOTO.get(voto_de.get(x['k']), 'sem voto registrado') for x in al if x['k'][0] == VOT[0]))}
txt = json.dumps(res, ensure_ascii=False, indent=1)
print(txt)
open('saida/resultado.json', 'w').write(txt + '\n')
