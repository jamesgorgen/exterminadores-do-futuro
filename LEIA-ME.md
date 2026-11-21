# Os exterminadores do futuro — observatório da direita no Congresso

O que a direita faz no Congresso, todos os dias. Um observatório dos movimentos da direita e da extrema-direita na Câmara e no Senado, a partir dos projetos apresentados e das votações nominais, com os dados oficiais das duas Casas atualizados diariamente.

A versão anterior, da campanha do segundo turno de 2026, está guardada no repositório `exterminadores-arquivo`.

## Como funciona

Um robô roda todo dia às 6h17 (horário de Brasília) no GitHub Actions, de graça para repositórios públicos.

1. Lista os deputados das legislaturas desde 2023 e reconhece os senadores pelos votos e pela autoria.
2. Reúne os projetos de lei (PL, PLP, PEC e PDL) apresentados por deputados e senadores de todos os partidos. Na Câmara, a busca é feita pela autoria de cada deputado. No Senado, quinzena a quinzena, lendo os autores.
   Também reúne os projetos sem autor parlamentar (Poder Executivo, comissões, Mesas, Senado como Casa, tribunais e outros órgãos), que contam na produção legislativa total. Na Câmara, pelos arquivos anuais de proposições e de autores (`proposicoes-AAAA` e `proposicoesAutores-AAAA`), com a API de autores para o que faltar; o ano corrente todo dia e os anteriores uma vez por mês (controle em `estado.json`, campo `semAutor`). No Senado, os projetos sem senador entre os autores. Esses projetos ficam com `a` vazio, `au` (nome do autor) e `ta` (`executivo`, `comissao`, `senado`, `judiciario`, `mp` ou `outro`). Os de rotina recebem `rt` (função `rotinaDe`): `outorga` (atos de outorga, renovação ou anulação de rádio e TV) e `administrativa` (cargos, funções, varas, carreiras e remuneração de servidores das Casas, dos tribunais, do Ministério Público e da Defensoria; escolha de ministro do TCU). Ficam na base, na classificação e na revisão, mas fora da produção do Balanço, contados à parte em `blocos.X.rotina`. Os acordos internacionais contam na produção, porque muitas vezes dividem os grupos.
3. Reúne as votações nominais dos plenários e das comissões. Na Câmara, pelos arquivos anuais completos de votações, votos, orientações e objetos, com a API como reserva. No Senado, pela API de votações de plenário e pela de votações em comissão. Requerimentos (urgência, retirada de pauta), destaques, emendas e pareceres são ligados ao projeto citado na ementa ou na descrição (campo `mp`, função `materiaPrincipal`), e a votação é classificada pela chave desse projeto. Assim a urgência, os destaques e o mérito de um projeto ficam juntos. As votações simbólicas do plenário da Câmara são guardadas à parte, com a matéria e o resultado (a Câmara não publica orientação de bancada para elas).
4. Classifica cada projeto e cada votação pelas pautas de `pautas.js`, com o Claude Haiku. O que já foi classificado não é refeito.
5. Calcula o índice de alinhamento de cada parlamentar e grava tudo na pasta `dados`.

A página (`index.html`) só lê os arquivos da pasta `dados`. Não depende de servidor nem do Worker do Cloudflare.

## Quem é a direita

- **Grupos, definidos pelo partido** (campo `grupos` em `pautas.js`). Extrema-direita reúne PL, Novo e Missão. Direita reúne PP, União Brasil, Republicanos, Podemos e PSD. Centro-direita reúne Cidadania, Avante, Solidariedade, MDB, PRD, PSDB e DC. Esquerda reúne PT, PSOL, PCdoB, PSB, PDT, Rede e PV. Quem não tem partido fica em "Sem partido". A mesma divisão vale para votações, emendas e dossiês.
- **Posição dos blocos numa votação.** A posição da extrema-direita e a da direita são, cada uma, a maioria dos votos Sim e Não do bloco, quando ao menos 60% dele vota no mesmo sentido. A esquerda é a referência do campo do governo, pela mesma regra.
- **Votações disputadas.** Aquelas em que um dos blocos (extrema-direita ou direita) e a esquerda votam em sentidos opostos.
- **Índices.** Cada parlamentar tem um índice com a extrema-direita e outro com a direita, a porcentagem das votações disputadas em que votou como o bloco. Exige ao menos 10 votações disputadas.
- **Em exercício.** A cada execução o robô baixa a lista atual de deputados (Câmara) e de senadores (Senado) e marca quem está no mandato hoje (campo `ex` em `parlamentares.json` e `indice.json`). Votos e projetos de suplentes que já saíram, licenciados e ex-parlamentares continuam valendo para as votações, mas a lista de parlamentares, os totais por grupo e a bancada dos dossiês estaduais contam só quem está em exercício, ou seja, 513 deputados e 81 senadores. Nas emendas, entram todos os autores do período, inclusive quem já deixou o mandato.
- **Vota com a direita.** Parlamentares da centro-direita, da esquerda ou sem partido cujo maior índice chega a 80% recebem o selo "vota com a direita", e de 60% a 80%, "vota próximo da direita" (campo `al` em `indice.json`; o grupo fica em `cl`).

As regras ficam em `pautas.js` (campo `indice`). Mudanças nelas valem a partir da execução seguinte. Mudanças nos grupos exigem uma execução completa, porque a posição do bloco é gravada em cada votação na hora da coleta.

## Pautas e grau

São 16 pautas, listadas em `pautas.js` com a descrição do que entra e do que caracteriza a extrema-direita. Para cada projeto e votação, a IA indica

- se o item faz avançar a pauta da direita (`avanca`), se vai contra ela (`barra`) ou se não trata de nenhuma;
- quais pautas, de uma a três;
- o grau, direita ou extrema-direita, quando o item faz avançar a pauta;
- um motivo curto.

O grau vale para o projeto ou para a votação, e nunca para a pessoa. A classificação lê só a ementa e aparece na página com a marca IA.

Para refazer todas as classificações depois de mudar as pautas, troque `VERSAO_CLASSIFICACAO` em `robo/coletar.mjs` e rode o robô.

O grau passa por uma segunda etapa, com instruções próprias, só para os itens que fazem avançar a pauta da direita. Essa etapa segue os critérios da equipe por tema, revisa as pautas (até três), diz se a IA tem certeza alta ou baixa e recebe como exemplos as correções já feitas pela equipe (até 300). Cada item é lido pelo modelo rápido (`MODELO`). O modelo mais forte (`MODELO_GRAU`) relê só os itens em que o rápido se declara inseguro, e nesses vale a leitura do mais forte. A certeza tem três níveis. É alta quando o modelo rápido está seguro, ou quando o mais forte confirma o grau e está seguro. É "grau" quando os dois veem pauta da direita e a dúvida fica só entre direita e extrema-direita, caso em que a revisão humana é opcional. É baixa, e exige revisão humana, quando há dúvida sobre ser ou não pauta da direita. Um erro 400 da API da Anthropic interrompe a etapa na hora e aparece no registro com a mensagem recebida, o que costuma indicar saldo de créditos esgotado. A cada 100 correções novas (`PASSO_REGRAS`), o modelo mais forte deduz de novo as regras que a equipe aplica, grava em `dados/regras-equipe.json`, e o robô refaz o grau sozinho. Essa reclassificação só refaz os itens sem certeza alta que a equipe ainda não corrigiu (os corrigidos não passam pela IA, porque a correção prevalece) e só acontece uma vez por semana, na execução agendada de segunda-feira, ou quando o robô é disparado à mão com a opção "reclassificar" marcada; nas demais execuções o robô só gradua os itens novos, com as regras já guardadas, para economizar créditos. O arquivo anual de votações da Câmara costuma chegar com atraso, e o robô completa pela API os dias seguintes à última votação do arquivo. Quando o Senado recusa a consulta de um mês de votações, o robô tenta de semana em semana. O workflow manual "Avaliar a triagem" (`robo/avaliar.mjs`) mede a concordância da IA com as correções da equipe e serve para testar mudanças antes de adotá-las. Para refazer apenas o grau à mão, troque `VERSAO_GRAU` em `robo/coletar.mjs`.

Na página de revisão, as filas mostram por padrão só os itens que exigem revisão. Os de dúvida só de grau aparecem ao escolher "Inclui dúvida só de grau". Os de certeza alta vão direto para o site com a marca IA e podem ser vistos escolhendo "Todos, até os de certeza alta". Para medir a taxa de erro desses itens, a opção "Amostra do mês" sorteia 50 projetos e 50 votações de certeza alta (direita e extrema-direita juntas). O sorteio depende só do mês, então é o mesmo para toda a equipe e muda no mês seguinte. A amostra mostra também os itens já conferidos, com a contagem do andamento no topo da lista.

## Arquivos

| Arquivo | Para que serve |
|---|---|
| `index.html` | A página |
| `pautas.js` | Pautas, núcleo e regras do índice |
| `correcoes.json` | Correções da equipe à classificação da IA |
| `revisao.html` | Página de revisão da triagem, para a equipe |
| `dossie.html` | Dossiês para imprimir (parlamentar e estado) |
| `dossies/` | Dossiês especiais (páginas estáticas com o PDF ao lado), listados na lista `ESPECIAIS` de `dossie.html` |
| `emendas.html` | Módulo de emendas parlamentares |
| `robo/emendas.py` | Gera os dados do módulo de emendas |
| `robo/motor.js` | Funções de busca e de classificação por tema, usadas pelo robô |
| `taxonomia.js` | Temas e áreas usados para marcar os assuntos das ementas |
| `robo/coletar.mjs` | O robô de coleta |
| `robo/pdfs.mjs` e `.github/workflows/dossies.yml` | Geram todo dia 1º os dossiês dos 27 estados em PDF e publicam em Releases do repositório; a página de dossiês aponta para o último mês |
| `.github/workflows/atualizar.yml` | O agendamento do robô no GitHub Actions |
| `compartilhar.jpg` | Imagem da prévia do link |
| `CNAME` | Domínio exterminadores.com.br |
| `dados/` | Gerada pelo robô (não edite à mão) |

Na pasta `dados`

| Arquivo | Conteúdo |
|---|---|
| `resumo.json` | Totais e números por pauta |
| `indice.json` | Índice e contagens de cada parlamentar |
| `proposicoes-direita.json` | Projetos que fazem avançar alguma pauta |
| `proposicoes-todas.json` | Todos os projetos em versão leve (ementa resumida, autores, classificação), para a busca da aba Proposições, que abre em "Todos os projetos" e carrega o arquivo só quando a aba é aberta |
| `votacoes-resumo.json` | Todas as votações nominais, sem os votos individuais |
| `votacoes-AAAA.json` | Votações do ano com o voto de cada parlamentar |
| `relatorias.json` | Relatorias do Senado desde 2023: matéria, relator, comissão e datas de designação e de saída. Os relatores em exercício também vão para `rl` em `proposicoes-direita.json` |
| `relatorias-camara.json` | Relatorias da Câmara desde 2023, lidas das tramitações pelo script `robo/relatorias-camara.mjs` (workflow "Relatorias da Câmara", diário): proposição, deputado, órgão, data da designação, data do parecer e se a relatoria está em andamento |
| `votos-disputadas.json` | Voto de cada parlamentar nas votações disputadas, uma letra por votação, usado pelo dossiê parlamentar |
| `proposicoes-AAAA.json` | Todos os projetos do ano, inclusive os do Poder Executivo, de comissões e de outros órgãos (`au`, `ta`) |
| `votacoes-simbolicas-AAAA.json` | Votações simbólicas do plenário da Câmara no ano: matéria e resultado |
| `votacoes-chave.json` | Votações-chave escolhidas pela equipe: para cada matéria, todas as votações ligadas a ela, o placar de cada grupo, a orientação do governo e da oposição e, por parlamentar, uma letra por votação |
| `classificacoes.json` | Classificações já feitas pela IA |
| `parlamentares.json` | Cadastro de deputados e senadores |
| `diagnostico.json` | Amostras dos dados brutos, contagens e erros da última execução. Em `numeracao`, as lacunas na numeração das proposições das últimas duas semanas; muitas de uma vez viram erro, sinal de falha na coleta |
| `estado.json` | Controle interno do robô |
| `verificados.json` | Opcional. Casos conferidos pela equipe, mantidos à mão |

## Publicação

1. **Arquivos.** Suba para o repositório `exterminadores-do-futuro` os arquivos desta pasta. Os arquivos da versão anterior (`config.js`, `promessas.js`, `projetos.json`, `triagens.json` e o `motor.js` da raiz) foram retirados.
2. **Agendamento.** Crie o arquivo `.github/workflows/atualizar.yml`. Pelo site do GitHub, use Add file, Create new file, escreva o caminho completo no nome do arquivo e cole o conteúdo.
3. **Chave da Anthropic.** Em Settings, Secrets and variables, Actions, crie o segredo `ANTHROPIC_API_KEY`.
4. **Primeira execução.** Em Actions, Atualizar dados, Run workflow, escolha `completo`. A primeira execução reúne a legislatura inteira e leva cerca de 20 minutos. As seguintes rodam sozinhas todo dia e levam poucos minutos.

## Emendas parlamentares

A página `emendas.html` mostra para onde os parlamentares destinam as emendas individuais ao Orçamento, de 2023 em diante, em quatro partes. A primeira compara como cada grupo divide o dinheiro. A segunda mostra onze áreas (saúde, transferências especiais Pix, educação, assistência social, urbanismo, agricultura, esporte e lazer, segurança e defesa, cultura, direitos da cidadania e outras funções). A terceira mostra a distribuição por estado e por município, com um mapa dos municípios (malha do IBGE em `dados/municipios.topo.json`), a ficha de cada estado e município e a origem do dinheiro por grupo. O mapa usa os pagamentos a prefeituras, fundos municipais e entidades locais, ligados ao município pelo nome e pela UF, e fica em `dados/emendas-municipios.json`. O valor por habitante dos municípios depende de `dados/populacao-municipios.json`, que o robô tenta baixar do IBGE a cada execução (`robo/populacao.py`). A quarta traz o perfil de cada parlamentar, com municípios, entidades favorecidas e convênios. As áreas são comparadas pela fatia do dinheiro de cada grupo e pela parcela de parlamentares que destinaram algo, e não por médias, porque a cota de emendas é igual dentro de cada Casa e as médias por área são distorcidas por poucos valores altos.

- **Grupos, definidos só pelo partido.** São os mesmos das votações (extrema-direita, direita, centro-direita, esquerda e sem partido). A lista fica no início de `robo/emendas.py` (`GRUPOS`) e precisa acompanhar a de `pautas.js`.
- **Atualização.** O agendamento `.github/workflows/emendas.yml` roda toda segunda-feira, baixa o arquivo de emendas do Portal da Transparência, gera `dados/emendas.json` com `robo/emendas.py` e grava no repositório. Se o download falhar, os dados anteriores continuam no ar. Também pode ser disparado à mão, em Actions, Atualizar emendas, informando outro endereço do arquivo, se for preciso.
- **Ligação dos autores.** Os autores são ligados pelo nome aos parlamentares de `dados/parlamentares.json`, o que cobre cerca de 91% do valor.



O jeito mais simples é a página de revisão, em https://exterminadores.com.br/revisao.html (não aparece no site nem nos buscadores). Ela mostra os projetos e as votações em filas (o que a IA marcou como direita, como extrema-direita, como contra a pauta, o que descartou e o que a equipe já conferiu), com botões para sentido, grau e pautas, um campo de nota e atalhos de teclado. As alterações ficam guardadas no navegador até alguém clicar em Salvar no site, que grava tudo no `correcoes.json` de uma vez.

Para salvar, cada pessoa precisa de uma chave de acesso do GitHub com permissão Contents, Read and write, só neste repositório. A própria página explica como criar, em Acesso ao GitHub. A pessoa precisa ser colaboradora do repositório (Settings, Collaborators).

Também é possível editar o arquivo à mão, como descrito abaixo.

Quando a IA errar, corrija no arquivo `correcoes.json`, na raiz do repositório. Pelo site do GitHub, abra o arquivo, clique no lápis, edite e salve com Commit changes. O robô roda sozinho ao salvar e o site se atualiza em poucos minutos. O item corrigido aparece com o selo "Conferido pela equipe" no lugar de "IA".

A chave é a do projeto (`PL 682/2024`) ou, para votações sem matéria, a da votação (`V:C:2585316-23`). Uma correção de projeto vale também para as votações desse projeto. Todos os campos são opcionais e só substituem o que for informado.

- `s`, sentido. `avanca` (faz avançar a pauta da direita), `barra` (vai contra ela) ou `""` (tira o item da lista).
- `p`, pautas, pelos identificadores de `pautas.js`, por exemplo `["armas"]`.
- `g`, grau. `direita` ou `extrema`.
- `m`, texto que aparece como "Checagem da equipe".
- `lote`, `1` para confirmações em bloco, feitas sem leitura item a item (por exemplo, os 672 projetos contra a pauta de autoria do PT, PSOL e PV confirmados em 18/11/2026). Valem no site com o selo "Classificado por IA", e não "Conferido pela equipe", e ficam fora dos exemplos e da contagem de correções que orientam a IA e do gabarito de `robo/avaliar.mjs`. Quem revisar um desses itens na página de revisão grava uma correção comum, sem a marca.

```json
{ "correcoes": {
  "PL 682/2024": { "s": "barra", "p": ["armas"], "m": "Restringe registros de CACs." },
  "PL 1148/2023": { "s": "" },
  "PL 2289/2025": { "g": "extrema" }
} }
```

Cuidado com as vírgulas e as aspas. Se o arquivo ficar com erro de formato, as correções deixam de valer e o erro aparece em `dados/diagnostico.json`.

## Balanço

`resumo.json` traz o campo `blocos`, calculado por `calcularBlocos` em `robo/coletar.mjs`, com os totais por Casa (`C`, `S`) e somados (`T`). Para cada grupo (extrema, direita, centro, esquerda): projetos pelo primeiro autor (`prop`), projetos com pauta da direita (`pauta`), parlamentares que passaram pelo grupo (`membros`), votações em que o grupo teve maioria definida (`vot`) e em quantas essa maioria ficou do lado vencedor (`venceu`). Também traz, por grupo, os projetos com situação conhecida (`comSit`), aprovados em ao menos uma Casa ou transformados em lei (`aprovada`), transformados em lei (`lei`) e arquivados (`arquivada`), e por tema (`temas`) o total, os aprovados e, por grupo, projetos, aprovados e projetos com pauta da direita. `resumo.json` também leva os nomes dos temas e cadernos (`temas`). Os projetos sem autor parlamentar contam em `prop` e nos demais totais da Casa e aparecem à parte no campo `fora` (projetos, pauta, situação e `tipos`, a contagem por tipo de autor). A aba Balanço do site lê esses números e mostra a linha "Executivo e outros".

## Votações-chave

A equipe escolhe as votações-chave na página de revisão (botão "Marcar como votação-chave" em cada projeto ou votação) ou à mão no campo `votacoesChave` de `correcoes.json`, pela chave da matéria (`"PL 4675/2025": { "t": "título curto", "nota": "por que importa" }`). O robô junta todas as votações ligadas à matéria, nominais e simbólicas, e grava `dados/votacoes-chave.json`. O site mostra as votações-chave na aba Balanço (placar de cada grupo) e na ficha de cada parlamentar (o voto e se acompanhou o governo). Na Câmara, a referência é a orientação oficial do governo; no Senado, que não publica orientações nos dados abertos, é a posição da esquerda.

## Situações das proposições

`robo/situacoes.mjs` (workflow "Situações das proposições", todo dia, sem IA) lê a situação atual de cada proposição nos arquivos anuais de proposições da Câmara e na lista de processos do Senado e grava `dados/situacoes.json`. Cada item traz a categoria (`t` em tramitação, `p` aprovada em ao menos uma Casa, `l` virou lei, `a` arquivada, retirada ou prejudicada), o índice do texto da situação em `descricoes` e a data. A regra que converte o texto em categoria está na função `categoria`.

## Biografias

O script `robo/biografias.mjs` (workflow "Biografias", toda segunda-feira e à mão) escreve a biografia de cada parlamentar do índice. Os fatos vêm da API da Câmara (dados pessoais, profissões, ocupações, mandatos externos, histórico de partidos), da API do Senado (dados, mandatos, formação, profissão, cargos, filiações) e do verbete da Wikipédia em português. O Haiku escreve o texto e o modelo forte refaz só quando o Haiku indica dúvida, em geral sobre a identidade do verbete ou um conflito sobre o mandato atual.

- `dados/biografias.json` guarda, por parlamentar, o texto (`b`), as fontes (`f`), o modelo, a data e uma marca da versão dos dados e das instruções (`h`). Só refaz quando essa marca muda.
- `dados/biografias-amostra.json` guarda a última amostra gerada com a opção "amostra".
- `biografias-correcoes.json`, na raiz, guarda as versões revisadas pela equipe na página `revisao-biografias.html`. Elas prevalecem no site e nunca voltam para a IA.
- O site não mostra fotos dos parlamentares. A ficha leva ao perfil oficial na Câmara ou no Senado.

## Casos verificados

Para destacar casos conferidos pela equipe, crie `dados/verificados.json` neste formato. O robô não mexe nesse arquivo.

```json
{ "casos": {
  "PL 1234/2025": { "chave": "PL 1234/2025", "casa": ["C"], "data": "2025-05-10", "ementa": "Texto da ementa",
    "autores": ["C204554"], "i": 2489123, "nota": "Texto da checagem da equipe",
    "x": { "s": "avanca", "p": ["armas"], "g": "direita" } }
} }
```

## Bancadas temáticas

A triagem do enquadramento dos parlamentares em exercício em dez bancadas (agronegócio, pauta religiosa, segurança e armas, mídia, mineração, setor financeiro, saúde privada, educação privada, bets e apostas e plataformas digitais) fica fora do site público, num Worker da Cloudflare protegido pelo Cloudflare Access, porque mostra vínculos de familiares e terceiros.

- **Robô sem IA.** `robo/bancadas.py` soma, para cada parlamentar e bancada, sinais de vínculo (empresas do próprio parlamentar, bens declarados ao TSE, ocupação declarada e nome de urna e, na mídia, sociedades diretas e vínculos indiretos do levantamento de mídia) e de atuação (projetos e votos classificados nas pautas da bancada, projetos e relatorias sobre o tema, frentes parlamentares da Câmara e emendas). Grava `bancadas/bancadas.json` no bucket privado do R2. Workflow "Bancadas": dias 3 e 17 de cada mês e sempre que mudam as regras ou o robô.
- **Regras** em `bancadas-regras.json`: atividades (CNAE), termos, ocupações, nomes de urna, pautas, frentes, pesos e limites de cada bancada. Os termos são expressões regulares sobre o texto em maiúsculas e sem acentos.
- **Enquadramento.** Núcleo tem vínculo e atuação; aliado tem atuação específica sem vínculo; interesse sem atuação tem vínculo e pouca atuação; dúvida tem sinais fracos ou contraditórios. Votos, parcela de emendas por área e frentes acompanham a ideologia ou são assinados em massa e não bastam sozinhos. Quem atua mais contra a pauta do que a favor, sem vínculo, fica de fora.
- **Página pública (fora do ar).** `bancadas.html` foi retirada do site em 18/11/2026 até todas as bancadas estarem conferidas. Para recolocar: restaurar o arquivo do commit 7597a34 (`git checkout 7597a34 -- bancadas.html`), devolver os links "Bancadas" em `index.html` e `emendas.html` e marcar `"publicar": true` nas bancadas prontas em `bancadas-regras.json`; o robô volta a gravar `dados/bancadas.json` com núcleo e aliados conferidos e evidências públicas do próprio parlamentar.
- **Triagem.** `cloudflare/triagem` (página `index.html` e `worker.js`), publicada pelo workflow "Publicar a triagem" com o segredo `CLOUDFLARE_API_TOKEN`. A equipe entra com o e-mail cadastrado no Access, decide (núcleo, aliado, não pertence, incerto) e marca as votações-chave, que passam a contar em dobro na execução seguinte do robô. Decisões em `bancadas/decisoes.json` no R2, com autor e data, e uma cópia de cada gravação em `bancadas/historico/`.

## Custos

O GitHub Actions é gratuito para repositório público. A IA custa cerca de 2 dólares na primeira execução completa e centavos por dia depois. Vale definir um limite mensal de gasto no console da Anthropic.

## Limites conhecidos

- A classificação lê só a ementa e serve como triagem.
- Votações simbólicas e secretas ficam de fora dos índices, porque não há registro do voto de cada parlamentar. As simbólicas do plenário da Câmara aparecem nas votações-chave só com o resultado; as do Senado não aparecem.
- Nos projetos da Câmara, o partido do autor é o mais recente. Nas votações, é o da data do voto.
- Votações secretas do Senado (autoridades, embaixadores) ficam de fora.
- Se uma consulta ao Senado falhar numa execução completa, a execução diária só refaz os últimos 45 dias. Uma nova execução completa recupera o que faltou.
