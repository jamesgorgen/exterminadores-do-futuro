# Passagem de sessão (17/11/2026)

Esta seção resume a sessão de 30/10 a 17/11. O histórico anterior está no arquivo PASSAGEM.md da área de arquivos do projeto no Claude.

## Onde está tudo
- Código e dados: repositório `jamesgorgen/exterminadores-do-futuro`, publicado em exterminadores.com.br (GitHub Pages). O `LEIA-ME.md` do repositório descreve robôs, arquivos e páginas.
- Segredo `ANTHROPIC_API_KEY` no GitHub. O workflow "Testar a chave da API" confere se ela funciona.
- Commits terminam com as linhas Co-Authored-By e Claude-Session.

## O que foi feito nesta fase
- **Relatorias da Câmara** em `dados/relatorias-camara.json` e arquivos por deputado em `dados/relatorias-camara/`.
- **Biografias** (`robo/biografias.mjs`, só Haiku, toda segunda). 750 de 751 prontas. Revisão em `revisao-biografias.html` com botão Aprovar; correções em `biografias-correcoes.json`.
- **Ficha do parlamentar** em janela que fecha sem perder a lista.
- **Aba Balanço** (produção da direita e da extrema-direita sobre o total, situação das proposições, temas) e **Dossiê do Congresso** na aba Dossiês. Situações em `dados/situacoes.json` (robô diário).
- **Grupos pelas votações** (caminho 3). Câmara pelo modelo de pontos ideais (`robo/posicoes.py`, toda segunda; página `posicoes.html`); Senado pelo partido. Totais em exercício: extrema 120, direita 227, centro 126, esquerda 120, sem partido 1.
- Retiradas as menções aos "Cadernos do Futuro" (usar temas ou assuntos). Seletores corrigidos no celular.
- **Identidade visual** conceito D (Congresso com a linha pontilhada chegando). Arquivos em `imagens/`.
- **Posts para o Instagram** (apresentação, posições, proposições, emendas). O card de emendas do primeiro post tem números antigos (R$ 52,5 bi, 62%, R$ 84,7 bi; atuais R$ 50,5 bi, 59%, R$ 85,4 bi).
- **Cloudflare** Web Analytics ativo. Proteção conferida em 17/11: proxy ligado, SSL Full, Always Use HTTPS e Bot Fight Mode. Com o proxy, o "DNS check" do GitHub Pages falha sempre, o que é esperado. Não usar Full (strict), porque o GitHub não emite certificado próprio com o proxy ligado.

## PLP 299/2026 (ajuste fiscal), análise em andamento
- Dois documentos para a equipe (Claude Docs):
  - "PLP 299/2026 no Congresso: votos, empresas dos parlamentares e benefícios fiscais" — https://claude.ai/artifact/KQxug2ZJvGstyRTMLiNdzi
  - "PLP 299/2026: os 594 parlamentares que votam, suas empresas e os benefícios fiscais" (versão principal, só os 81 senadores e 513 deputados em exercício) — https://claude.ai/artifact/6PhZ8CpqoY6FtkRkZu2m1W
- Dados: votos em `robo/analises/plp299_votos.csv` (urgência 40×38, substitutivo 45×31, 12/11). Extração com `robo/analises/plp299_tudo.py` pelo workflow "Análises avulsas" (cerca de 1 hora). A saída fica no ramo `analises-saida-plp299_tudo` do repositório (os artefatos do GitHub não baixam daqui). Análise local com `robo/analises/plp299_analise.py`.
- Método: sócios do CNPJ (nome civil + 6 dígitos do CPF do TSE), atividade pela consulta pública de CNPJ, benefícios na DIRBI (2024–2026) e ECF (2023+). Compensações por empresa estão sob sigilo fiscal.
- Achados principais: 323 dos 594 são sócios de empresas (932 ativas). No Senado, apoio de 73% entre os sem empresa e 46% entre os com empresa, diferença concentrada na direita. Indústria e comércio têm 78% dos R$ 366,5 bi da DIRBI em 2025. Na Câmara, 70% da direita e 19% da esquerda têm empresa; onze deputados com benefícios, quase todos pelo Perse (Magda Mofatto, R$ 57 mi).
- **Dossiê especial no site** (17/11): `dossies/plp-299-2026.html` e `.pdf`, convertidos do documento principal sem a marca da plataforma, listados em "Dossiês especiais" na página de dossiês. Ao atualizar o documento, refazer a página e o PDF e trocar a linha de versão em `ESPECIAIS`.
- **Próximo passo:** atualizar os dois documentos com o resultado dos destaques de 17/11, sobretudo o do Republicanos (Alan Rick) que retira a restrição às compensações. Depois, a votação na Câmara. Oferecida uma planilha com todas as empresas de cada parlamentar.

## Mídia e parlamentares (17/11)
- **Base da Receita e do TSE no Cloudflare R2** (bucket privado `exterminadores-dados`; segredos `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` no GitHub). Espelho por `robo/analises/receita_r2.py` (CNPJ do mês atual completo, Sócios de mai/2023, TSE 2018/2022/2026; ~9,3 GB, 1h24). Workflow "Espelho no R2" (`.github/workflows/espelho-r2.yml`) roda nos dias 18 e 28; depois de copiar o mês novo inteiro apaga o anterior (mantém os Sócios do mês mais antigo). Índice no ramo `espelho-r2`.
- **Análises avulsas** rodam também quando `robo/analises/fila.txt` muda no main (primeira linha = script), porque o token desta sessão não aciona workflows. Limite de 6 h. O GitHub recusa arquivos acima de 100 MB: saídas grandes vão compactadas (.json.gz).
- `robo/analises/midia3.py` (versão final; midia.py e midia2.py são tentativas anteriores) gera o universo de emissoras e jornais e os cruzamentos; saída no ramo `analises-saida-midia3`. `robo/analises/midia_analise.py <saída> <saída do plp299_tudo>` calcula os vínculos por faixa. A planilha com os vínculos (indícios de parentesco e laranjas) foi entregue ao James na conversa e **não** deve ir para o repositório público.
- Resultado: 50 parlamentares em exercício com vínculo direto, 54 com indireto forte, 28 por sobrenome. Os ramos `analises-saida-midia` e `analises-saida-midia2` são de execuções que travaram e podem ser apagados.
- Gabinetes do Senado: `robo/analises/midia_senado.py` (ramo `analises-saida-midia_senado`); copiar `gabinetes_senado_x_midia.json` para a pasta da saída antes de rodar `midia_analise.py`.

## Bancadas temáticas (18/11)
- Robô `robo/bancadas.py` (sem IA), regras em `bancadas-regras.json`, workflow "Bancadas". Escopo definido pelo James: inclui aliados. Como os familiares importam, a triagem saiu do GitHub e foi para a Cloudflare: Worker `cloudflare/triagem` (workflow "Publicar a triagem"), dados e decisões no R2 (`bancadas/`). Descrição no LEIA-ME.
- Para ligar: o James cria o token de Workers e o segredo `CLOUDFLARE_API_TOKEN`, liga o Access no Worker com os e-mails da equipe e informa o nome da equipe do Zero Trust e a AUD, que vão em `cloudflare/triagem/wrangler.toml` (`ACCESS_TEAM`, `ACCESS_AUD`). Sem isso o Worker responde 503.
- Familiares por enquanto só na mídia (vínculos indiretos do levantamento de mídia). Fase 2: o mesmo cruzamento por setor, e as bases novas: titulares da ANM, lista da Secretaria de Prêmios e Apostas (a MP 1.394/2026 proibiu as apostas de quota fixa), operadoras da ANS, instituições do Banco Central, mantenedoras do e-MEC e doações de campanha de sócios de empresas do setor. Depois, exibir o enquadramento aprovado na ficha do parlamentar.

- Página pública das bancadas retirada do ar em 18/11 a pedido do James até todas estarem operacionais; como recolocar está no LEIA-ME (commit 7597a34).

## Pendências do James
- 2FA no GitHub, Cloudflare e Registro.br e revisão dos tokens dos revisores encaminhadas pelo James em 17/11. Ramo `diag-dns` apagado em 17/11 (esta sessão não consegue apagar ramos; o James apaga pelo site).

## Redes
- Instagram da plataforma: @observatoriodadireita (confirmado em 17/11). O site ainda não traz link para o perfil.

