"""Robô do comparador: processa os pedidos que o Worker público deixa no R2.

R2 (bucket privado exterminadores-dados), prefixo comparador/:
  pedidos/<id>.json      pedido e situação (fila, processando, pronta, erro, removida)
  envios/<sha256>.pdf    PDFs enviados pelos visitantes
  fontes/<ref>.pdf       PDFs baixados da Câmara e do Senado (cache)
  resultados/<id>.json   comparação pronta (quadro, análise, metadados)
  indice.json            lista das comparações prontas, lida pela página
  cota/AAAA-MM/<ip>      uso mensal por IP (o Worker grava; o robô devolve a cota quando o pedido falha)

Também cria os pedidos de robo/comparador/semente.json e remove as comparações listadas em robo/comparador/remover.txt.
Uso: python robo/comparador/fila.py   (variáveis R2_* e ANTHROPIC_API_KEY)
"""
import hashlib, json, os, re, sys, tempfile, time, traceback, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motor, analise

AQUI = os.path.dirname(os.path.abspath(__file__))
P = 'comparador/'
MAX_TENTATIVAS = 3
ORCAMENTO_S = int(os.environ.get('COMPARADOR_ORCAMENTO_S', '1500'))
UA = {'User-Agent': 'exterminadores.com.br (comparador de textos; contato@exterminadores.com.br)'}

def agora():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def id_de(ref_a, ref_b):
    """Mesma conta do Worker: os 16 primeiros caracteres do SHA-256 de 'refA|refB'."""
    return hashlib.sha256(f'{ref_a}|{ref_b}'.encode()).hexdigest()[:16]

# ---------------------------------------------------------------- R2
def r2():
    import boto3
    return boto3.client('s3', endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID'].strip()}.r2.cloudflarestorage.com",
                        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'].strip(), aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'].strip(),
                        region_name='auto')
S3, B = None, os.environ.get('R2_BUCKET', 'exterminadores-dados')

def ler(k, binario=False):
    try:
        o = S3.get_object(Bucket=B, Key=P + k)['Body'].read()
        return o if binario else json.loads(o)
    except S3.exceptions.NoSuchKey:
        return None
    except Exception as e:
        if 'NoSuchKey' in str(e) or '404' in str(e):
            return None
        raise

def gravar(k, obj, tipo='application/json'):
    corpo = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode()
    S3.put_object(Bucket=B, Key=P + k, Body=corpo, ContentType=tipo)

def apagar(k):
    S3.delete_object(Bucket=B, Key=P + k)

def listar(prefixo):
    chaves, tok = [], None
    while True:
        kw = {'Bucket': B, 'Prefix': P + prefixo}
        if tok: kw['ContinuationToken'] = tok
        r = S3.list_objects_v2(**kw)
        chaves += [o['Key'][len(P):] for o in r.get('Contents', [])]
        if not r.get('IsTruncated'): return chaves
        tok = r['NextContinuationToken']

# ---------------------------------------------------------------- fontes
def http(url, tentativas=4, json_=False):
    ultimo = None
    for t in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={**UA, 'Accept': 'application/json' if json_ else '*/*'})
            with urllib.request.urlopen(req, timeout=120) as r:
                dados = r.read()
            return json.loads(dados) if json_ else dados
        except Exception as e:
            ultimo = e
            time.sleep(5 * (t + 1))
    raise RuntimeError(f'não foi possível baixar {url[:90]}: {ultimo}')

def _data(s):
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', s or '')
    return f'{m.group(3)}/{m.group(2)}/{m.group(1)}' if m else ''

def fonte(ref, pedido_lado):
    """Devolve (bytes do PDF, metadados) de uma referência camara:ID, senado:PROCESSO:DOC ou arquivo:SHA256."""
    if ref.startswith('camara:'):
        pid = ref.split(':')[1]
        d = http(f'https://dadosabertos.camara.leg.br/api/v2/proposicoes/{pid}', json_=True)['dados']
        autor = ''
        try:
            aut = http(f'https://dadosabertos.camara.leg.br/api/v2/proposicoes/{pid}/autores', json_=True)['dados']
            if aut: autor = aut[0].get('nome', '') + (f' e outros' if len(aut) > 1 else '')
        except Exception:
            pass
        if not d.get('urlInteiroTeor'):
            raise ValueError(f"A Câmara não publicou o texto integral de {d.get('siglaTipo')} {d.get('numero')}/{d.get('ano')}.")
        nome = f"{d.get('siglaTipo')} {d.get('numero')}" + (f"/{d.get('ano')}" if str(d.get('ano') or '0') != '0' else '')
        meta = {'nome': nome, 'tipo': d.get('descricaoTipo', ''), 'autor': autor,
                'data': _data(d.get('dataApresentacao')), 'url': d['urlInteiroTeor'].replace('http://', 'https://'),
                'casa': 'Câmara', 'ementa': (d.get('ementa') or '')[:400]}
        url = meta['url']
    elif ref.startswith('senado:'):
        _, proc, doc = ref.split(':')
        d = http(f'https://legis.senado.leg.br/dadosabertos/processo/{proc}', json_=True)
        achado = None
        for au in d.get('autuacoes') or []:
            for inf in au.get('informesLegislativos') or []:
                for x in inf.get('documentosAssociados') or []:
                    if (x.get('url') or '').endswith('/' + doc):
                        achado = x
        if not achado:
            raise ValueError('Documento do Senado não encontrado no processo.')
        url = achado['url']
        meta = {'nome': achado.get('identificacao') or achado.get('tipo', 'Documento'), 'tipo': achado.get('tipo', ''),
                'autor': achado.get('autoria', ''), 'data': _data(achado.get('data')), 'url': url, 'casa': 'Senado',
                'ementa': (achado.get('descricao') or '')[:400]}
    elif ref.startswith('arquivo:'):
        sha = ref.split(':')[1]
        pdf = ler(f'envios/{sha}.pdf', binario=True)
        if pdf is None:
            raise ValueError('O PDF enviado não foi encontrado.')
        if hashlib.sha256(pdf).hexdigest() != sha:
            raise ValueError('O PDF enviado chegou corrompido.')
        nome = re.sub(r'\s+', ' ', str(pedido_lado.get('nome') or 'PDF enviado')).strip()[:120]
        meta = {'nome': nome, 'tipo': 'PDF enviado', 'autor': re.sub(r'\s+', ' ', str(pedido_lado.get('autor') or ''))[:120],
                'data': re.sub(r'[^0-9/]', '', str(pedido_lado.get('data') or ''))[:10], 'url': '', 'casa': 'Envio'}
        return pdf, meta
    else:
        raise ValueError('Referência inválida.')
    chave = 'fontes/' + hashlib.sha256(ref.encode()).hexdigest()[:24] + '.pdf'
    pdf = ler(chave, binario=True)
    if pdf is None:
        pdf = http(url)
        if pdf[:4] != b'%PDF':
            raise ValueError(f"O texto de {meta['nome']} não veio em PDF.")
        gravar(chave, pdf, 'application/pdf')
    return pdf, meta

# ---------------------------------------------------------------- processamento
def processar(ped):
    with tempfile.TemporaryDirectory() as tmp:
        metas, textos, ocr = {}, {}, []
        for lado in ('a', 'b'):
            pdf, meta = fonte(ped[lado]['ref'], ped[lado])
            if pdf[:4] != b'%PDF':
                raise ValueError('Um dos arquivos não é um PDF.')
            arq = os.path.join(tmp, lado + '.pdf')
            open(arq, 'wb').write(pdf)
            txt, usou_ocr = motor.extrair(arq)
            if usou_ocr: ocr.append(meta['nome'])
            textos[lado] = motor.articulado(txt)
            metas[lado] = meta
    comp = motor.comparar(textos['a'], textos['b'])
    if not any(i['cls'] != 'igual' for i in comp['itens']):
        avisos_iguais = ['Os dois textos são iguais.']
    else:
        avisos_iguais = []
    meta_ia = {'proposicao': ped.get('proposicao'), 'A': metas['a'], 'B': metas['b']}
    avisos = list(avisos_iguais)
    if ocr:
        avisos.append('Texto obtido por leitura óptica (PDF escaneado): pode haver erros de leitura em ' + ', '.join(ocr) + '.')
    try:
        ia, uso = analise.analisar(meta_ia, comp) if not avisos_iguais else ({'conclusao': 'Os dois textos são iguais', 'resumo': [], 'balanco': '', 'itens': {}}, {})
    except Exception as e:
        if ped.get('tentativas', 0) + 1 < MAX_TENTATIVAS:
            raise
        ia, uso = {'conclusao': '', 'resumo': [], 'balanco': '', 'itens': {}}, {}
        avisos.append('A análise de IA não pôde ser feita; o quadro comparativo está completo.')
    itens = []
    for it in comp['itens']:
        chave = it['b'] or it['a']
        a = ia['itens'].get(chave, {})
        cls = it['cls']
        if cls == 'alterado':
            cls = a.get('cls', 'merito')
        nota = a.get('nota') or {'igual': 'Sem alteração.', 'reorganizado': 'Só mudanças de posição ou de numeração.'}.get(cls, '')
        itens.append({'a': it['a'], 'b': it['b'], 'cls': cls, 'efeito': a.get('efeito', []), 'nota': nota,
                      'rows': it['rows'], 'st': it['st'], 'tam': it['tamanho']})
    contagem = {}
    for it in itens:
        contagem[it['cls']] = contagem.get(it['cls'], 0) + 1
    titulo = re.sub(r'\s+', ' ', str(ped.get('titulo') or '')).strip()[:140] or (ped.get('proposicao') or metas['a']['nome'])
    return {'id': ped['id'], 'titulo': titulo, 'proposicao': ped.get('proposicao') or '', 'conclusao': ia['conclusao'],
            'versaoA': metas['a'], 'versaoB': metas['b'], 'resumo': ia['resumo'], 'balanco': ia['balanco'],
            'renomeacoes': comp['renomeacoes'], 'itens': itens, 'contagem': contagem, 'avisos': avisos,
            'gerado': agora(), 'ia': uso}

def entrada_indice(res):
    return {'id': res['id'], 'titulo': res['titulo'], 'proposicao': res['proposicao'], 'conclusao': res['conclusao'],
            'a': {'nome': res['versaoA']['nome'], 'data': res['versaoA'].get('data', ''), 'casa': res['versaoA'].get('casa', '')},
            'b': {'nome': res['versaoB']['nome'], 'data': res['versaoB'].get('data', ''), 'casa': res['versaoB'].get('casa', '')},
            'contagem': res['contagem'], 'gerado': res['gerado']}

def atualizar_indice(novos=(), remover=()):
    ind = ler('indice.json') or {'itens': []}
    itens = [x for x in ind['itens'] if x['id'] not in set(remover) and x['id'] not in {n['id'] for n in novos}]
    itens = list(novos) + itens
    itens.sort(key=lambda x: x['gerado'], reverse=True)
    gravar('indice.json', {'atualizado': agora(), 'itens': itens})

# ---------------------------------------------------------------- semente e remoção
def semente():
    arq = os.path.join(AQUI, 'semente.json')
    if not os.path.exists(arq):
        return
    for s in json.load(open(arq)):
        pid = id_de(s['a']['ref'], s['b']['ref'])
        if ler(f'pedidos/{pid}.json') is None:
            gravar(f'pedidos/{pid}.json', {'id': pid, 'estado': 'fila', 'criado': agora(), 'atualizado': agora(), 'origem': 'semente',
                                            'a': s['a'], 'b': s['b'], 'titulo': s.get('titulo', ''), 'proposicao': s.get('proposicao', ''), 'tentativas': 0})
            print('semente na fila:', pid, s.get('titulo'))

def remocoes():
    arq = os.path.join(AQUI, 'remover.txt')
    if not os.path.exists(arq):
        return
    ids = [l.split('#')[0].strip() for l in open(arq)]
    ids = [i for i in ids if re.fullmatch(r'[0-9a-f]{16}', i)]
    feitos = []
    for i in ids:
        ped = ler(f'pedidos/{i}.json')
        if ped and ped.get('estado') == 'removida':
            continue
        if ler(f'resultados/{i}.json') is not None:
            apagar(f'resultados/{i}.json')
        gravar(f'pedidos/{i}.json', {**(ped or {'id': i}), 'estado': 'removida', 'atualizado': agora()})
        feitos.append(i)
    if feitos:
        atualizar_indice(remover=feitos)
        print('removidas:', feitos)

# ---------------------------------------------------------------- principal
def main():
    global S3
    S3 = r2()
    inicio = time.time()
    semente()
    remocoes()
    pend = []
    for k in listar('pedidos/'):
        ped = ler(k)
        if not ped:
            continue
        parado = ped.get('estado') == 'processando' and (time.time() - datetime.fromisoformat(ped['atualizado']).timestamp()) > 3600
        if ped.get('estado') == 'fila' or parado:
            pend.append(ped)
    pend.sort(key=lambda p: p['criado'])
    print(f'{len(pend)} pedido(s) na fila')
    for ped in pend:
        if time.time() - inicio > ORCAMENTO_S:
            print('tempo esgotado; o resto fica para a próxima execução'); break
        pid = ped['id']
        ped.update(estado='processando', atualizado=agora())
        gravar(f'pedidos/{pid}.json', ped)
        try:
            t0 = time.time()
            res = processar(ped)
            gravar(f'resultados/{pid}.json', res)
            atualizar_indice(novos=[entrada_indice(res)])
            ped.update(estado='pronta', atualizado=agora(), erro=None)
            print(f'pronta {pid} em {time.time() - t0:.0f}s', res.get('ia'))
        except Exception as e:
            ped['tentativas'] = ped.get('tentativas', 0) + 1
            definitivo = isinstance(e, ValueError) or ped['tentativas'] >= MAX_TENTATIVAS
            msg = str(e) if isinstance(e, ValueError) else 'Falha temporária ao processar; tente de novo mais tarde.'
            ped.update(estado='erro' if definitivo else 'fila', atualizado=agora(), erro=msg if definitivo else None)
            print(f'erro {pid} (tentativa {ped["tentativas"]}):', type(e).__name__, str(e)[:300])
            traceback.print_exc()
            if definitivo and ped.get('cota'):
                try:
                    apagar(ped['cota']); print('cota devolvida')
                except Exception:
                    pass
        gravar(f'pedidos/{pid}.json', ped)

if __name__ == '__main__':
    main()
