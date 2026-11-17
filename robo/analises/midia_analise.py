# Análise local da saída de midia.py. Uso: python3 robo/analises/midia_analise.py <pasta da saída> <pasta da saída do plp299_tudo>
# Gera <saída>/vinculos.json e imprime o resumo por parlamentar.
import json, sys, os, re, collections, unicodedata
d, d2 = sys.argv[1] + '/', sys.argv[2] + '/'
def L(n, base=None):
    p = (base or d) + n
    return json.load(open(p)) if os.path.exists(p) else None
def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z ]', ' ', s)).strip()
PARL = L('parlamentares.json'); U = L('universo.json') or {}; QSA = L('qsa.json') or {}
ind = json.load(open('dados/indice.json'))['p']
EX = {k for k, v in ind.items() if v.get('ex')}
QUAL = {'05': 'administrador', '10': 'diretor', '16': 'presidente', '22': 'sócio', '49': 'sócio-administrador', '65': 'titular',
        '17': 'procurador', '08': 'conselheiro', '30': 'sócio comanditado', '31': 'sócio comanditário', '37': 'sócio PJ domiciliado no exterior'}
def emp(b):
    u = U.get(b, {}); e = (u.get('estab') or [{}])
    m = next((x for x in e if x.get('cnpj', '').endswith('0001') or True), {})
    ativa = any(x.get('sit') == '02' for x in e)
    tipo = ', '.join(sorted(set(u.get('cnaes', [])))) or ('outorga MCom' if u.get('mcom') else 'nome')
    return {'b': b, 'razao': u.get('razao'), 'uf': m.get('uf'), 'ativa': ativa, 'mcom': u.get('mcom'), 'cnaes': u.get('cnaes'), 'natureza': u.get('natureza')}
UF_EMP = {b: {x.get('uf') for x in u.get('estab', [])} for b, u in U.items()}
V = collections.defaultdict(list)   # parlamentar -> [vínculos]
def add(k, tipo, forca, b, det):
    V[k].append({'tipo': tipo, 'forca': forca, **emp(b), 'det': det})

CHAVES = {(norm(p['nomeCompleto']), c[3:9]): k for k, p in PARL.items() if p.get('nomeCompleto') for c in p['cpfs']}
# 1. direto (QSA atual)
for b, ss in QSA.items():
    if b not in U: continue
    for s in ss:
        k = CHAVES.get((norm(s['nome']), s['doc'].strip('*'))) if s['tipo'] == '2' else None
        if k: add(k, 'sócio direto', 'direto', b, QUAL.get(s['qualif'], s['qualif']) + ' desde ' + s['entrada'])
# 2. holdings: mídia <- holding (QSA nível 2/3) <- parlamentar ; ou empresa do parlamentar sócia da mídia
pai = collections.defaultdict(set)   # holding -> empresas que ela controla
for b, ss in QSA.items():
    for s in ss:
        if s['tipo'] == '1': pai[s['doc'][:8]].add(b)
def midias_acima(h, prof=0):
    out = set()
    for x in pai.get(h, ()):
        if x in U: out.add(x)
        if prof < 3: out |= midias_acima(x, prof + 1)
    return out
for h, ss in QSA.items():
    if h in U and not any(s.get('holding') for s in ss): pass
    for s in ss:
        k = CHAVES.get((norm(s['nome']), s['doc'].strip('*'))) if s['tipo'] == '2' and s.get('holding') else None
        if k:
            for m in midias_acima(h): add(k, 'por holding', 'forte', m, f'sócio da holding {h}')
EMPP = collections.defaultdict(set)
for s in L('socios.json', d2)['socios']: EMPP[s['cnpj']].add(s['codigo'])
for x in L('doparl_pj.json') or []:
    if x['cnpj'] in U:
        for k in EMPP.get(x['socio_pj'][:8], ()): add(k, 'empresa do parlamentar é sócia', 'forte', x['cnpj'], f"via {x['nome']}")
# 3. representação legal
for r in L('representacao.json') or []:
    if r['cnpj'] in U: add(r['parl'], 'representante legal de sócio', 'forte', r['cnpj'], f"representa {r['nome']}")
# 4. rede de sócios
COS = {(c['nome'], c['cpf6']): c['parl'] for c in L('cosocios.json') or []}
for b, ss in QSA.items():
    if b not in U: continue
    for s in ss:
        if s['tipo'] != '2': continue
        for k in COS.get((norm(s['nome']), s['doc'].strip('*')), []):
            if CHAVES.get((norm(s['nome']), s['doc'].strip('*'))) == k: continue
            add(k, 'sócio do parlamentar em outra empresa', 'forte', b, s['nome'])
# 5. familiares por sobrenome raro na mesma UF
PART = {'DA', 'DE', 'DO', 'DAS', 'DOS', 'E', 'JUNIOR', 'FILHO', 'NETO', 'SOBRINHO', 'JR'}
freq = collections.Counter()
pf = [(b, s) for b, ss in QSA.items() for s in ss if s['tipo'] == '2']
for b, s in pf: freq.update(set(norm(s['nome']).split()[1:]))
comuns = {t for t, n in freq.most_common(300)}
idx = collections.defaultdict(list)
for b, s in pf:
    for t in set(norm(s['nome']).split()[1:]) - PART - comuns: idx[t].append((b, s))
for k, p in PARL.items():
    toks = [t for t in norm(p.get('nomeCompleto')).split()[1:] if t not in PART and t not in comuns and len(t) > 2]
    if not toks: continue
    vist = set()
    for t in toks:
        for b, s in idx.get(t, []):
            if b not in U or p['uf'] not in UF_EMP.get(b, set()): continue
            if CHAVES.get((norm(s['nome']), s['doc'].strip('*'))) == k: continue
            comuns_n = set(norm(s['nome']).split()) & set(toks)
            chave = (b, s['nome'])
            if chave in vist: continue
            vist.add(chave)
            raro = min(freq[x] for x in comuns_n)
            forca = 'sobrenome (2+)' if len(comuns_n) >= 2 else ('sobrenome raro' if raro <= 15 else None)
            if forca: add(k, 'possível familiar', forca, b, f"{s['nome']} ({QUAL.get(s['qualif'], s['qualif'])}); sobrenomes em comum: {', '.join(sorted(comuns_n))}")
# 6. contatos compartilhados
for chave, bs in (L('contatos_compartilhados.json') or {}).items():
    ms = [b for b in bs if b in U]; ps = {k for b in bs for k in EMPP.get(b, ())}
    if len(bs) > 6: continue   # contador ou endereço genérico
    for k in ps:
        for m in ms:
            if m not in {x for x in bs if k in EMPP.get(x, ())}: add(k, 'contato igual ao de empresa do parlamentar', 'indício', m, chave.split('|')[0])
# 7. dinheiro
for x in L('ceap_midia.json') or []:
    k = x.get('parl') if x['casa'] == 'C' else next((kk for kk, p in PARL.items() if kk[0] == 'S' and norm(p['nome']) == norm(x['nome'])), None)
    if k: add(k, 'cota parlamentar paga', 'indício', x['cnpj'][:8], f"{x['ano']} R$ {x['valor']} ({x.get('tipo')})")
for x in L('campanha_despesas_midia.json') or []: add(x['parl'], 'gasto de campanha', 'indício', x['cnpj'][:8], f"{x['ano']} R$ {x['valor']}")
for x in L('campanha_doacoes_socios_midia.json') or []:
    if x.get('empresa_midia') in U: add(x['parl'], 'doação de sócio/empresa de mídia', 'indício', x['empresa_midia'], f"{x['ano']} {x['doador']} R$ {x['valor']}")
# 8. gabinete
for x in L('gabinetes_x_midia.json') or []:
    for b in x['empresas']: add(x['parl'], 'funcionário do gabinete é sócio', 'forte', b, x['nome'])
# 9. saídas
sa = L('saidas.json') or {}
for x in sa.get('saidas', []):
    if x['cnpj'] in U: add(x['parl'], f"saiu da sociedade (estava em {sa['mes_antigo']})", 'forte', x['cnpj'], f"entrada {x['entrada']}; sócios atuais: " + '; '.join(s['nome'] for s in sa['qsa_atual'].get(x['cnpj'], [])[:6]))
# 10. bens declarados ao TSE
rx = re.compile(r'R[AÁ]DIO|TELEVIS|\bTV\b|JORNAL|EMISSORA|RADIODIFUS|RADIOFUS', re.I)
for f, pre in (('bens.json', 'S'), ('bens_deputados.json', 'C')):
    for x in L(f, d2) or []:
        if rx.search(x.get('desc') or '') and not re.search('RADIOLOG|APARTAMENTO|IMOVEL|SALA', x['desc'], re.I):
            V[pre + str(x['codigo'])].append({'tipo': f"declarou ao TSE ({x['ano']})", 'forca': 'direto', 'b': None, 'razao': x['desc'][:120], 'uf': None, 'ativa': None, 'det': 'R$ ' + x['valor']})
ORD = {'direto': 0, 'forte': 1, 'sobrenome (2+)': 2, 'sobrenome raro': 3, 'indício': 4}
res = {}
for k, vs in V.items():
    i = ind.get(k, {}); p = PARL.get(k, {})
    res[k] = {'nome': i.get('n') or p.get('nome'), 'partido': i.get('s') or p.get('partido'), 'uf': i.get('uf') or p.get('uf'), 'grupo': i.get('cl'), 'ex': k in EX,
              'melhor': min(ORD[v['forca']] for v in vs), 'vinculos': sorted(vs, key=lambda v: ORD[v['forca']])}
json.dump(res, open(d + 'vinculos.json', 'w'), ensure_ascii=False, indent=1)
ex = {k: v for k, v in res.items() if v['ex']}
print('parlamentares em exercício com algum vínculo:', len(ex))
for nivel, nome in ORD.items():
    print(' melhor vínculo', nivel, sum(1 for v in ex.values() if v['melhor'] == nome))
for k, v in sorted(ex.items(), key=lambda x: (x[1]['melhor'], x[0][0], x[1]['nome'] or '')):
    print(f"\n{k} {v['nome']} ({v['partido']}/{v['uf']}, {v['grupo']})")
    for x in v['vinculos'][:12]: print('   ', x['forca'], '|', x['tipo'], '|', x['razao'], x['uf'] or '', '' if x['ativa'] in (None, True) else '[inativa]', '|', x['det'])
