"""Converte as votações-chave antigas das bancadas (marcadas votação por votação) em proposições-chave (marcadas pelo
projeto), em bancadas/decisoes.json no R2. Uso único. A saída lista só projetos e marcações, sem nomes."""
import glob, json, os, re, subprocess, sys, time, unicodedata
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'boto3'], check=True)
import boto3
os.makedirs('saida', exist_ok=True)
s3 = boto3.client('s3', endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID'].strip()}.r2.cloudflarestorage.com",
                  aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'].strip(), aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'].strip(),
                  region_name='auto')
B = os.environ['R2_BUCKET']; K = 'bancadas/decisoes.json'
dados = json.loads(s3.get_object(Bucket=B, Key=K)['Body'].read())
vot = {}
for f in glob.glob('dados/votacoes-20*.json'):
    for v in json.load(open(f)).get('itens', []): vot[v['id']] = v
RX = re.compile(r'^(PEC|PDL|PL|PLP) \d+/\d{4}$')
pro = dados.setdefault('proposicoes', {}); feito, sem = {}, []
for b, o in list((dados.get('votacoes') or {}).items()):
    for i, val in list(o.items()):
        v = vot.get(i) or {}; c = (v.get('mp') or v.get('mat') or '').upper()
        if not RX.match(c) or val not in ('S', 'N'): sem.append(i); continue
        pro.setdefault(b, {}).setdefault(c, val); feito.setdefault(b, {})[c] = val; del o[i]
    if not o: dados['votacoes'].pop(b)
agora = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()); dados['atualizado'] = agora
s3.put_object(Bucket=B, Key=K, Body=json.dumps(dados, ensure_ascii=False).encode(), ContentType='application/json')
s3.put_object(Bucket=B, Key=f"bancadas/historico/{agora.replace(':', '-')}-migracao.json", Body=json.dumps({'por': 'robô (migração para proposições-chave)', 'em': agora, 'convertidas': feito, 'sem_projeto': sem}).encode())
res = {'convertidas': feito, 'votacoes_sem_projeto_mantidas': sem, 'proposicoes_chave': pro}
print(json.dumps(res, ensure_ascii=False, indent=1)); open('saida/resultado.json', 'w').write(json.dumps(res, ensure_ascii=False, indent=1) + '\n')
