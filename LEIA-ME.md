# Os exterminadores do futuro — observatório da direita no Congresso

O que a direita faz no Congresso, todos os dias. Um observatório dos movimentos da direita e da extrema-direita na Câmara e no Senado, a partir dos projetos apresentados e das votações nominais, com os dados oficiais das duas Casas atualizados diariamente.

A versão anterior, da campanha do segundo turno de 2026, está guardada no repositório `exterminadores-arquivo`.

## Como funciona

Um robô roda todo dia às 6h17 (horário de Brasília) no GitHub Actions, de graça para repositórios públicos.

1. Lista os deputados das legislaturas desde 2023 e reconhece os senadores pelos votos e pela autoria.
2. Reúne os projetos de lei (PL, PLP, PEC e PDL) apresentados por deputados e senadores de todos os partidos. Na Câmara, a busca é feita pela autoria de cada deputado. No Senado, quinzena a quinzena, lendo os autores.
3. Reúne as votações nominais dos plenários e das comissões. Na Câmara, pelos arquivos anuais completos de votações, votos, orientações e objetos, com a API como reserva. No Senado, pela API de votações de plenário e pela de votações em comissão.
4. Classifica cada projeto e cada votação pelas pautas de `pautas.js`, com o Claude Haiku. O que já foi classificado não é refeito.
5. Calcula o índice de alinhamento de cada parlamentar e grava tudo na pasta `dados`.

A página (`index.html`) só lê os arquivos da pasta `dados`. Não depende de servidor nem do Worker do Cloudflare.

## Quem é a direita

- **Núcleo.** Parlamentares de PL, Novo, PP, União Brasil, Republicanos e Podemos (lista `nucleo` em `pautas.js`).
- **Posição da direita numa votação.** A maioria dos votos Sim e Não do núcleo, quando ao menos 60% dele vota no mesmo sentido. O PT é a referência do campo do governo, pela mesma regra.
- **Votações disputadas.** Aquelas em que a direita e o PT votam em sentidos opostos.
- **Índice de alinhamento.** Porcentagem das votações disputadas em que o parlamentar votou como a direita. Exige ao menos 10 votações disputadas.
- **Alinhados e próximos.** Parlamentares de outros partidos com índice de 80% ou mais (alinhados) ou de 60% a 80% (próximos).

As regras ficam em `pautas.js` (campo `indice`). Mudanças nelas valem a partir da execução seguinte. Mudanças no núcleo exigem uma execução completa, porque a posição do bloco é gravada em cada votação na hora da coleta.

## Pautas e grau

São 16 pautas, listadas em `pautas.js` com a descrição do que entra e do que caracteriza a extrema-direita. Para cada projeto e votação, a IA indica

- se o item faz avançar a pauta da direita (`avanca`), se vai contra ela (`barra`) ou se não trata de nenhuma;
- quais pautas, de uma a três;
- o grau, direita ou extrema-direita, quando o item faz avançar a pauta;
- um motivo curto.

O grau vale para o projeto ou para a votação, e nunca para a pessoa. A classificação lê só a ementa e aparece na página com a marca IA.

Para refazer todas as classificações depois de mudar as pautas, troque `VERSAO_CLASSIFICACAO` em `robo/coletar.mjs` e rode o robô.

O grau passa por uma segunda etapa, com instruções próprias, só para os itens que fazem avançar a pauta da direita. Essa etapa segue os critérios da equipe por tema, revisa as pautas (até três), diz se a IA tem certeza alta ou baixa e recebe como exemplos as correções já feitas pela equipe (até 150). A cada 30 correções novas, o robô refaz o grau sozinho, para que a IA aprenda com a equipe. Para refazer apenas o grau à mão, troque `VERSAO_GRAU` em `robo/coletar.mjs`.

Na página de revisão, as filas mostram por padrão só os itens de certeza baixa. Os de certeza alta vão direto para o site com a marca IA e podem ser vistos escolhendo "Certeza alta e baixa".

## Arquivos

| Arquivo | Para que serve |
|---|---|
| `index.html` | A página |
| `pautas.js` | Pautas, núcleo e regras do índice |
| `correcoes.json` | Correções da equipe à classificação da IA |
| `revisao.html` | Página de revisão da triagem, para a equipe |
| `emendas.html` | Módulo de emendas parlamentares |
| `robo/emendas.py` | Gera os dados do módulo de emendas |
| `robo/motor.js` | Funções de busca e de classificação por tema, usadas pelo robô |
| `taxonomia.js` | Temas dos Cadernos do Futuro, usados para marcar os temas das ementas |
| `robo/coletar.mjs` | O robô de coleta |
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
| `votacoes-resumo.json` | Todas as votações nominais, sem os votos individuais |
| `votacoes-AAAA.json` | Votações do ano com o voto de cada parlamentar |
| `proposicoes-AAAA.json` | Todos os projetos do ano |
| `classificacoes.json` | Classificações já feitas pela IA |
| `parlamentares.json` | Cadastro de deputados e senadores |
| `diagnostico.json` | Amostras dos dados brutos, contagens e erros da última execução |
| `estado.json` | Controle interno do robô |
| `verificados.json` | Opcional. Casos conferidos pela equipe, mantidos à mão |

## Publicação

1. **Arquivos.** Suba para o repositório `exterminadores-do-futuro` os arquivos desta pasta. Os arquivos da versão anterior (`config.js`, `promessas.js`, `projetos.json`, `triagens.json` e o `motor.js` da raiz) foram retirados.
2. **Agendamento.** Crie o arquivo `.github/workflows/atualizar.yml`. Pelo site do GitHub, use Add file, Create new file, escreva o caminho completo no nome do arquivo e cole o conteúdo.
3. **Chave da Anthropic.** Em Settings, Secrets and variables, Actions, crie o segredo `ANTHROPIC_API_KEY`.
4. **Primeira execução.** Em Actions, Atualizar dados, Run workflow, escolha `completo`. A primeira execução reúne a legislatura inteira e leva cerca de 20 minutos. As seguintes rodam sozinhas todo dia e levam poucos minutos.

## Emendas parlamentares

A página `emendas.html` mostra para onde os parlamentares destinam as emendas individuais ao Orçamento, de 2023 em diante, em quatro partes. A primeira compara como cada grupo divide o dinheiro. A segunda mostra onze áreas (saúde, transferências especiais Pix, educação, assistência social, urbanismo, agricultura, esporte e lazer, segurança e defesa, cultura, direitos da cidadania e outras funções). A terceira mostra a distribuição por estado, com mapa, valor por habitante (Censo 2022) e a origem do dinheiro por grupo. A quarta traz o perfil de cada parlamentar, com municípios, entidades favorecidas e convênios. As áreas são comparadas pela fatia do dinheiro de cada grupo e pela parcela de parlamentares que destinaram algo, e não por médias, porque a cota de emendas é igual dentro de cada Casa e as médias por área são distorcidas por poucos valores altos.

- **Grupos, definidos só pelo partido.** Extrema-direita reúne PL, Novo e Missão. Direita reúne PP, União Brasil, Republicanos, Podemos, PSD, Cidadania e Solidariedade. Alinhados reúne MDB, PDT, Rede, PSB e PV. Esquerda reúne PT, PSOL e PCdoB. Outros partidos reúne os demais (PSDB, Avante, PRD e sem partido). A lista fica no início de `robo/emendas.py` (`GRUPOS`) e vale só para este módulo.
- **Atualização.** O agendamento `.github/workflows/emendas.yml` roda todo dia 7, baixa o arquivo de emendas do Portal da Transparência, gera `dados/emendas.json` com `robo/emendas.py` e grava no repositório. Se o download falhar, os dados anteriores continuam no ar. Também pode ser disparado à mão, em Actions, Atualizar emendas, informando outro endereço do arquivo, se for preciso.
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

```json
{ "correcoes": {
  "PL 682/2024": { "s": "barra", "p": ["armas"], "m": "Restringe registros de CACs." },
  "PL 1148/2023": { "s": "" },
  "PL 2289/2025": { "g": "extrema" }
} }
```

Cuidado com as vírgulas e as aspas. Se o arquivo ficar com erro de formato, as correções deixam de valer e o erro aparece em `dados/diagnostico.json`.

## Casos verificados

Para destacar casos conferidos pela equipe, crie `dados/verificados.json` neste formato. O robô não mexe nesse arquivo.

```json
{ "casos": {
  "PL 1234/2025": { "chave": "PL 1234/2025", "casa": ["C"], "data": "2025-05-10", "ementa": "Texto da ementa",
    "autores": ["C204554"], "i": 2489123, "nota": "Texto da checagem da equipe",
    "x": { "s": "avanca", "p": ["armas"], "g": "direita" } }
} }
```

## Custos

O GitHub Actions é gratuito para repositório público. A IA custa cerca de 2 dólares na primeira execução completa e centavos por dia depois. Vale definir um limite mensal de gasto no console da Anthropic.

## Limites conhecidos

- A classificação lê só a ementa e serve como triagem.
- Votações simbólicas e secretas ficam de fora, porque não há registro do voto de cada parlamentar.
- Nos projetos da Câmara, o partido do autor é o mais recente. Nas votações, é o da data do voto.
- Votações secretas do Senado (autoridades, embaixadores) ficam de fora.
- Se uma consulta ao Senado falhar numa execução completa, a execução diária só refaz os últimos 45 dias. Uma nova execução completa recupera o que faltou.
