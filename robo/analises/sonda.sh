#!/bin/bash
set +e
UA='exterminadores-do-futuro (observatório; contato@exterminadores.com.br)'
T=gn672Ad4CF8N6TK
lista(){ echo "=== $1"; curl -sS -A "$UA" -m 90 -u "$T:" -X PROPFIND -H 'Depth: 1' "https://arquivos.receitafederal.gov.br/public.php/webdav/$1" | grep -o '<d:href>[^<]*</d:href>\|<d:getcontentlength>[^<]*' | sed 's/<d:href>//;s/<\/d:href>//;s/<d:getcontentlength>/   tamanho /' | head -60; }
lista 'Dados'
lista 'Dados/'
for d in Dados/Beneficios Dados/Beneficios%20Fiscais Dados/DIRBI Dados/Renuncias Dados/Cadastros; do lista "$d"; done
