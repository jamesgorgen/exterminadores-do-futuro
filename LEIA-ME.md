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

O grau passa por uma segunda etapa, com instruções próprias, só para os itens que fazem avançar a pauta da direita. Para refazer apenas o grau, troque `VERSAO_GRAU` em `robo/coletar.mjs`.

## Arquivos

| Arquivo | Para que serve |
|---|---|
| `index.html` | A página |
| `pautas.js` | Pautas, núcleo e regras do índice |
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
