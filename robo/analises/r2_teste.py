"""Teste do R2: grava, lista, lê e apaga um arquivo no bucket. Não imprime as chaves."""
import os, subprocess, sys, time
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'boto3'], check=True)
import boto3
os.makedirs('saida', exist_ok=True)
linhas = []
def p(*a):
    print(*a, flush=True); linhas.append(' '.join(map(str, a)))
for v in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY'):
    x = os.environ.get(v, '')
    p(v, 'presente' if x else 'AUSENTE', f'({len(x)} caracteres, sem espaços nas pontas: {x == x.strip()})')
try:
    s3 = boto3.client('s3', endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID'].strip()}.r2.cloudflarestorage.com",
                      aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'].strip(), aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'].strip(),
                      region_name='auto')
    b = os.environ['R2_BUCKET']; k = 'teste/ola.txt'; corpo = f'ok {time.time()}'.encode()
    s3.put_object(Bucket=b, Key=k, Body=corpo); p('gravação: ok')
    p('listagem:', [o['Key'] for o in s3.list_objects_v2(Bucket=b, Prefix='teste/').get('Contents', [])])
    p('leitura confere:', s3.get_object(Bucket=b, Key=k)['Body'].read() == corpo)
    s3.delete_object(Bucket=b, Key=k); p('remoção: ok')
    p('RESULTADO: R2 FUNCIONANDO')
except Exception as e:
    p('RESULTADO: FALHOU', type(e).__name__, str(e)[:300])
open('saida/resultado.txt', 'w').write('\n'.join(linhas) + '\n')
