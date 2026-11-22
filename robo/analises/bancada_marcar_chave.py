"""Marca votações-chave de uma bancada direto nas decisões da equipe (bancadas/decisoes.json, no R2), como faria a
página de triagem. Uso pontual, a pedido da equipe. Variáveis: BANCADA e VOTOS ("id=S,id=N"; "id=" desmarca).
Grava também uma cópia da mudança em bancadas/historico/. A saída só lista ids e votos esperados, sem nomes."""
import json, os, subprocess, sys, time
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'boto3'], check=True)
import boto3

BAN = os.environ.get('BANCADA', 'plataformas')
VOTOS = os.environ.get('VOTOS', 'C:2310837-8=N,C:2579791-17=N')
os.makedirs('saida', exist_ok=True)
s3 = boto3.client('s3', endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID'].strip()}.r2.cloudflarestorage.com",
                  aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'].strip(), aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'].strip(),
                  region_name='auto')
B = os.environ['R2_BUCKET']; K = 'bancadas/decisoes.json'
try: dados = json.loads(s3.get_object(Bucket=B, Key=K)['Body'].read())
except Exception: dados = {'decisoes': {}, 'votacoes': {}}
vot = dados.setdefault('votacoes', {}).setdefault(BAN, {})
mud = {}
for par in filter(None, VOTOS.split(',')):
    i, _, v = par.strip().partition('=')
    if v in ('S', 'N'): vot[i] = v
    else: vot.pop(i, None)
    mud[i] = v or None
if not vot: dados['votacoes'].pop(BAN, None)
agora = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
dados['atualizado'] = agora
s3.put_object(Bucket=B, Key=K, Body=json.dumps(dados, ensure_ascii=False).encode(), ContentType='application/json')
s3.put_object(Bucket=B, Key=f"bancadas/historico/{agora.replace(':', '-')}-robo.json",
              Body=json.dumps({'por': 'robô (análise avulsa, a pedido da equipe)', 'em': agora, 'mudancas': {'votacoes': {BAN: mud}}}).encode())
res = {'bancada': BAN, 'marcadas_agora': mud, 'votacoes_chave_da_bancada': dados['votacoes'].get(BAN, {})}
print(json.dumps(res, ensure_ascii=False, indent=1))
open('saida/resultado.json', 'w').write(json.dumps(res, ensure_ascii=False, indent=1) + '\n')
