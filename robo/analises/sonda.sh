#!/bin/bash
set +e
UA='exterminadores-do-futuro (observatório; contato@exterminadores.com.br)'
echo "=== links da página de benefícios da Receita"
curl -sSL -A "$UA" -m 60 'https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/beneficios-e-renuncias-fiscais' | grep -o 'href="[^"]*"' | grep -iv 'portal_css\|\.css\|javascript\|#' | sort -u | grep -i 'dirbi\|renun\|benef\|csv\|zip\|xlsx\|dados' | head -80
echo "=== links da página de dados CNPJ"
curl -sSL -A "$UA" -m 60 'https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/cadastros/consultas/dados-publicos-cnpj' | grep -o 'href="[^"]*"' | grep -i 'arquivos\|cnpj\|dados' | sort -u | head -30
