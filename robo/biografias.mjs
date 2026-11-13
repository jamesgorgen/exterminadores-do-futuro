// Biografias dos parlamentares.
//
// Os fatos vêm só de fontes públicas: a API da Câmara, a API do Senado e o verbete da Wikipédia em português.
// O modelo leve (Haiku) escreve um texto curto a partir desses dados, sem acrescentar nada.
// Quando ele indica dúvida (por exemplo, um verbete que pode ser de um homônimo), o modelo mais forte refaz o texto.
//
// Uma biografia só é refeita quando os dados de origem mudam, e nunca quando a equipe a corrigiu à mão (eq: 1).
//
// AMOSTRA=10 gera só uma amostra variada, gravada em dados/biografias-amostra.json, para avaliar o tom.
// IDS=C220654,S5672 limita a geração a esses parlamentares.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const RAIZ = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const DADOS = process.env.DADOS || path.join(RAIZ, 'dados');
const API_CAMARA = 'https://dadosabertos.camara.leg.br/api/v2';
const API_SENADO = 'https://legis.senado.leg.br/dadosabertos';
const WIKI = 'https://pt.wikipedia.org/w/api.php';
const MODELO = 'claude-haiku-5-5';
const MODELO_FORTE = 'claude-opus-5-5';
const AMOSTRA = +(process.env.AMOSTRA || 0);
const IDS = String(process.env.IDS || '').split(',').map(s => s.trim()).filter(Boolean);
const ARQ = path.join(DADOS, AMOSTRA ? 'biografias-amostra.json' : 'biografias.json');
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
const espera = ms => new Promise(r => setTimeout(r, ms));
const conta = { haiku: 0, forte: 0, tokens_in: 0, tokens_out: 0, sem_wiki: 0, falhas: 0 };

async function pegar(url, tipo = 'json') {
  for (let t = 1; t <= 4; t++) {
    try {
      const r = await fetch(url, { headers: { accept: 'application/json', 'user-agent': 'exterminadores-do-futuro (observatório; contato@exterminadores.com.br)' }, signal: AbortSignal.timeout(45000) });
      if (r.status === 404) return null;
      if (r.ok) return tipo === 'json' ? await r.json() : await r.text();
    } catch (e) {}
    await espera(1500 * t * t);
  }
  return null;
}

// Tira do JSON das APIs o que não é fato biográfico (endereços, códigos internos, metadados) e encurta.
function compactar(x, prof = 0) {
  if (Array.isArray(x)) return x.slice(0, 40).map(v => compactar(v, prof + 1)).filter(v => v !== undefined);
  if (x && typeof x === 'object') {
    const o = {};
    for (const [k, v] of Object.entries(x)) {
      if (/^(uri|url|id$|cod|codigo|email|telefone|gabinete|foto|glossario|metadados|links|versao|noticia|predio|sala|andar|fax|site|redeSocial|ideCadastro)/i.test(k)) continue;
      const c = compactar(v, prof + 1);
      if (c === undefined || c === '' || (typeof c === 'object' && !Object.keys(c).length)) continue;
      o[k] = c;
    }
    return o;
  }
  if (x === null || x === undefined) return undefined;
  return typeof x === 'string' ? x.slice(0, 300) : x;
}

async function dadosCamara(id) {
  const [d, prof, ocup, mand, hist] = await Promise.all(['', '/profissoes', '/ocupacoes', '/mandatosExternos', '/historico']
    .map(s => pegar(`${API_CAMARA}/deputados/${id}${s}`)));
  if (!d || !d.dados) return null;
  // O histórico repete o mesmo partido a cada mudança de situação. Fica só a sequência de partidos, com a data da troca.
  const partidos = [];
  for (const h of ((hist && hist.dados) || []).sort((a, b) => String(a.dataHora).localeCompare(String(b.dataHora)))) {
    if (!partidos.length || partidos[partidos.length - 1].partido !== h.siglaPartido) partidos.push({ partido: h.siglaPartido, desde: String(h.dataHora).slice(0, 10), legislatura: h.idLegislatura });
  }
  return compactar({
    deputado: d.dados, profissoes: prof && prof.dados, ocupacoes_anteriores: ocup && ocup.dados,
    mandatos_fora_da_camara: mand && mand.dados, partidos_na_camara: partidos
  });
}

async function dadosSenado(cod) {
  const partes = { '': 'senador', '/mandatos': 'mandatos', '/historicoAcademico': 'formacao', '/profissao': 'profissao', '/cargos': 'cargos_no_senado', '/filiacoes': 'filiacoes_partidarias' };
  const res = await Promise.all(Object.keys(partes).map(s => pegar(`${API_SENADO}/senador/${cod}${s}.json`)));
  if (!res[0]) return null;
  const o = {}; Object.values(partes).forEach((n, i) => { if (res[i]) o[n] = res[i]; });
  return compactar(o);
}

// Verbete da Wikipédia: procura pelo nome parlamentar e confere que o texto fala de um político.
async function verbete(p) {
  const cargo = p.c === 'S' ? 'senador' : 'deputado federal';
  const busca = await pegar(`${WIKI}?action=query&list=search&format=json&srlimit=5&srsearch=${encodeURIComponent(`${p.n} ${cargo}`)}`);
  const achados = ((busca && busca.query && busca.query.search) || []);
  const normal = s => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const partesNome = normal(p.n).split(/\s+/).filter(w => w.length > 2 && !/^(delegad|capitao|coronel|pastor|general|sargento|cabo|doutor|dr\.|professor|bispo|missionari|tenente|major|soldado|subtenente|delegada|pastora|professora|doutora|deputad)/.test(w));
  for (const a of achados) {
    const t = normal(a.title);
    if (!partesNome.length || !partesNome.some(w => t.includes(w))) continue;
    const j = await pegar(`${WIKI}?action=query&prop=extracts|info&inprop=url&explaintext=1&redirects=1&format=json&titles=${encodeURIComponent(a.title)}`);
    const pg = j && j.query && Object.values(j.query.pages || {})[0];
    const texto = pg && pg.extract ? String(pg.extract) : '';
    if (!/deputad|senador|vereador|prefeit|pol[ií]tic/i.test(texto.slice(0, 1500))) continue;
    // Seções que não ajudam numa biografia curta.
    const limpo = texto.split(/\n==+ *(Refer[êe]ncias|Liga[çc][õo]es externas|Ver tamb[ée]m|Notas|Bibliografia) *==+/)[0];
    return { titulo: pg.title, url: pg.fullurl, texto: limpo.slice(0, 7000) };
  }
  return null;
}

const INSTRUCOES = `Você escreve biografias curtas de parlamentares brasileiros para um observatório do Congresso.

Regras
1. Use somente os fatos presentes nos DADOS. Não acrescente nada que você saiba por conta própria, nem datas, cargos, partidos ou parentescos.
2. Os dados oficiais (Câmara ou Senado) prevalecem sobre a Wikipédia quando houver conflito.
3. O verbete da Wikipédia pode ser de um homônimo. Use-o só se data ou local de nascimento, partido, estado ou cargos baterem com os dados oficiais. Se não tiver certeza de que é a mesma pessoa, ignore o verbete e marque c como "baixa".
4. Escreva de três a cinco frases, em português, em terceira pessoa, nesta ordem: origem (nascimento e cidade) e formação; profissão e carreira antes da política; cargos eletivos ou públicos anteriores; o mandato atual (partido e estado); trocas de partido, se houver. Pule o que não constar nos dados.
5. Tom descritivo e neutro. Nada de adjetivos, elogios, críticas ou juízos. Não fale de votos, projetos, polêmicas, processos ou investigações, mesmo que apareçam no verbete.
6. Não use dois pontos para ligar frases. Escreva os nomes dos partidos pela sigla. Datas por extenso só com o ano, salvo a data de nascimento.
7. Não comece com o nome completo seguido de vírgula e aposto longo. Comece pelo nome parlamentar.

Responda só com JSON, sem texto fora dele, no formato {"bio": "...", "usou_wikipedia": true ou false, "c": "alta" ou "baixa", "duvida": "motivo curto, vazio se c for alta"}.
Marque c como "baixa" quando os dados forem contraditórios, quando o verbete talvez seja de outra pessoa ou quando houver dados de menos para três frases.`;

async function escrever(p, dados, wiki, modelo) {
  const texto = `PARLAMENTAR\n${p.n}, ${p.c === 'S' ? 'senador(a)' : 'deputado(a) federal'}, ${p.s || p.p}/${p.uf}\n\nDADOS OFICIAIS (${p.c === 'S' ? 'Senado Federal' : 'Câmara dos Deputados'})\n${JSON.stringify(dados).slice(0, 16000)}\n\nVERBETE DA WIKIPÉDIA\n${wiki ? `${wiki.titulo}\n${wiki.texto}` : '(não encontrado)'}`;
  const corpo = { model: modelo, max_tokens: 900, system: INSTRUCOES, messages: [{ role: 'user', content: texto }] };
  for (let i = 0; i < 5; i++) {
    let r;
    try {
      r = await fetch('https://api.anthropic.com/v1/messages', { method: 'POST', signal: AbortSignal.timeout(120000),
        headers: { 'content-type': 'application/json', 'x-api-key': process.env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' }, body: JSON.stringify(corpo) });
    } catch (e) { await espera(3000 * (i + 1)); continue; }
    if (r.status === 400 || r.status === 401 || r.status === 403) { log('  API recusou:', r.status, (await r.text()).slice(0, 200)); return null; }
    if (!r.ok) { await espera(3000 * (i + 1)); continue; }
    const j = await r.json();
    conta.tokens_in += (j.usage && j.usage.input_tokens) || 0; conta.tokens_out += (j.usage && j.usage.output_tokens) || 0;
    const t = (j.content || []).filter(b => b.type === 'text').map(b => b.text).join('');
    try { const o = JSON.parse(t.slice(t.indexOf('{'), t.lastIndexOf('}') + 1)); if (o.bio) return o; } catch (e) {}
  }
  return null;
}

const hash = x => crypto.createHash('sha1').update(JSON.stringify(x)).digest('hex').slice(0, 12);

function escolherAmostra(lista) {
  // Mistura de Casas e grupos, com parlamentares conhecidos e pouco conhecidos.
  const pega = (c, g, n) => lista.filter(([, p]) => p.c === c && p.cl === g).sort((a, b) => (b[1].np || 0) - (a[1].np || 0));
  const out = [];
  const add = (l, idx) => { for (const i of idx) if (l[i] && !out.includes(l[i])) out.push(l[i]); };
  add(pega('C', 'extrema'), [0, 40]); add(pega('C', 'direita'), [0, 120]); add(pega('C', 'esquerda'), [0]); add(pega('C', 'centro'), [30]);
  add(pega('S', 'extrema'), [0]); add(pega('S', 'direita'), [10]); add(pega('S', 'esquerda'), [0]); add(pega('S', 'centro'), [5]);
  return out.slice(0, AMOSTRA);
}

async function principal() {
  if (!process.env.ANTHROPIC_API_KEY) throw new Error('ANTHROPIC_API_KEY ausente');
  const indice = JSON.parse(fs.readFileSync(path.join(DADOS, 'indice.json'), 'utf8')).p;
  let antes = { itens: {} }; try { antes = JSON.parse(fs.readFileSync(ARQ, 'utf8')); } catch (e) {}
  let lista = Object.entries(indice);
  if (IDS.length) lista = lista.filter(([k]) => IDS.includes(k));
  else if (AMOSTRA) lista = escolherAmostra(lista);
  log(`Biografias: ${lista.length} parlamentares${AMOSTRA ? ' (amostra)' : ''}`);

  const itens = { ...(antes.itens || {}) };
  let feitas = 0, mantidas = 0;
  for (const [k, p] of lista) {
    const atual = itens[k];
    if (atual && atual.eq) { mantidas++; continue; }
    const id = k.slice(1);
    const dados = p.c === 'S' ? await dadosSenado(id) : await dadosCamara(id);
    if (!dados) { conta.falhas++; log(`  ${k} ${p.n}: dados oficiais indisponíveis`); continue; }
    const wiki = await verbete(p);
    if (!wiki) conta.sem_wiki++;
    const h = hash([dados, wiki && wiki.texto]);
    if (atual && atual.h === h) { mantidas++; continue; }
    let o = await escrever(p, dados, wiki, MODELO); conta.haiku++;
    let modelo = MODELO;
    if (o && o.c !== 'alta') { const f = await escrever(p, dados, wiki, MODELO_FORTE); conta.forte++; if (f) { log(`  ${k} ${p.n}: releitura pelo modelo forte (${o.duvida || 'sem motivo'})`); o = f; modelo = MODELO_FORTE; } }
    if (!o) { conta.falhas++; continue; }
    const fontes = [p.c === 'S'
      ? { t: 'Senado Federal', u: `https://www25.senado.leg.br/web/senadores/senador/-/perfil/${id}` }
      : { t: 'Câmara dos Deputados', u: `https://www.camara.leg.br/deputados/${id}` }];
    if (wiki && o.usou_wikipedia) fontes.push({ t: 'Wikipédia', u: wiki.url });
    itens[k] = { b: String(o.bio).trim(), f: fontes, h, m: modelo, d: new Date().toISOString().slice(0, 10), ...(o.c !== 'alta' ? { cf: 'baixa', dv: o.duvida || '' } : {}) };
    feitas++;
    if (AMOSTRA) log(`\n${p.n} (${k}, ${modelo})\n${itens[k].b}\nFontes: ${fontes.map(f => f.t).join(', ')}${o.c !== 'alta' ? `\nDúvida: ${o.duvida}` : ''}\n`);
    if (feitas % 25 === 0) fs.writeFileSync(ARQ, JSON.stringify({ gerado: new Date().toISOString(), itens }));
  }
  fs.writeFileSync(ARQ, JSON.stringify({ gerado: new Date().toISOString(), itens }));
  const custo = conta.tokens_in / 1e6 * 0.10 + conta.tokens_out / 1e6 * 0.50;
  log(`Concluído: ${feitas} escritas, ${mantidas} mantidas. Haiku ${conta.haiku}, modelo forte ${conta.forte}, sem verbete ${conta.sem_wiki}, falhas ${conta.falhas}.`);
  log(`Tokens: ${conta.tokens_in} de entrada, ${conta.tokens_out} de saída (estimativa pelo preço do Haiku, US$ ${custo.toFixed(3)}; as releituras do modelo forte custam mais).`);
}

principal().catch(e => { console.error(e); process.exit(1); });
