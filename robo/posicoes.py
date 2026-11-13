"""Posição de cada parlamentar estimada pelas votações nominais (pontos ideais).

Modelo em duas dimensões, ajustado por máxima verossimilhança com penalização, separadamente em cada Casa,
sobre as votações em que a minoria teve pelo menos 2,5% dos votos. Entram parlamentares com pelo menos 25 votos sim ou não.
A primeira dimensão é orientada com o PL à direita e normalizada para que 95% dos parlamentares fiquem entre -1 e 1.
Os cortes entre os quatro grupos vêm de um agrupamento (k-médias) dos parlamentares em exercício, iniciado
pelos cortes da semana anterior para que a fronteira não oscile sem motivo.

Grava dados/posicoes.json. Não usa IA. Roda toda semana (workflow "Posições pelas votações").
Referência: Zucco e Lauderdale (2011), Distinguishing between influences on Brazilian legislative behavior.
"""
import datetime
import json
import os
import sys
import collections

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.environ.get('DADOS', os.path.join(RAIZ, 'dados'))
ANOS = range(2023, datetime.date.today().year + 1)
MIN_VOTOS = 25
MIN_MINORIA = 0.025


def ler(nome, padrao=None):
    try:
        with open(os.path.join(DADOS, nome), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


INDICE = ler('indice.json', {}).get('p', {})
VOTACOES = [x for a in ANOS for x in (ler(f'votacoes-{a}.json', {}) or {}).get('itens', [])]


def ajustar(casa, dims=2, iters=3000, seed=0):
    linhas, leg, cols = [], {}, []
    for v in VOTACOES:
        if v.get('k') != casa:
            continue
        s, n = v.get('v', {}).get('S', []), v.get('v', {}).get('N', [])
        tot = len(s) + len(n)
        if tot < 10 or min(len(s), len(n)) / tot < MIN_MINORIA:
            continue
        j = len(cols)
        cols.append(v['id'])
        for valor, ids in ((1.0, s), (0.0, n)):
            for i in ids:
                k = casa + str(i)
                leg.setdefault(k, len(leg))
                linhas.append((leg[k], j, valor))
    cont = collections.Counter(r[0] for r in linhas)
    ok = {i for i, c in cont.items() if c >= MIN_VOTOS}
    linhas = [r for r in linhas if r[0] in ok]
    inv = {i: k for k, i in leg.items()}
    li = np.array([r[0] for r in linhas])
    vj = np.array([r[1] for r in linhas])
    y = np.array([r[2] for r in linhas])
    rng = np.random.default_rng(seed)
    L, J = len(leg), len(cols)
    x = rng.normal(0, 0.1, (L, dims))
    # Início com o PL à direita e PT, PSOL e PCdoB à esquerda, só para fixar a orientação.
    for k, i in leg.items():
        s = (INDICE.get(k) or {}).get('s', '')
        if s in ('PL', 'NOVO', 'Novo'):
            x[i, 0] = 1
        if s in ('PT', 'PSOL', 'PCdoB'):
            x[i, 0] = -1
    a = np.zeros(J)
    b = rng.normal(0, 0.1, (J, dims))
    lr = 0.05
    params = [x, a, b]
    m = [np.zeros_like(p) for p in params]
    v2 = [np.zeros_like(p) for p in params]
    for t in range(1, iters + 1):
        z = a[vj] + np.sum(b[vj] * x[li], 1)
        p = 1 / (1 + np.exp(-z))
        g = p - y
        gx = np.zeros_like(x)
        np.add.at(gx, li, g[:, None] * b[vj])
        gx += 0.5 * x
        ga = np.bincount(vj, g, J) + 0.01 * a
        gb = np.zeros_like(b)
        np.add.at(gb, vj, g[:, None] * x[li])
        gb += 0.1 * b
        for q, gr in enumerate((gx, ga, gb)):
            m[q] = 0.9 * m[q] + 0.1 * gr
            v2[q] = 0.999 * v2[q] + 0.001 * gr * gr
            params[q] -= lr * (m[q] / (1 - 0.9 ** t)) / (np.sqrt(v2[q] / (1 - 0.999 ** t)) + 1e-8)
    acerto = float(np.mean(((a[vj] + np.sum(b[vj] * x[li], 1)) > 0) == (y == 1)))
    X = x.copy()
    idx = sorted(ok)
    pl = [i for i in idx if (INDICE.get(inv[i]) or {}).get('s') == 'PL']
    pt = [i for i in idx if (INDICE.get(inv[i]) or {}).get('s') == 'PT']
    if pl and pt and X[pl, 0].mean() < X[pt, 0].mean():
        X[:, 0] *= -1
    for d in range(dims):
        lo, hi = np.percentile(X[idx, d], [2.5, 97.5])
        X[:, d] = (X[:, d] - (lo + hi) / 2) / ((hi - lo) / 2)
    pos = {inv[i]: [round(float(X[i, 0]), 3), round(float(X[i, 1]), 3), int(cont[i])] for i in idx}
    return pos, J, acerto


def cortes(pos, anteriores):
    d = np.array([v[0] for k, v in pos.items() if (INDICE.get(k) or {}).get('ex')])
    if anteriores and len(anteriores) == 3:
        a = [-1.0] + list(anteriores) + [1.4]
        c = np.array([(a[i] + a[i + 1]) / 2 for i in range(4)])
    else:
        c = np.percentile(d, [10, 40, 70, 95])
    for _ in range(200):
        lab = np.argmin(abs(d[:, None] - c[None]), 1)
        c = np.array([d[lab == j].mean() if (lab == j).any() else c[j] for j in range(4)])
    return [round(float(v), 3) for v in (c[:-1] + c[1:]) / 2]


def principal():
    if not INDICE or not VOTACOES:
        print('Faltam o índice ou as votações.', file=sys.stderr)
        sys.exit(1)
    antes = ler('posicoes.json', {}) or {}
    saida = {
        'gerado': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        'metodo': 'Pontos ideais em duas dimensões, por máxima verossimilhança com penalização, sobre as votações nominais contestadas, separadamente em cada Casa.',
    }
    for casa in 'CS':
        pos, J, acerto = ajustar(casa)
        c = cortes(pos, (antes.get(casa) or {}).get('cortes'))
        saida[casa] = {'votacoes': J, 'acerto': round(acerto, 3), 'cortes': c, 'p': pos}
        print(f'{casa}: {J} votações, {len(pos)} parlamentares, acerto {acerto:.3f}, cortes {c}')
    with open(os.path.join(DADOS, 'posicoes.json'), 'w', encoding='utf-8') as f:
        json.dump(saida, f, ensure_ascii=False)


if __name__ == '__main__':
    principal()
