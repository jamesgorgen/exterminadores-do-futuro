#!/bin/bash
set +e
UA='exterminadores-do-futuro (observatório; contato@exterminadores.com.br)'
for p in renuncias-fiscais-de-tributos-federais empresas-habilitadas-em-regimes-tributarios-e-aduaneiros-especiais; do
echo "=== $p"
curl -sSL -A "$UA" -m 60 "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/beneficios-e-renuncias-fiscais/$p" > saida/$p.html
grep -o 'href="[^"]*"' saida/$p.html | grep -iv 'facebook\|twitter\|linkedin\|whatsapp\|governodigital\|/pt-br/temas\|servicos\|\.css' | sort -u | head -60
python3 -c "
import re,html,sys;t=open('saida/$p.html',encoding='utf-8',errors='ignore').read()
m=re.search(r'id=\"content-core\"(.*?)</article>',t,re.S) or re.search(r'<article(.*?)</article>',t,re.S)
s=re.sub(r'<[^>]+>',' ',m.group(1) if m else t);s=html.unescape(re.sub(r'\s+',' ',s));print(s[:3000])"
done
echo "=== CNPJ"
curl -sSL -A "$UA" -m 60 'https://arquivos.receitafederal.gov.br/index.php/s/' -o /dev/null -w "%{http_code}\n"
curl -sSL -A "$UA" -m 60 'https://dadosabertos.rfb.gov.br/CNPJ/' | head -c 1500; echo
curl -sSL -A "$UA" -m 60 'https://dadosabertos.rfb.gov.br/CNPJ/dados_abertos_cnpj/' | grep -o 'href="[^"]*"' | tail -5
