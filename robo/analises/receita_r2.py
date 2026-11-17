"""Espelho mensal no Cloudflare R2: base do CNPJ da Receita (mês atual completo e Sócios do mês mais antigo) e bases do TSE.
Baixa em paralelo (o servidor da Receita é lento por conexão) e só envia o que ainda não está no bucket com o mesmo tamanho.
Estrutura no bucket: receita/cnpj/<AAAA-MM>/<arquivo>.zip ; tse/<arquivo>.zip ; receita/cnpj/indice.json"""
import os, re, sys, json, time, subprocess, threading, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'boto3'], check=True)
import boto3, requests
from boto3.s3.transfer import TransferConfig

UA = {'user-agent': 'exterminadores-do-futuro (observatório; contato@exterminadores.com.br)'}
RFB = 'https://arquivos.receitafederal.gov.br/public.php/webdav/Dados'
TOKEN = ('gn672Ad4CF8N6TK', '')
TSE = 'https://cdn.tse.jus.br/estatistica/sead/odsele'
B = os.environ.get('R2_BUCKET', 'exterminadores-dados')
s3 = boto3.client('s3', endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID'].strip()}.r2.cloudflarestorage.com",
                  aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'].strip(), aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'].strip(), region_name='auto')
CFG = TransferConfig(multipart_chunksize=64 << 20, max_concurrency=4)
T0 = time.time(); trava = threading.Lock()
def log(*a):
    with trava: print(f'[{(time.time()-T0)/60:.0f} min]', *a, flush=True)
os.makedirs('saida', exist_ok=True); os.makedirs('/tmp/espelho', exist_ok=True)

def tamanho_r2(chave):
    try: return s3.head_object(Bucket=B, Key=chave)['ContentLength']
    except Exception: return None
def listar(caminho):
    r = requests.request('PROPFIND', f'{RFB}/{caminho}', headers={**UA, 'Depth': '1'}, auth=TOKEN, timeout=120)
    out = []
    for resp in ET.fromstring(r.content).iter('{DAV:}response'):
        href = resp.find('{DAV:}href').text
        tam = resp.find('.//{DAV:}getcontentlength')
        out.append((href, int(tam.text) if tam is not None and tam.text else None))
    return out

def espelhar(url, chave, auth=None, tam_origem=None):
    atual = tamanho_r2(chave)
    if atual and (tam_origem is None or atual == tam_origem):
        log('já no R2', chave, atual); return chave, atual, 'existente'
    local = '/tmp/espelho/' + chave.replace('/', '_')
    for t in range(4):
        try:
            with requests.get(url, headers=UA, auth=auth, stream=True, timeout=900) as r:
                r.raise_for_status()
                with open(local, 'wb') as f:
                    for b in r.iter_content(4 << 20): f.write(b)
            if tam_origem and os.path.getsize(local) != tam_origem: raise IOError('tamanho diferente do anunciado')
            break
        except Exception as e:
            log('falha', chave, 'tentativa', t + 1, e); time.sleep(30)
    else:
        return chave, None, 'falhou'
    s3.upload_file(local, B, chave, Config=CFG)
    n = os.path.getsize(local); os.remove(local)
    log('enviado', chave, f'{n/1e6:.0f} MB'); return chave, n, 'enviado'

tarefas = []
meses = sorted(h.rstrip('/').split('/')[-1] for h, _ in listar('Cadastros/CNPJ/') if re.search(r'\d{4}-\d{2}/?$', h))
atual, antigo = meses[-1], meses[0]
log('meses', antigo, '...', atual)
for href, tam in listar(f'Cadastros/CNPJ/{atual}/'):
    nome = href.rstrip('/').split('/')[-1]
    if nome.endswith('.zip'): tarefas.append((f'{RFB}/Cadastros/CNPJ/{atual}/{nome}', f'receita/cnpj/{atual}/{nome}', TOKEN, tam))
for href, tam in listar(f'Cadastros/CNPJ/{antigo}/'):
    nome = href.rstrip('/').split('/')[-1]
    if nome.startswith('Socios') and nome.endswith('.zip'): tarefas.append((f'{RFB}/Cadastros/CNPJ/{antigo}/{nome}', f'receita/cnpj/{antigo}/{nome}', TOKEN, tam))
for ano in (2018, 2022, 2026):
    for nome in (f'consulta_cand/consulta_cand_{ano}.zip', f'bem_candidato/bem_candidato_{ano}.zip',
                 f'prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{ano}.zip'):
        tarefas.append((f'{TSE}/{nome}', f'tse/{nome.split("/")[-1]}', None, None))
log('arquivos a conferir', len(tarefas))

res = []
with ThreadPoolExecutor(max_workers=int(os.environ.get('PARALELO', '6'))) as ex:
    fut = [ex.submit(espelhar, *t) for t in tarefas]
    for f in as_completed(fut): res.append(f.result())
indice = {'atualizado': time.strftime('%Y-%m-%d %H:%M'), 'mes_atual': atual, 'mes_antigo': antigo, 'arquivos': sorted(res)}
s3.put_object(Bucket=B, Key='receita/cnpj/indice.json', Body=json.dumps(indice, ensure_ascii=False, indent=1).encode())
json.dump(indice, open('saida/indice.json', 'w'), ensure_ascii=False, indent=1)
falhas = [r for r in res if r[2] == 'falhou']
log('fim', len(res), 'arquivos;', len(falhas), 'falhas', falhas)
