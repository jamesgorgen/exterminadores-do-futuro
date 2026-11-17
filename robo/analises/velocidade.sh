T=gn672Ad4CF8N6TK; B=https://arquivos.receitafederal.gov.br/public.php/webdav/Dados/Cadastros/CNPJ
M=$(curl -s -u "$T:" -X PROPFIND -H 'Depth: 1' "$B/" | grep -o '[0-9]\{4\}-[0-9]\{2\}/' | sort -u | tail -1)
echo "mês $M"
curl -s -u "$T:" -X PROPFIND -H 'Depth: 1' "$B/$M" | grep -o '<d:getcontentlength>[0-9]*</d:getcontentlength>\|[A-Za-z]*[0-9]\.zip' | paste - - | head -40
curl -s -u "$T:" -o /dev/null --max-time 120 -w 'Socios0: %{size_download} bytes em %{time_total}s, %{speed_download} B/s\n' "$B/${M}Socios0.zip"
