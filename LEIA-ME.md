# Os exterminadores do futuro

Flávio diz uma coisa e propõe outra. A página põe lado a lado trechos literais do programa de governo de Flávio Bolsonaro e os projetos que ele e seus aliados apresentam no Congresso.

Projetos defendidos pelos parlamentares conservadores e reacionários no Brasil organizados por temas que ameaçam nossos direitos e do Brasil.

A ferramenta reúne os projetos apresentados por PL, Novo, PP, União Brasil, Podemos e Republicanos (inclusive com a sigla antiga PRB) na Câmara e no Senado e os classifica pelos temas dos Cadernos do Futuro do Brasil.

## Arquivos

| Arquivo | Para que serve |
|---|---|
| `index.html` | A página da ferramenta |
| `motor.js` | Consulta as APIs, filtra por partido e classifica as ementas |
| `promessas.js` | Trechos do programa de Flávio, com página, e os temas onde a prática aparece |
| `taxonomia.js` | Temas e termos usados na classificação (é aqui que se ajustam os termos) |
| `config.js` | Endereço do serviço intermediário |
| `triagens.json` | Triagens e avaliações já feitas, publicadas junto com a página (gerado pelo modo de administração) |
| `worker.js` | Serviço intermediário para o Cloudflare Workers |

## Publicação

1. **Serviço intermediário no Cloudflare.** O Worker se chama `exterminadores-proxy`. Cole nele o conteúdo de `worker.js` e publique. A lista `ORIGENS_PERMITIDAS` já contém o exterminadores.com.br e, durante a transição, os endereços antigos (lulafezefara.com.br e GitHub Pages).
2. **Chave da Anthropic.** Em Settings, Variables and Secrets, cadastre `ANTHROPIC_API_KEY` como Secret.
3. **Banco D1.** Veja a seção seguinte.
4. **Página.** Suba `index.html`, `motor.js`, `taxonomia.js`, `promessas.js`, `config.js`, `triagens.json` e `CNAME` para a raiz do repositório `exterminadores-do-futuro`, que publica o exterminadores.com.br pelo GitHub Pages. Depois de publicar, recarregue com Ctrl+Shift+R.

## Banco D1 (armazenamento permanente das triagens)

Triagens e avaliações ficam guardadas num banco D1 do próprio Cloudflare. Ele é único para o mundo todo e não expira, então o que uma pessoa triou serve a todos os visitantes, em qualquer cidade, sem nova chamada à IA. O volume da ferramenta cabe com folga no plano gratuito.

Para ligar o banco, uma vez só.

1. No painel do Cloudflare, abra **Storage & Databases**, depois **D1 SQL Database**, e clique em **Create**. Dê o nome `exterminadores` e confirme.
2. Abra o Worker `exterminadores-proxy`, vá em **Settings**, depois **Bindings**, e clique em **Add**. Escolha **D1 database**, escreva `DB` (maiúsculo) como nome da variável e selecione o banco `exterminadores`. Salve e publique (Deploy).
3. Abra a página com `?admin` no fim do endereço (https://exterminadores.com.br/?admin). A faixa amarela de administração deve dizer que o banco do Worker está ligado.

As tabelas são criadas sozinhas na primeira chamada. Não é preciso rodar nenhum comando. Sem o banco, o Worker continua funcionando com o cache local do Cloudflare, como antes, mas esse cache vale só para o data center de quem triou e pode ser apagado a qualquer momento.

Triagens antigas que ainda estiverem nesse cache local passam para o banco automaticamente quando alguém pede a triagem do mesmo projeto.

## Triagens publicadas e modo de administração

A página procura as triagens já feitas em três lugares, nesta ordem.

1. **`triagens.json`**, publicado na mesma pasta da página. É o estoque principal. Qualquer visitante já abre a legislatura triada sem nenhuma chamada ao Worker para isso.
2. **Banco do Worker.** Depois de cada busca, a página pergunta ao Worker, pela rota `/consultar`, o que já foi triado por qualquer pessoa e ainda não está no arquivo. Essa consulta não chama a IA e não custa créditos.
3. **Navegador de quem triou.** O que cada pessoa tria fica também no navegador dela, como reserva.

O botão de triagem só manda à IA o que não estiver em nenhum desses lugares.

**Para atualizar o `triagens.json`.** Abra a página com `?admin` no endereço. A faixa de administração mostra quantas triagens estão no arquivo publicado, no banco e no seu navegador. O botão **Exportar triagens.json** junta tudo (banco, arquivo publicado e navegador) e baixa um arquivo novo. Suba esse arquivo para a raiz do repositório no GitHub, no lugar do anterior. Vale repetir isso de tempos em tempos para incorporar os projetos novos.

O arquivo traz uma triagem por linha, então o histórico do GitHub mostra exatamente o que entrou a cada atualização.

**Versão do critério.** O arquivo só é aceito se a versão gravada nele for igual à constante `VERSAO_TRIAGEM` do `index.html` (hoje `t7`). Ao mudar o critério da triagem, troque `VERSAO_TRIAGEM` no `worker.js` e no `index.html`, rode as triagens de novo e exporte um novo arquivo. O mesmo vale para `VERSAO_AVALIACAO`.

## Como a busca funciona

- **Câmara.** Usa o filtro de partido do autor da própria API, ano a ano, e aplica o recorte de datas na própria página, porque a API não conclui buscas por partido com intervalo de datas. A API também recusa o filtro para a sigla UNIÃO, então nesse caso a ferramenta lista os deputados do partido e busca pela autoria de cada um. Nesse caminho vale o partido atual do deputado, e o resultado aparece marcado.
- **Senado.** A API não filtra por partido. A ferramenta baixa todas as proposições do período quinzena a quinzena e lê a sigla registrada na autoria, que é a do momento da apresentação. Projetos vindos da Câmara são descartados para não duplicar.
- **Temas.** Cada ementa é comparada com os termos da taxonomia. Acentos e maiúsculas não importam, e o termo encontra variações de até três letras no fim. Siglas curtas (IA, SUS, CAR) valem só como palavra inteira em maiúsculas. Termos iniciados por `=` valem só como palavra exata.
- **Cache.** O Worker guarda cada resposta das APIs do Congresso por seis horas. Buscas repetidas ficam rápidas e aliviam as APIs.

## Flávio promete, mas olha

Cada área tem cartões com um trecho literal do programa de Flávio e a página do documento. Depois da busca, cada cartão mostra quantos projetos do PL e aliados tratam do mesmo assunto, e o botão Ver os projetos filtra a lista e abre a faixa de contraste. Projetos em que o próprio Flávio é autor recebem um selo amarelo, e a opção Mostrar só projetos de autoria do próprio Flávio Bolsonaro isola esses projetos (ele é senador, então é preciso incluir o Senado e o PL na busca).

A contagem mostra que o campo dele legisla sobre aquele assunto, e não que cada projeto contradiz a promessa. Antes de divulgar um caso, leia a ementa e peça a avaliação do texto integral.

Para trocar uma promessa, edite `promessas.js` mantendo o trecho literal e a página, e atualize também `PROMESSAS_FLAVIO` no `worker.js`.

## Triagem por IA pelas ementas

A triagem serve para encontrar o que o programa de Flávio contradiz ou esconde do eleitor. Ela não destaca projetos bons.

Depois da busca, o botão de triagem manda ao Worker as ementas dos projetos da lista atual que ainda não foram triados (com os filtros escolhidos, ligados a algum tema e sem homenagens), em lotes de 25. O Claude Haiku 5.5 (`MODELO_TRIAGEM` no `worker.js`) faz dois julgamentos.

- **Efeito negativo.** Se o projeto tem efeito negativo, efeito a conferir ou nenhum efeito negativo aparente, e qual dos 74 temas da taxonomia é o mais atingido (constante `TEMAS`, que deve acompanhar o `taxonomia.js`). A régua é a síntese das diretrizes dos Cadernos do Futuro (constante `REFERENCIA`), usada sem citação.
- **O que o programa de Flávio diz.** Se o projeto contradiz uma promessa do programa, trata de algo que o programa omite ou faz o que o programa declara abertamente. A comparação usa a estrutura do programa (`PROGRAMA_FLAVIO`) e as promessas literais com página (`PROMESSAS_FLAVIO`, as mesmas de `promessas.js`). Nas contradições, o motivo cita a promessa e a página.

A tabela cruza as sete áreas (efeito negativo) e o efeito a conferir com as três colunas (contradiz, omitido, declarado). Cada projeto conta uma única vez. Os projetos sem efeito negativo aparente ficam fora da tabela, com um atalho para vê-los. Clicar numa célula, linha ou coluna filtra a lista, e os cartões das promessas e a planilha acompanham.

- As instruções fixas vão com cache no pedido à Anthropic, o que reduz o custo dos lotes seguintes.
- Cada projeto é triado uma única vez e fica guardado no banco D1 sem prazo de validade.
- O custo é da ordem de um décimo de centavo de dólar por lote de 25 ementas.

## Avaliação por IA dos projetos marcados

Depois da busca, marque os projetos que interessam e clique em Avaliar. O Worker lê o texto integral oficial de cada projeto (o PDF da Câmara ou do Senado) e pede ao Claude Sonnet 5.5 uma avaliação à luz dos Cadernos do Futuro, com posição (conflita, converge, misto ou neutro), resumo do que o projeto faz de fato, efeitos, diretrizes envolvidas, trecho de apoio e pontos a conferir antes de divulgar.

- Cada avaliação fica guardada no banco D1 e entra no `triagens.json` na próxima exportação, então avaliar de novo o mesmo projeto não gera custo e a avaliação aparece para todos os visitantes.
- O limite é de 40 avaliações por hora por pessoa e 15 por clique.
- Cada avaliação custa de 2 a 7 centavos de dólar, umas cinquenta vezes mais que a triagem de uma ementa.
- A síntese das diretrizes usada como régua está no próprio `worker.js` (constante `REFERENCIA`). Para ajustar o critério, edite esse texto e mude `VERSAO_AVALIACAO` no `worker.js` e no `index.html`.
- Como a página é pública, qualquer visitante pode pedir triagens e avaliações com a sua chave. Vale definir um limite mensal de gasto no console da Anthropic.

## Rotas do Worker

| Rota | O que faz | Usa a IA |
|---|---|---|
| `GET /?url=` | Repassa consultas às APIs da Câmara e do Senado | Não |
| `POST /triar` | Tria até 25 ementas, devolvendo de graça as já triadas | Só para as novas |
| `POST /avaliar` | Avalia o texto integral de um projeto | Só se ainda não avaliado |
| `POST /consultar` | Devolve as triagens e avaliações guardadas | Não |
| `GET /exportar` | Devolve tudo o que está no banco, para o `triagens.json` | Não |
| `GET /estado` | Diz se o banco está ligado e quanto guarda | Não |

## Para ajustar a taxonomia

Edite `taxonomia.js`. Cada tema tem `termos` (o que procurar) e `excluir` (o que descarta o tema quando aparece). Se mudar os identificadores dos temas, atualize também a lista `TEMAS` no `worker.js`. Depois de salvar e publicar, a aba Temas e termos da própria página mostra a versão em uso.

## Limites conhecidos

- A classificação lê apenas a ementa. Serve como triagem e não substitui a leitura do texto.
- Coautorias de partidos diferentes fazem a proposição aparecer em mais de um partido.
- Períodos longos geram centenas de consultas. A legislatura inteira pode levar alguns minutos na primeira vez.
