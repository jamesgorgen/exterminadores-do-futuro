# Passagem de sessão (17/11/2026, com acréscimo de 21/11)

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

- 21/11: triagem da bancada de plataformas digitais concluída pela equipe (49 parlamentares: 26 núcleo, 23 aliados; 39 deputados e 10 senadores). Segue fora do site por decisão do James; os totais, sem nomes, saem pela análise avulsa `robo/analises/bancada_card.py` (variáveis BANCADA e VOTACAO).
- 21/11, noite: (1) 529 votações da Câmara sem matéria recuperadas pela API (a urgência do PL 2630/2020, de 25/04/2023, estava sem matéria e sem classificação); (2) votações-chave do site: PL 2630/2020 e PL 2338/2023 (este sem votação nominal até agora); (3) decisões da equipe mantidas quando a regra deixa de apontar a pessoa (6 casos na bancada de plataformas, que passa a 55); (4) aba "Votam com a bancada" na triagem. Decidido pelo James: urgências valem como votações-chave das bancadas quando o projeto não teve votação de mérito, e o mínimo caiu para 2; marcadas em plataformas as urgências do PL 2630 e do PL 4675 (voto esperado: não), pela análise `bancada_marcar_chave.py`. Ocupação do TSE não serve para influenciadores (lista fechada, sem a categoria).
- Página pública das bancadas retirada do ar em 18/11 a pedido do James até todas estarem operacionais; como recolocar está no LEIA-ME (commit 7597a34).

## Projetos do Executivo, votações ligadas e votações-chave (21/11)
- Motivo: o PL 4675/2025 (Mercados Digitais, do Poder Executivo) não aparecia na revisão, porque o robô só coletava projetos de parlamentares. A urgência dele (18/03/2026, 276 a 186) estava na base como REQ 4612/2025.
- `robo/coletar.mjs` agora coleta os projetos sem autor parlamentar (Executivo, comissões, Senado como Casa, tribunais, outros órgãos) e eles **contam na produção legislativa** (decisão do James). Campos `au` e `ta`; no Balanço, linha "Executivo e outros" e campo `fora` em `resumo.blocos`.
- Requerimentos, destaques e emendas ficam sob a matéria principal (`mp`, `materiaPrincipal`). 1.266 votações passaram a ficar ligadas a um projeto. A classificação da votação é a do projeto.
- Votações-chave: campo `votacoesChave` em `correcoes.json` (já com PL 4675/2025 e PLP 299/2026), botão na revisão, saída `dados/votacoes-chave.json`, seção no Balanço e na ficha do parlamentar.
- Votações simbólicas do plenário da Câmara em `dados/votacoes-simbolicas-AAAA.json`, com matéria e resultado. Conferido com os dados reais em 21/11: a Câmara não publica orientação de bancada nas simbólicas.
- Correção de 21/11: projetos de senador que chegam à Câmara ("Senado Federal - Fulano") e autores "(S/Partido/AP)" no Senado eram tratados como sem autor parlamentar; 30 projetos voltaram para os senadores.
- A primeira execução depois disso lê o Senado desde 2023 e os arquivos da Câmara de todos os anos; demora mais e classifica algumas centenas de itens novos com a IA.
- Proposições de rotina sem autor parlamentar ficam fora da produção (decisão do James, 21/11): outorgas de rádio e TV (2.313, quase todas da Comissão de Comunicação) e pautas administrativas (33). Os acordos internacionais (118) contam na produção, por decisão do James, porque muitas vezes dividem os grupos. Campo `rt`. Possível uso: cruzar as outorgas com os vínculos de mídia.
- Aba Proposições abre em "Todos os projetos" (`dados/proposicoes-todas.json`, versão leve); busca aceita "4.675". Projeto e votações ligados nos dois sentidos (botões nos cartões, endereços `?p=` e `?vm=`).
- A Câmara adiou o PL 4675/2025 para 27/11. Quando o mérito for votado, entra sozinho na votação-chave.

## Pendências do James
- 2FA no GitHub, Cloudflare e Registro.br e revisão dos tokens dos revisores encaminhadas pelo James em 17/11. Ramo `diag-dns` apagado em 17/11 (esta sessão não consegue apagar ramos; o James apaga pelo site).

## Redes
- Instagram da plataforma: @observatoriodadireita (confirmado em 17/11). O site ainda não traz link para o perfil.

