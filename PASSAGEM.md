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
- **Cloudflare** Web Analytics ativo. Passo a passo de proteção entregue (proxy, SSL Full, Always Use HTTPS, Bot Fight Mode), a cargo do James.

## PLP 299/2026 (ajuste fiscal), análise em andamento
- Dois documentos para a equipe (Claude Docs):
  - "PLP 299/2026 no Congresso: votos, empresas dos parlamentares e benefícios fiscais" — https://claude.ai/artifact/KQxug2ZJvGstyRTMLiNdzi
  - "PLP 299/2026: os 594 parlamentares que votam, suas empresas e os benefícios fiscais" (versão principal, só os 81 senadores e 513 deputados em exercício) — https://claude.ai/artifact/6PhZ8CpqoY6FtkRkZu2m1W
- Dados: votos em `robo/analises/plp299_votos.csv` (urgência 40×38, substitutivo 45×31, 12/11). Extração com `robo/analises/plp299_tudo.py` pelo workflow "Análises avulsas" (cerca de 1 hora). A saída fica no ramo `analises-saida-plp299_tudo` do repositório (os artefatos do GitHub não baixam daqui). Análise local com `robo/analises/plp299_analise.py`.
- Método: sócios do CNPJ (nome civil + 6 dígitos do CPF do TSE), atividade pela consulta pública de CNPJ, benefícios na DIRBI (2024–2026) e ECF (2023+). Compensações por empresa estão sob sigilo fiscal.
- Achados principais: 323 dos 594 são sócios de empresas (932 ativas). No Senado, apoio de 73% entre os sem empresa e 46% entre os com empresa, diferença concentrada na direita. Indústria e comércio têm 78% dos R$ 366,5 bi da DIRBI em 2025. Na Câmara, 70% da direita e 19% da esquerda têm empresa; onze deputados com benefícios, quase todos pelo Perse (Magda Mofatto, R$ 57 mi).
- **Próximo passo:** atualizar os dois documentos com o resultado dos destaques de 17/11, sobretudo o do Republicanos (Alan Rick) que retira a restrição às compensações. Depois, a votação na Câmara. Oferecida uma planilha com todas as empresas de cada parlamentar.

## Pendências do James
- Proteção no Cloudflare, 2FA no GitHub, Cloudflare e Registro.br, revisar os tokens dos revisores, apagar o ramo `diag-dns`.
- Confirmar o perfil do Instagram (@exterminadoresdofuturo, presumido).

