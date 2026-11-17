#!/bin/bash
set +e
UA='exterminadores-do-futuro (observatório; contato@exterminadores.com.br)'
T=gn672Ad4CF8N6TK
lista(){ echo "=== $1"; curl -sS -A "$UA" -m 90 -u "$T:" -X PROPFIND -H 'Depth: 1' "https://arquivos.receitafederal.gov.br/public.php/webdav/$1" | grep -o '<d:href>[^<]*</d:href>\|<d:getcontentlength>[^<]*' | sed 's/<d:href>//;s/<\/d:href>//;s/<d:getcontentlength>/   tamanho /' | head -60; }
for d in Dados/Obrigacoes_Acessorias Dados/Creditos_Tributarios; do lista "$d"; done
for d in $(curl -sS -A "$UA" -m 90 -u "$T:" -X PROPFIND -H 'Depth: 1' https://arquivos.receitafederal.gov.br/public.php/webdav/Dados/Obrigacoes_Acessorias | grep -o '<d:href>[^<]*</d:href>' | sed 's/<d:href>\/public.php\/webdav\///;s/<\/d:href>//' | tail -n +2); do lista "$d"; done
for d in $(curl -sS -A "$UA" -m 90 -u "$T:" -X PROPFIND -H 'Depth: 1' https://arquivos.receitafederal.gov.br/public.php/webdav/Dados/Creditos_Tributarios | grep -o '<d:href>[^<]*</d:href>' | sed 's/<d:href>\/public.php\/webdav\///;s/<\/d:href>//' | tail -n +2); do lista "$d"; done
