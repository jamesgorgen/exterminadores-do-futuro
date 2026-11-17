#!/bin/bash
# Sonda os endereços das bases de dados usadas na análise do PLP 299/2026.
set +e
UA='exterminadores-do-futuro (observatório; contato@exterminadores.com.br)'
sonda(){ echo "=== $1"; curl -sSL -A "$UA" -m 60 -o saida/tmp -w "HTTP %{http_code} %{content_type} %{size_download}\n" "$1"; head -c 3000 saida/tmp | tr -d '\r'; echo; }
sonda 'https://dados.gov.br/dados/api/publico/conjuntos-dados/renuncias-fiscais-de-tributos-federais'
sonda 'https://dados.gov.br/api/3/action/package_show?id=renuncias-fiscais-de-tributos-federais'
sonda 'https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/beneficios-e-renuncias-fiscais'
sonda 'https://dados.gov.br/dados/conjuntos-dados/renuncias-fiscais-de-tributos-federais'
sonda 'https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/'
sonda 'https://cdn.tse.jus.br/estatistica/sead/odsele/bem_candidato/'
curl -sSI -A "$UA" -m 60 'https://cdn.tse.jus.br/estatistica/sead/odsele/bem_candidato/bem_candidato_2022.zip' | head -12
curl -sSI -A "$UA" -m 60 'https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2022.zip' | head -12
curl -sSI -A "$UA" -m 60 'https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2018.zip' | head -12
rm -f saida/tmp
