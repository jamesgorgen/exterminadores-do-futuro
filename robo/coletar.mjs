// Robô de coleta de "Os exterminadores do futuro", observatório da direita no Congresso.
//
// Roda no GitHub Actions todo dia (.github/workflows/atualizar.yml) e grava os dados em dados/.
//
// Etapas
// 1. Parlamentares. Deputados das legislaturas do período (API da Câmara). Senadores são reconhecidos
//    pelos votos e pela autoria das proposições.
// 2. Proposições. Na Câmara, por autoria de cada deputado e por ano. No Senado, quinzena a quinzena,
//    lendo os autores no texto de autoria. Tipos PL, PLP, PEC e PDL.
// 3. Votações nominais de plenário e de comissões.
//    Câmara, pelos arquivos anuais completos (votações, votos, orientações e objetos), com a API como reserva.
//    Senado, plenário pela API de votações e comissões pela API de votações em comissão.
// 4. Classificação por IA (Claude Haiku) de cada proposição e de cada votação sem proposição conhecida,
//    pelas pautas de pautas.js. O que já foi classificado fica em dados/classificacoes.json e não é refeito.
// 5. Índice de alinhamento de cada parlamentar nas votações disputadas entre o núcleo da direita e o PT.
// 6. Arquivos para a página e um diagnóstico com amostras dos dados brutos.
//
// Variáveis de ambiente
//   ANTHROPIC_API_KEY  chave da API da Anthropic (segredo do repositório)
//   MODO               diario (padrão) ou completo (refaz a legislatura inteira)
//   INICIO             data inicial da coleta completa (padrão 2023-02-01)
//   MAX_CLASSIFICACOES teto de itens classificados por execução (padrão 60000)
//   SEM_IA             1 para pular a classificação (teste)

import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DADOS = path.join(RAIZ, 'dados');
// Cópia própria do motor, para não interferir na página publicada.
const Motor = require(path.join(RAIZ, 'robo', 'motor.js'));
const PAUTAS = require(path.join(RAIZ, 'pautas.js'));
const TAX = (() => { const ctx = { window: {} }; vm.runInNewContext(fs.readFileSync(path.join(RAIZ, 'taxonomia.js'), 'utf8'), ctx); return ctx.window.TAXONOMIA; })();
const TC = Motor.compilarTaxonomia(TAX);

const AGORA = new Date();
const HOJE = AGORA.toISOString().slice(0, 10);
const MODO = process.env.MODO || 'diario';
const INICIO = process.env.INICIO || '2023-02-01';
const MAX_CLASSIFICACOES = +(process.env.MAX_CLASSIFICACOES || 60000);
const SEM_IA = process.env.SEM_IA === '1';
const TIPOS = ['PL', 'PLP', 'PEC', 'PDL'];
const MODELO = 'claude-haiku-5-5';
const VERSAO_CLASSIFICACAO = 'd1';   // mude para refazer todas as classificações

const API_CAMARA = 'https://dadosabertos.camara.leg.br/api/v2';
const ARQ_CAMARA = 'https://dadosabertos.camara.leg.br/arquivos';
const API_SENADO = 'https://legis.senado.leg.br/dadosabertos';
// Comissões permanentes do Senado consultadas para votações em comissão.
const COMISSOES_SENADO = ['CAE', 'CAS', 'CCJ', 'CCDD', 'CCT', 'CDH', 'CDR', 'CE', 'CEsp', 'CI', 'CMA', 'CRA', 'CRE', 'CSP', 'CTFC'];

// Permite trocar o acesso à rede nos testes.
const rede = { fetch: (...a) => fetch(...a) };
export function trocarRede(f) { rede.fetch = f; }

// ------------------------------------------------------------------ utilidades
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
const diag = { inicio: AGORA.toISOString(), modo: MODO, amostras: {}, contagens: {}, erros: [] };
function amostra(nome, obj) {
  if (diag.amostras[nome] || !obj || typeof obj !== 'object') return;
  const resumo = {};
  for (const [k, v] of Object.entries(obj)) resumo[k] = typeof v === 'object' && v !== null ? (Array.isArray(v) ? `[${v.length}] ` + JSON.stringify(v[0] || null).slice(0, 300) : JSON.stringify(v).slice(0, 300)) : v;
  diag.amostras[nome] = resumo;
}
function erro(onde, e) { const m = `${onde}: ${String(e && e.message || e).slice(0, 300)}`; diag.erros.push(m); log('ERRO', m); }
const contar = (nome, n = 1) => { diag.contagens[nome] = (diag.contagens[nome] || 0) + n; };

function lerJson(nome, padrao) {
  try { return JSON.parse(fs.readFileSync(path.join(DADOS, nome), 'utf8')); } catch (e) { return padrao; }
}
function gravarJson(nome, obj, compacto) {
  fs.mkdirSync(DADOS, { recursive: true });
  fs.writeFileSync(path.join(DADOS, nome), compacto ? JSON.stringify(obj) : JSON.stringify(obj, null, 1));
}
const espera = ms => new Promise(r => setTimeout(r, ms));

async function baixar(url, { tentativas = 4, tempo = 90000, tipo = 'json' } = {}) {
  let atraso = 1500;
  for (let i = 0; i < tentativas; i++) {
    try {
      const r = await rede.fetch(url, { headers: { Accept: 'application/json', 'User-Agent': 'exterminadores-do-futuro (observatorio)' }, signal: AbortSignal.timeout(tempo) });
      if (r.ok) return tipo === 'texto' ? await r.text() : await r.json();
      if (r.status === 404 || r.status === 400) throw Object.assign(new Error('http ' + r.status), { definitivo: true });
      if (r.status === 429) atraso *= 2;
    } catch (e) {
      if (e.definitivo) throw e;
      if (i === tentativas - 1) throw e;
    }
    await espera(atraso); atraso *= 2;
  }
  throw new Error('falhou ' + url);
}

// XML simples -> objeto (filhos repetidos viram lista, atributos são ignorados, texto vira string).
function xmlParaObjeto(xml) {
  const raiz = {}; const pilha = [{ nome: '#', obj: raiz }];
  const re = /<(\/?)([A-Za-z_][\w.:-]*)[^>]*?(\/?)>|([^<]+)/g;
  let m;
  xml = String(xml).replace(/<\?[\s\S]*?\?>|<!--[\s\S]*?-->|<!DOCTYPE[^>]*>/g, '');
  while ((m = re.exec(xml))) {
    const topo = pilha[pilha.length - 1];
    if (m[4] !== undefined) { const t = m[4].trim(); if (t) topo.texto = (topo.texto || '') + t.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, '&'); continue; }
    if (m[1]) {   // fechamento
      const no = pilha.pop(); const pai = pilha[pilha.length - 1];
      const valor = Object.keys(no.obj).length ? no.obj : (no.texto || '');
      const ja = pai.obj[no.nome];
      pai.obj[no.nome] = ja === undefined ? valor : Array.isArray(ja) ? [...ja, valor] : [ja, valor];
      continue;
    }
    if (m[3]) { const pai = topo; const ja = pai.obj[m[2]]; pai.obj[m[2]] = ja === undefined ? '' : Array.isArray(ja) ? [...ja, ''] : [ja, '']; continue; }
    pilha.push({ nome: m[2], obj: {} });
  }
  return raiz;
}
// Listas de um único item no XML viram objeto; esta função garante a lista.
const comoLista = v => Array.isArray(v) ? v : v && typeof v === 'object' ? [v] : [];

// Senado: aceita JSON ou XML e guarda no diagnóstico a primeira resposta bruta de cada tipo de consulta.
async function baixarSenado(url, rotulo, opcoes = {}) {
  const texto = await baixar(url, Object.assign({}, opcoes, { tipo: 'texto' }));
  if (!diag.brutos) diag.brutos = {};
  if (!diag.brutos[rotulo]) diag.brutos[rotulo] = { url, tamanho: texto.length, inicio: texto.slice(0, 1500) };
  const t = texto.trim();
  if (!t) return null;
  if (t[0] === '<') return xmlParaObjeto(t);
  return JSON.parse(t);
}

// Procura um campo pelo nome, sem diferenciar maiúsculas, inclusive em objetos aninhados de um nível
// ("deputado_id", "deputado_.id" ou "deputado.id").
function pega(o, ...nomes) {
  if (!o || typeof o !== 'object') return undefined;
  const chaves = Object.keys(o);
  for (const nome of nomes) {
    const alvo = nome.toLowerCase();
    const k = chaves.find(c => c.toLowerCase() === alvo);
    if (k !== undefined && o[k] !== null && o[k] !== '') return o[k];
    const partes = alvo.split(/[._]/).filter(Boolean);
    if (partes.length === 2) {
      const pai = chaves.find(c => c.toLowerCase().replace(/_$/, '') === partes[0]);
      if (pai && o[pai] && typeof o[pai] === 'object') {
        const filho = Object.keys(o[pai]).find(c => c.toLowerCase() === partes[1]);
        if (filho !== undefined && o[pai][filho] !== null && o[pai][filho] !== '') return o[pai][filho];
      }
    }
  }
  return undefined;
}
// Lista de registros de uma resposta (dados, ou o primeiro array encontrado).
function registros(j) {
  if (Array.isArray(j)) return j;
  if (j && Array.isArray(j.dados)) return j.dados;
  if (j && typeof j === 'object') for (const v of Object.values(j)) { const r = registros(v); if (r.length) return r; }
  return [];
}

const ano = d => +String(d).slice(0, 4);
function anosDoPeriodo(ini, fim) { const out = []; for (let a = ano(ini); a <= ano(fim); a++) out.push(a); return out; }

// Sigla de partido -> id do partido (lista do motor), ou a própria sigla.
const SIGLA_PARA_ID = new Map();
for (const p of Motor.PARTIDOS) [...p.camara, ...p.senado, ...p.antecessoras].forEach(s => SIGLA_PARA_ID.set(s.toUpperCase(), p.id));
const idPartido = s => { if (/^s\s*\/?\s*part|sem partido/i.test(String(s || ''))) return 'SP'; const k = Motor.normalizar(String(s || '')).toUpperCase().replace(/\s+/g, ' ').trim(); return SIGLA_PARA_ID.get(String(s || '').toUpperCase().trim()) || SIGLA_PARA_ID.get(k) || (k ? 'OUTROS' : ''); };
const NUCLEO = new Set(PAUTAS.nucleo);
const REFERENCIA = new Set(PAUTAS.referenciaGoverno);

function codigoVoto(v) {
  const t = Motor.normalizar(String(v || '')).trim();
  if (t === 'sim' || t === 's') return 'S';
  if (t === 'nao' || t === 'n') return 'N';
  if (t.startsWith('absten')) return 'A';
  if (t.startsWith('obstru')) return 'O';
  return '';
}

// ------------------------------------------------------------------ estado e arquivos
const estado = lerJson('estado.json', { anosCompletos: {}, ultimaColeta: '' });
const parlamentares = lerJson('parlamentares.json', { gerado: '', p: {} });       // chave C<id> ou S<id>
const classificacoes = lerJson('classificacoes.json', { versao: VERSAO_CLASSIFICACAO, c: {} });
if (classificacoes.versao !== VERSAO_CLASSIFICACAO) { classificacoes.versao = VERSAO_CLASSIFICACAO; classificacoes.c = {}; }

function registrarParlamentar(chave, dados) {
  const atual = parlamentares.p[chave] || {};
  // O partido mais recente prevalece.
  if (dados.d && atual.d && dados.d < atual.d) { parlamentares.p[chave] = Object.assign({}, dados, atual); return; }
  parlamentares.p[chave] = Object.assign(atual, Object.fromEntries(Object.entries(dados).filter(([, v]) => v !== undefined && v !== '')));
}
// Índice de nomes de senadores, para ligar a autoria das proposições aos códigos dos votos.
function chaveNome(n) { return Motor.normalizar(String(n || '')).trim().replace(/^senador[a]?\s+/, '').replace(/[^a-z ]/g, '').replace(/\s+/g, ' ').trim(); }

// ------------------------------------------------------------------ 1. deputados
async function coletarDeputados(ini, fim) {
  for (const leg of Motor.legislaturas(ini, fim)) {
    let pagina = 1, total = 1;
    while (pagina <= total) {
      try {
        const j = await baixar(`${API_CAMARA}/deputados?idLegislatura=${leg}&itens=100&pagina=${pagina}&ordem=ASC&ordenarPor=nome`);
        const lista = registros(j);
        amostra('camara_deputado', lista[0]);
        lista.forEach(d => registrarParlamentar('C' + pega(d, 'id'), { n: pega(d, 'nome'), s: pega(d, 'siglaPartido'), p: idPartido(pega(d, 'siglaPartido')), uf: pega(d, 'siglaUf'), c: 'C' }));
        contar('deputados', lista.length);
        total = Motor.ultimaPagina(j);
      } catch (e) { erro(`deputados leg ${leg} pág ${pagina}`, e); }
      pagina++;
    }
  }
}

// ------------------------------------------------------------------ 2. proposições
const proposicoesPorAno = {};
function arquivoProposicoes(a) {
  if (!proposicoesPorAno[a]) {
    const j = lerJson(`proposicoes-${a}.json`, { ano: a, itens: [] });
    proposicoesPorAno[a] = new Map(j.itens.map(it => [it.c, it]));
  }
  return proposicoesPorAno[a];
}
function guardarProposicao(it) {
  // Algumas datas de apresentação vêm erradas na fonte (PL de 2026 com data de 2009). O ano do número prevalece.
  const anoChave = +String(it.c).split('/')[1];
  if (anoChave && it.d && ano(it.d) !== anoChave) { contar('proposicoes_data_corrigida'); it.d = `${anoChave}-01-01`; }
  const mapa = arquivoProposicoes(ano(it.d || it.c.split('/')[1]));
  const ja = mapa.get(it.c);
  if (ja) {
    ja.a = [...new Set([...(ja.a || []), ...(it.a || [])])];
    ja.p = [...new Set([...(ja.p || []), ...(it.p || [])])];
    if (!ja.k.includes(it.k[0])) ja.k = [...ja.k, ...it.k];
    for (const f of ['i', 'l', 'e', 'd', 'u', 'ss']) if (!ja[f] && it[f]) ja[f] = it[f];
  } else mapa.set(it.c, it);
}

async function coletarProposicoesCamara(anos) {
  const deps = Object.entries(parlamentares.p).filter(([k]) => k[0] === 'C');
  const tarefas = [];
  for (const [chave] of deps) for (const a of anos) tarefas.push({ chave, a });
  log(`Câmara, proposições de ${deps.length} deputados em ${anos.join(', ')} (${tarefas.length} consultas)`);
  let feitas = 0;
  await Motor.emParalelo(tarefas.map(t => async () => {
    let pagina = 1, total = 1;
    while (pagina <= total) {
      const q = new URLSearchParams({ idDeputadoAutor: t.chave.slice(1), siglaTipo: TIPOS.join(','), ano: String(t.a), itens: '100', pagina: String(pagina), ordem: 'ASC', ordenarPor: 'id' });
      try {
        const j = await baixar(`${API_CAMARA}/proposicoes?${q}`);
        const lista = registros(j);
        amostra('camara_proposicao', lista[0]);
        for (const d of lista) {
          const chave = `${pega(d, 'siglaTipo')} ${pega(d, 'numero')}/${pega(d, 'ano')}`;
          const dep = parlamentares.p[t.chave] || {};
          guardarProposicao({ c: chave, k: ['C'], d: String(pega(d, 'dataApresentacao') || '').slice(0, 10) || `${pega(d, 'ano')}-01-01`,
            e: String(pega(d, 'ementa') || ''), a: [t.chave], p: dep.p ? [dep.p] : [], i: pega(d, 'id') });
        }
        contar('proposicoes_camara_registros', lista.length);
        total = Motor.ultimaPagina(j);
      } catch (e) { if (pagina === 1) erro(`proposições ${t.chave} ${t.a}`, e); }
      pagina++;
    }
    if (++feitas % 200 === 0) log(`  ${feitas} de ${tarefas.length}`);
  }), 6);
}

async function coletarProposicoesSenado(ini, fim) {
  const janelas = Motor.janelasQuinzenais(ini, fim);
  log(`Senado, proposições em ${janelas.length} quinzenas`);
  const porNome = new Map(Object.entries(parlamentares.p).filter(([k]) => k[0] === 'S').map(([k, v]) => [chaveNome(v.n), k]));
  await Motor.emParalelo(janelas.map(([a, b]) => async () => {
    // Uma consulta por tipo, porque a API pode não aceitar a sigla repetida.
    let lista = [];
    for (const tipo of TIPOS) {
      try { lista = lista.concat(registros(await baixarSenado(Motor.urlSenado([tipo], a, b), 'senado_processo'))); }
      catch (e) { erro(`proposições Senado ${tipo} ${a}`, e); }
    }
    contar('senado_processo_registros', lista.length);
    amostra('senado_proposicao', lista[0]);
    for (const d of lista) {
      if (pega(d, 'objetivo') === 'Revisora') continue;
      const autoria = String(pega(d, 'autoria') || '');
      // "Senador Fulano (PL/SP), Senadora Beltrana (PT/BA)"
      const autores = [...autoria.matchAll(/([^,(]+?)\s*\(([^()\/]+)\/([A-Z]{2})\)/g)];
      if (!autores.length) continue;
      const m = /^(\S+)\s+(\d+)\/(\d{4})/.exec(String(pega(d, 'identificacao') || ''));
      if (!m) continue;
      const chave = `${m[1]} ${parseInt(m[2], 10)}/${m[3]}`;
      const ids = [], partidos = [];
      for (const [, nome, sigla, uf] of autores) {
        const cn = chaveNome(nome);
        let k = porNome.get(cn);
        if (!k) { k = 'SN:' + cn; registrarParlamentar(k, { n: nome.replace(/^\s*Senador[a]?\s+/i, '').trim(), s: sigla.trim(), p: idPartido(sigla), uf, c: 'S' }); porNome.set(cn, k); }
        ids.push(k); partidos.push(idPartido(sigla));
      }
      guardarProposicao({ c: chave, k: ['S'], d: String(pega(d, 'dataApresentacao') || '').slice(0, 10), e: String(pega(d, 'ementa') || ''),
        a: ids, p: [...new Set(partidos)], i: pega(d, 'codigoMateria'), ss: String(pega(d, 'situacaoAtual') || '') });
      contar('proposicoes_senado', 1);
    }
  }), 3);
}

// ------------------------------------------------------------------ 3. votações
const votacoesPorAno = {};
function arquivoVotacoes(a) {
  if (!votacoesPorAno[a]) {
    const j = lerJson(`votacoes-${a}.json`, { ano: a, itens: [] });
    votacoesPorAno[a] = new Map(j.itens.map(v => [v.id, v]));
  }
  return votacoesPorAno[a];
}
// Guarda a votação já com a posição do bloco e da referência calculadas pelos partidos da época,
// e com os votos agrupados por tipo ({S: [códigos], N: [...], A, O, '-'}), o que reduz o tamanho dos arquivos.
function guardarVotacao(v) {
  if (!v || !v.d || !Object.keys(v.v || {}).length) return;
  if (!Object.values(v.v).some(c => c === 'S' || c === 'N')) { contar('votacoes_sem_sim_nao'); return; }
  const b = posicao(v.v, v.ps || {}, NUCLEO);
  const g = posicao(v.v, v.ps || {}, REFERENCIA);
  const grupos = {};
  for (const [k, c] of Object.entries(v.v)) (grupos[c] || (grupos[c] = [])).push(+k.slice(1));
  const sai = Object.assign({}, v, { v: grupos, bl: b.pos, blc: b.coesao, gv: g.pos, disp: !!(b.pos && g.pos && b.pos !== g.pos) });
  delete sai.ps;
  sai.venceu = sai.bl && sai.res ? ((sai.bl === 'S') === (sai.res === 'A')) : null;
  arquivoVotacoes(ano(v.d)).set(v.id, sai);
  contar('votacoes_' + v.k + (v.pl ? '_plenario' : '_comissao'));
}
// Percorre os votos agrupados como pares [chave do parlamentar, voto].
function* votosDe(vt) { for (const [c, lista] of Object.entries(vt.v || {})) for (const id of lista) yield [vt.k + id, c]; }

const chaveMateria = (sigla, numero, anoM) => (sigla && numero && anoM) ? `${String(sigla).trim()} ${parseInt(numero, 10)}/${anoM}` : '';

// Câmara: arquivos anuais completos.
async function coletarVotacoesCamaraArquivos(a) {
  const base = n => `${ARQ_CAMARA}/${n}/json/${n}-${a}.json`;
  log(`Câmara, arquivos anuais de votações de ${a}`);
  const [vot, votos, ori, obj] = await Promise.all(['votacoes', 'votacoesVotos', 'votacoesOrientacoes', 'votacoesObjetos']
    .map(n => baixar(base(n), { tempo: 600000, tentativas: 3 }).then(registros).catch(e => { erro(`arquivo ${n}-${a}`, e); return null; })));
  if (!vot || !votos) return false;
  amostra('camara_arq_votacao', vot[0]); amostra('camara_arq_voto', votos[0]);
  if (ori) amostra('camara_arq_orientacao', ori[0]);
  if (obj) amostra('camara_arq_objeto', obj[0]);
  const porVotacao = new Map();
  for (const r of votos) {
    const id = pega(r, 'idVotacao'); if (!id) continue;
    const dep = pega(r, 'deputado_id', 'idDeputado');
    const cv = codigoVoto(pega(r, 'voto', 'tipoVoto'));
    if (!dep) continue;
    const sigla = pega(r, 'deputado_siglaPartido', 'siglaPartido');
    registrarParlamentar('C' + dep, { n: pega(r, 'deputado_nome', 'nome'), uf: pega(r, 'deputado_siglaUf', 'siglaUf'), c: 'C' });
    if (!porVotacao.has(id)) porVotacao.set(id, { v: {}, ps: {} });
    const x = porVotacao.get(id);
    x.v['C' + dep] = cv || '-';
    if (sigla) x.ps['C' + dep] = idPartido(sigla);
  }
  const orient = new Map();
  for (const r of ori || []) {
    const id = pega(r, 'idVotacao'); if (!id) continue;
    if (!orient.has(id)) orient.set(id, {});
    const b = pega(r, 'siglaBancada', 'siglaPartidoBloco'); const o = pega(r, 'orientacao', 'orientacaoVoto');
    if (b && o) orient.get(id)[b] = o;
  }
  const objetos = new Map();
  for (const r of obj || []) {
    const id = pega(r, 'idVotacao'); if (!id) continue;
    const sig = pega(r, 'proposicao_siglaTipo', 'siglaTipo');
    const item = { c: chaveMateria(sig, pega(r, 'proposicao_numero', 'numero'), pega(r, 'proposicao_ano', 'ano')), e: pega(r, 'proposicao_ementa', 'ementa') || '', principal: ['PL', 'PLP', 'PEC', 'PDL', 'MPV', 'PLV', 'PLN'].includes(sig) };
    const ja = objetos.get(id);
    if (!ja || (!ja.principal && item.principal)) objetos.set(id, item);
  }
  let n = 0;
  for (const r of vot) {
    const id = pega(r, 'id'); const x = porVotacao.get(id);
    if (!x) continue;   // votação simbólica, sem votos nominais
    const orgao = String(pega(r, 'siglaOrgao') || '');
    const ob = objetos.get(id) || {};
    guardarVotacao({ id: 'C:' + id, k: 'C', o: orgao, pl: orgao.toUpperCase() === 'PLEN',
      d: String(pega(r, 'dataHoraRegistro', 'data') || '').slice(0, 10), desc: String(pega(r, 'descricao') || '').slice(0, 600),
      mat: ob.c || '', me: String(ob.e || '').slice(0, 700), res: String(pega(r, 'aprovacao')) === '1' ? 'A' : String(pega(r, 'aprovacao')) === '0' ? 'R' : '',
      v: x.v, ps: x.ps, ori: orient.get(id) || undefined });
    n++;
  }
  log(`  ${n} votações nominais da Câmara em ${a}`);
  return n > 0 || vot.length > 0;
}

// Câmara: reserva pela API, mês a mês.
async function coletarVotacoesCamaraApi(ini, fim) {
  for (const [a, b] of Motor.janelasMensais(ini, fim)) {
    let pagina = 1, total = 1;
    while (pagina <= total) {
      let lista = [];
      try {
        const j = await baixar(`${API_CAMARA}/votacoes?dataInicio=${a}&dataFim=${b}&itens=200&pagina=${pagina}&ordem=ASC&ordenarPor=dataHoraRegistro`);
        lista = registros(j); total = Motor.ultimaPagina(j);
        amostra('camara_api_votacao', lista[0]);
      } catch (e) { erro(`votações Câmara API ${a}`, e); break; }
      await Motor.emParalelo(lista.map(r => async () => {
        const id = pega(r, 'id');
        try {
          const vj = registros(await baixar(`${API_CAMARA}/votacoes/${id}/votos`));
          if (!vj.length) { contar('camara_api_votacao_sem_votos'); return; }
          amostra('camara_api_voto', vj[0]);
          const v = {}, ps = {};
          for (const x of vj) {
            const dep = pega(x, 'deputado_.id', 'deputado_id'); if (!dep) continue;
            v['C' + dep] = codigoVoto(pega(x, 'tipoVoto', 'voto')) || '-';
            ps['C' + dep] = idPartido(pega(x, 'deputado_.siglaPartido', 'deputado_siglaPartido'));
            registrarParlamentar('C' + dep, { n: pega(x, 'deputado_.nome', 'deputado_nome'), uf: pega(x, 'deputado_.siglaUf', 'deputado_siglaUf'), c: 'C' });
          }
          let ori;
          try { ori = {}; registros(await baixar(`${API_CAMARA}/votacoes/${id}/orientacoes`)).forEach(o => { const bb = pega(o, 'siglaPartidoBloco', 'siglaBancada'); const oo = pega(o, 'orientacaoVoto', 'orientacao'); if (bb && oo) ori[bb] = oo; }); } catch (e) { ori = undefined; }
          const orgao = String(pega(r, 'siglaOrgao') || '');
          guardarVotacao({ id: 'C:' + id, k: 'C', o: orgao, pl: orgao.toUpperCase() === 'PLEN', d: String(pega(r, 'dataHoraRegistro', 'data') || '').slice(0, 10),
            desc: String(pega(r, 'descricao') || '').slice(0, 600), mat: '', me: '', res: String(pega(r, 'aprovacao')) === '1' ? 'A' : String(pega(r, 'aprovacao')) === '0' ? 'R' : '', v, ps, ori });
        } catch (e) { contar('camara_api_votacao_erro'); }
      }), 4);
      pagina++;
    }
  }
}

const CAMPOS_VOTO = ['siglaVotoParlamentar', 'descricaoVotoParlamentar', 'voto', 'QualidadeVoto', 'DescricaoVoto', 'SiglaVoto'];
// Procura, em qualquer formato de resposta, os objetos que são votações com votos nominais.
// Uma votação é um objeto que contém uma lista de votos (registros com código do parlamentar e voto).
function acharVotacoes(no, saida = [], pai = null) {
  if (Array.isArray(no)) {
    const pareceVotos = no.length && no.every(x => x && typeof x === 'object' && pega(x, 'codigoParlamentar', 'codigoSenador', 'CodigoParlamentar') !== undefined)
      && CAMPOS_VOTO.some(c => pega(no[0], c) !== undefined);
    if (pareceVotos && pai) { saida.push({ votacao: pai, votos: no }); return saida; }
    no.forEach(x => acharVotacoes(x, saida, null));
  } else if (no && typeof no === 'object') {
    for (const v of Object.values(no)) {
      // Formato XML convertido: { Votos: { Voto: [...] } }
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        const interno = Object.values(v).find(Array.isArray);
        if (interno && interno.length && pega(interno[0], 'codigoParlamentar', 'CodigoParlamentar') !== undefined && CAMPOS_VOTO.some(c => pega(interno[0], c) !== undefined) && Object.keys(v).length === 1) { saida.push({ votacao: no, votos: interno }); continue; }
      }
      acharVotacoes(v, saida, no);
    }
  }
  return saida;
}
function votacaoSenado({ votacao: o, votos }, plenario, comissao) {
  const sigla = pega(o, 'siglaMateria', 'SiglaSubtipoMateria', 'siglaSubtipoMateria', 'sigla');
  const num = pega(o, 'numeroMateria', 'NumeroMateria', 'numero');
  const an = pega(o, 'anoMateria', 'AnoMateria', 'ano');
  let mat = chaveMateria(sigla, num, an);
  const ident = String(pega(o, 'identificacao', 'materia', 'DescricaoIdentificacaoMateria', 'identificacaoMateria') || '');
  const mm = /^(\S+)\s+(\d+)\/(\d{4})/.exec(ident);
  if (!mat && mm) mat = `${mm[1]} ${parseInt(mm[2], 10)}/${mm[3]}`;
  const data = String(pega(o, 'dataSessao', 'data', 'DataHoraInicioReuniao', 'dataHoraInicioReuniao', 'dataInicio', 'DataSessao') || '').slice(0, 10);
  const cod = pega(o, 'codigoSessaoVotacao', 'codigoVotacao', 'CodigoVotacao', 'codigoVotacaoSve', 'codigo', 'idVotacao');
  const secreta = /^(s|sim|true)$/i.test(String(pega(o, 'votacaoSecreta', 'secreta', 'IndicadorVotacaoSecreta') || ''));
  if (secreta) { contar('senado_secretas'); return null; }
  const res = Motor.normalizar(String(pega(o, 'resultadoVotacao', 'resultado', 'DescricaoResultado') || ''));
  const v = {}, ps = {};
  for (const x of votos) {
    const c = pega(x, 'codigoParlamentar', 'codigoSenador', 'CodigoParlamentar'); if (!c) continue;
    const nome = pega(x, 'nomeParlamentar', 'nomeSenador', 'NomeParlamentar');
    const sigP = pega(x, 'siglaPartidoParlamentar', 'partido', 'SiglaPartidoParlamentar', 'siglaPartido');
    const uf = pega(x, 'siglaUFParlamentar', 'siglaUfParlamentar', 'uf', 'SiglaUFParlamentar', 'SiglaUfParlamentar');
    v['S' + c] = codigoVoto(pega(x, ...CAMPOS_VOTO)) || '-';
    if (sigP) ps['S' + c] = idPartido(sigP);
    registrarParlamentar('S' + c, { n: nome, s: sigP, p: idPartido(sigP), uf, c: 'S', d: data });
  }
  if (!data || !cod) return null;
  return { id: (plenario ? 'S:' : 'SC:') + (comissao ? comissao + ':' : '') + cod, k: 'S', o: plenario ? 'PLEN' : comissao, pl: plenario, d: data,
    desc: String(pega(o, 'descricaoVotacao', 'descricao', 'DescricaoVotacao') || '').slice(0, 600), mat, me: String(pega(o, 'ementa', 'EmentaMateria', 'ementaMateria') || '').slice(0, 700),
    res: res.startsWith('aprov') || res === 'a' ? 'A' : res.startsWith('rejeit') || res === 'r' ? 'R' : '', v, ps };
}

async function coletarVotacoesSenado(ini, fim) {
  log('Senado, votações de plenário');
  for (const [a, b] of Motor.janelasMensais(ini, fim)) {
    let achadas = [];
    for (const fmt of [s => s, s => s.replace(/-/g, '')]) {
      try {
        achadas = acharVotacoes(await baixarSenado(`${API_SENADO}/votacao?dataInicio=${fmt(a)}&dataFim=${fmt(b)}`, 'senado_votacao_' + (fmt(a) === a ? 'iso' : 'compacta')));
        if (achadas.length) break;
      } catch (e) { if (fmt(a) !== a) erro(`votações Senado ${a}`, e); }
    }
    contar('senado_plenario_votacoes_achadas', achadas.length);
    if (achadas[0]) { amostra('senado_votacao', achadas[0].votacao); amostra('senado_voto', achadas[0].votos[0]); }
    achadas.forEach(x => guardarVotacao(votacaoSenado(x, true)));
  }
  log('Senado, votações em comissões');
  const trimestres = [];
  for (const [a, b] of Motor.janelasMensais(ini, fim)) {
    const u = trimestres[trimestres.length - 1];
    if (u && u.n < 3) { u.b = b; u.n++; } else trimestres.push({ a, b, n: 1 });
  }
  const tarefas = [];
  for (const com of COMISSOES_SENADO) for (const t of trimestres) tarefas.push({ com, t });
  await Motor.emParalelo(tarefas.map(({ com, t }) => async () => {
    const urls = [
      `${API_SENADO}/votacaoComissao/comissao/${com}?dataInicio=${t.a.replace(/-/g, '')}&dataFim=${t.b.replace(/-/g, '')}`,
      `${API_SENADO}/votacaoComissao/comissao/${com}.json?dataInicio=${t.a.replace(/-/g, '')}&dataFim=${t.b.replace(/-/g, '')}`,
    ];
    for (const u of urls) {
      try {
        const j = await baixarSenado(u, 'senado_comissao', { tentativas: 2 });
        const achadas = acharVotacoes(j);
        contar('senado_comissao_votacoes_achadas', achadas.length);
        if (achadas[0]) { amostra('senado_comissao_votacao', achadas[0].votacao); amostra('senado_comissao_voto', achadas[0].votos[0]); }
        achadas.forEach(x => guardarVotacao(votacaoSenado(x, false, com)));
        return;
      } catch (e) { if (u === urls[urls.length - 1]) { contar('senado_comissao_falha'); if (!diag.erros.some(x => x.startsWith('comissão Senado'))) erro(`comissão Senado ${com}`, e); } }
    }
  }), 3);
}

// ------------------------------------------------------------------ 4. classificação por IA
const LISTA_PAUTAS = PAUTAS.lista.map(p => `- ${p.id} (${p.nome}). ${p.descricao} Extrema-direita quando: ${p.extrema}`).join('\n');
const IDS_PAUTAS = new Set(PAUTAS.lista.map(p => p.id));
const INSTRUCOES = `Você é analista de um observatório que acompanha a atuação da direita e da extrema-direita no Congresso Nacional brasileiro. Para cada item numerado (uma proposição legislativa ou uma votação, descrita pela ementa), diga se ele trata de alguma das pautas abaixo e em que sentido.

PAUTAS
${LISTA_PAUTAS}

CAMPOS
- "s" é o sentido. Use "avanca" quando o item faz avançar a pauta da direita (por exemplo, flexibiliza o porte de armas, reduz a maioridade penal, anistia golpistas, restringe o aborto legal, afrouxa o licenciamento ambiental, retira direitos trabalhistas). Use "barra" quando o item vai contra a pauta da direita (por exemplo, amplia o controle de armas, reduz a jornada de trabalho, protege terras indígenas, regula plataformas digitais). Deixe vazio quando o item não trata de nenhuma pauta.
- "p" é a lista de pautas tratadas, de uma a três, pelos identificadores acima. Vazia quando "s" for vazio.
- "g" é o grau, só quando "s" for "avanca". Use "extrema" quando o item se encaixa na descrição de extrema-direita da pauta, e "direita" nos demais casos. Vazio quando "s" for "barra" ou vazio.
- "m" é o motivo, em até 20 palavras, dizendo o que o item faz em relação à pauta. Tom informativo, sem adjetivos de militância. Não use dois-pontos. Vazio quando "s" for vazio.

REGRAS
- Julgue só o conteúdo da ementa. Os autores e os partidos não são informados.
- Homenagens, datas comemorativas, denominações e ajustes administrativos ficam com "s" vazio.
- Na dúvida, deixe "s" vazio. É melhor deixar de marcar do que marcar errado.

Responda somente com JSON válido, sem texto antes ou depois, neste formato.
{"r":[{"n":1,"s":"avanca","p":["armas"],"g":"direita","m":"Amplia o porte de armas para vigilantes de empresas privadas"},{"n":2,"s":"","p":[],"g":"","m":""}]}`;

async function classificarLote(itens) {
  const lista = itens.map((it, k) => `${k + 1}. ${it.chave}. ${String(it.texto).slice(0, 700)}`).join('\n');
  const corpo = { model: MODELO, max_tokens: Math.min(8000, 1200 + itens.length * 120), thinking: { type: 'disabled' },
    system: [{ type: 'text', text: INSTRUCOES, cache_control: { type: 'ephemeral' } }], messages: [{ role: 'user', content: 'ITENS\n' + lista }] };
  let atraso = 3000;
  for (let i = 0; i < 4; i++) {
    let r;
    try {
      r = await rede.fetch('https://api.anthropic.com/v1/messages', { method: 'POST', signal: AbortSignal.timeout(120000),
        headers: { 'content-type': 'application/json', 'x-api-key': process.env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' }, body: JSON.stringify(corpo) });
    } catch (e) { await espera(atraso); atraso *= 2; continue; }
    if (r.status === 400 && corpo.thinking) { delete corpo.thinking; continue; }
    if (r.status === 401 || r.status === 403) throw new Error('chave da Anthropic recusada');
    if (!r.ok) { await espera(atraso); atraso *= 2; continue; }
    const j = await r.json();
    const texto = (j.content || []).filter(b => b.type === 'text').map(b => b.text).join('');
    let res;
    try { res = JSON.parse(texto.slice(texto.indexOf('{'), texto.lastIndexOf('}') + 1)).r; } catch (e) { res = null; }
    if (!Array.isArray(res)) { await espera(atraso); continue; }
    const saida = {};
    for (const x of res) {
      const it = itens[(+x.n) - 1]; if (!it) continue;
      const s = ['avanca', 'barra'].includes(x.s) ? x.s : '';
      const p = s ? (Array.isArray(x.p) ? x.p : []).filter(id => IDS_PAUTAS.has(id)).slice(0, 3) : [];
      saida[it.chave] = { s: p.length ? s : '', p, g: s === 'avanca' && p.length ? (x.g === 'extrema' ? 'extrema' : 'direita') : '', m: p.length ? String(x.m || '').slice(0, 200) : '' };
    }
    return saida;
  }
  return {};
}

async function classificarPendentes(itens) {
  const pend = itens.filter(it => !classificacoes.c[it.chave]).slice(0, MAX_CLASSIFICACOES);
  log(`Classificação, ${pend.length} itens novos (${itens.length - pend.length} já classificados)`);
  if (!pend.length || SEM_IA || !process.env.ANTHROPIC_API_KEY) { if (pend.length) log('  sem chave da Anthropic ou SEM_IA, classificação pulada'); return; }
  const lotes = [];
  for (let i = 0; i < pend.length; i += 25) lotes.push(pend.slice(i, i + 25));
  let feitos = 0;
  await Motor.emParalelo(lotes.map(l => async () => {
    try { Object.assign(classificacoes.c, await classificarLote(l)); }
    catch (e) { erro('classificação', e); if (/recusada/.test(e.message)) throw e; }
    feitos += l.length;
    if (feitos % 1000 < 25) { log(`  ${feitos} de ${pend.length}`); gravarJson('classificacoes.json', classificacoes, true); }
  }), 4);
  contar('classificados', feitos);
}

// ------------------------------------------------------------------ 5. alinhamento
function posicao(votos, ps, grupo) {
  let s = 0, n = 0;
  for (const [k, v] of Object.entries(votos)) {
    if (!grupo.has(ps[k])) continue;
    if (v === 'S') s++; else if (v === 'N') n++;
  }
  const t = s + n;
  // Ao menos dois votos do grupo, para que comissões pequenas do Senado também entrem.
  if (t < 2) return { pos: '', coesao: 0 };
  const c = Math.max(s, n) / t;
  return { pos: c >= PAUTAS.indice.coesaoMinima ? (s >= n ? 'S' : 'N') : '', coesao: Math.round(c * 100) / 100 };
}
function calcularAlinhamento(todasVotacoes) {
  const conta = {};
  for (const vt of todasVotacoes) {
    if (!vt.disp) continue;
    for (const [k, v] of votosDe(vt)) {
      if (v !== 'S' && v !== 'N') continue;
      const c = conta[k] || (conta[k] = { vd: 0, va: 0, vdc: 0, vds: 0 });
      c.vd++; if (v === vt.bl) c.va++;
      if (vt.k === 'C') c.vdc++; else c.vds++;
    }
  }
  return conta;
}

// ------------------------------------------------------------------ execução
export async function executar() {
  const completo = MODO === 'completo' || !estado.ultimaColeta;
  const ini = completo ? INICIO : new Date(AGORA - 45 * 86400000).toISOString().slice(0, 10);
  const anos = anosDoPeriodo(completo ? INICIO : ini, HOJE);
  log(`Modo ${completo ? 'completo' : 'diário'}, período ${ini} a ${HOJE}`);

  await coletarDeputados(INICIO, HOJE);

  // Votações primeiro, porque trazem os códigos dos senadores usados para ligar a autoria das proposições.
  for (const a of anos) {
    const ok = await coletarVotacoesCamaraArquivos(a);
    if (!ok) await coletarVotacoesCamaraApi(a === anos[0] ? ini : `${a}-01-01`, a === ano(HOJE) ? HOJE : `${a}-12-31`);
  }
  // Se o arquivo do ano corrente não trouxe nada recente, completa os últimos dias pela API.
  await coletarVotacoesSenado(ini, HOJE);

  await coletarProposicoesCamara(anos);
  await coletarProposicoesSenado(ini, HOJE);

  // Carrega os anos que não foram tocados nesta execução, para que os arquivos gravados fiquem completos.
  for (const a of anosDoPeriodo(INICIO, HOJE)) { arquivoVotacoes(a); arquivoProposicoes(a); }
  const todasVot = Object.values(votacoesPorAno).flatMap(m => [...m.values()]);
  const todasPropFinal = Object.values(proposicoesPorAno).flatMap(m => [...m.values()]);
  // Temas da taxonomia, pelas ementas.
  for (const it of todasPropFinal) if (!it.m) it.m = Motor.classificar(it.e || '', TC).map(t => t.id);

  // Classificação. Proposições pela chave; votações pela matéria quando houver ementa, senão pela descrição.
  const paraClassificar = [];
  const vistos = new Set();
  for (const it of todasPropFinal) if (!Motor.ehHomenagem(it.e || '', TC)) { paraClassificar.push({ chave: it.c, texto: it.e }); vistos.add(it.c); }
  for (const vt of todasVot) {
    if (vt.mat && (vistos.has(vt.mat) || vt.me)) { if (!vistos.has(vt.mat)) { paraClassificar.push({ chave: vt.mat, texto: vt.me }); vistos.add(vt.mat); } vt.ck = vt.mat; }
    else { vt.ck = 'V:' + vt.id; paraClassificar.push({ chave: vt.ck, texto: [vt.desc, vt.me].filter(Boolean).join(' ') }); }
  }
  await classificarPendentes(paraClassificar);

  // Alinhamento.
  const conta = calcularAlinhamento(todasVot);
  const contaProp = {};
  for (const it of todasPropFinal) {
    const cl = classificacoes.c[it.c];
    for (const a of it.a || []) {
      const c = contaProp[a] || (contaProp[a] = { n: 0, d: 0, x: 0, pp: {} });
      c.n++;
      if (cl && cl.s === 'avanca') { c.d++; if (cl.g === 'extrema') c.x++; cl.p.forEach(p => c.pp[p] = (c.pp[p] || 0) + 1); }
    }
  }
  const indice = {};
  for (const [k, p] of Object.entries(parlamentares.p)) {
    const c = conta[k] || { vd: 0, va: 0, vdc: 0, vds: 0 };
    const pr = contaProp[k] || { n: 0, d: 0, x: 0, pp: {} };
    const i = c.vd >= PAUTAS.indice.votacoesMinimas ? Math.round(1000 * c.va / c.vd) / 10 : null;
    const classe = NUCLEO.has(p.p) ? 'nucleo' : i !== null && i >= PAUTAS.indice.alinhado * 100 ? 'alinhado' : i !== null && i >= PAUTAS.indice.proximo * 100 ? 'proximo' : '';
    if (!c.vd && !pr.n) continue;
    indice[k] = { n: p.n, c: p.c, p: p.p, s: p.s, uf: p.uf, i, vd: c.vd, va: c.va, cl: classe, np: pr.n, nd: pr.d, nx: pr.x, pp: pr.pp };
  }

  // Gravação. Apaga arquivos de anos anteriores à legislatura, criados por datas erradas da fonte.
  fs.mkdirSync(DADOS, { recursive: true });
  for (const f of fs.readdirSync(DADOS)) {
    const mm = /^(proposicoes|votacoes)-(\d{4})\.json$/.exec(f);
    if (mm && +mm[2] < 2023) { fs.unlinkSync(path.join(DADOS, f)); delete (mm[1] === 'proposicoes' ? proposicoesPorAno : votacoesPorAno)[mm[2]]; }
  }
  for (const [a, m] of Object.entries(proposicoesPorAno)) {
    const itens = [...m.values()].sort((x, y) => (y.d || '').localeCompare(x.d || ''));
    if (itens.length) gravarJson(`proposicoes-${a}.json`, { ano: +a, itens }, true);
  }
  for (const [a, m] of Object.entries(votacoesPorAno)) {
    const itens = [...m.values()].sort((x, y) => (y.d || '').localeCompare(x.d || ''));
    if (itens.length) gravarJson(`votacoes-${a}.json`, { ano: +a, itens }, true);
  }
  gravarJson('classificacoes.json', classificacoes, true);
  parlamentares.gerado = AGORA.toISOString();
  gravarJson('parlamentares.json', parlamentares, true);
  gravarJson('indice.json', { gerado: AGORA.toISOString(), regras: PAUTAS.indice, nucleo: PAUTAS.nucleo, referencia: PAUTAS.referenciaGoverno, p: indice }, true);

  // Arquivos leves para a página.
  const cl = k => classificacoes.c[k] || {};
  const direita = todasPropFinal.filter(it => cl(it.c).s === 'avanca')
    .map(it => ({ c: it.c, k: it.k, d: it.d, e: it.e, a: it.a, p: it.p, m: it.m, i: it.i, ss: it.ss, x: cl(it.c) }))
    .sort((x, y) => (y.d || '').localeCompare(x.d || ''));
  gravarJson('proposicoes-direita.json', { gerado: AGORA.toISOString(), itens: direita }, true);
  const resumoVot = todasVot.map(vt => ({ id: vt.id, k: vt.k, o: vt.o, pl: vt.pl, d: vt.d, desc: vt.desc, mat: vt.mat, me: vt.me, res: vt.res,
    bl: vt.bl, blc: vt.blc, gv: vt.gv, disp: vt.disp, venceu: vt.venceu, ori: vt.ori, x: cl(vt.ck),
    t: Object.fromEntries(Object.entries(vt.v || {}).map(([c, l]) => [c, l.length])) }))
    .sort((x, y) => (y.d || '').localeCompare(x.d || ''));
  gravarJson('votacoes-resumo.json', { gerado: AGORA.toISOString(), itens: resumoVot }, true);

  const desde = d => new Date(AGORA - d * 86400000).toISOString().slice(0, 10);
  const porPauta = {};
  for (const p of PAUTAS.lista) porPauta[p.id] = { prop: 0, extrema: 0, prop30: 0, vot: 0, vitorias: 0, derrotas: 0 };
  for (const it of direita) { const x = it.x; if (x.s !== 'avanca') continue; for (const p of x.p) { porPauta[p].prop++; if (x.g === 'extrema') porPauta[p].extrema++; if (it.d >= desde(30)) porPauta[p].prop30++; } }
  for (const vt of resumoVot) { if (!vt.x.p) continue; for (const p of vt.x.p) { porPauta[p].vot++; if (vt.venceu === true) porPauta[p].vitorias++; if (vt.venceu === false) porPauta[p].derrotas++; } }
  gravarJson('resumo.json', {
    gerado: AGORA.toISOString(), inicio: INICIO,
    totais: { proposicoes: todasPropFinal.length, direita: direita.filter(it => it.x.s === 'avanca').length, extrema: direita.filter(it => it.x.g === 'extrema').length,
      votacoes: resumoVot.length, disputadas: resumoVot.filter(v => v.disp).length, vitorias: resumoVot.filter(v => v.disp && v.venceu === true).length,
      derrotas: resumoVot.filter(v => v.disp && v.venceu === false).length,
      nucleo: Object.values(indice).filter(p => p.cl === 'nucleo').length, alinhados: Object.values(indice).filter(p => p.cl === 'alinhado').length },
    porPauta,
    recentes: { proposicoes: direita.filter(it => it.x.s === 'avanca' && it.d >= desde(7)).length, votacoes: resumoVot.filter(v => v.d >= desde(7)).length }
  });

  estado.ultimaColeta = AGORA.toISOString();
  if (completo) anos.forEach(a => estado.anosCompletos[a] = HOJE);
  gravarJson('estado.json', estado);
  diag.fim = new Date().toISOString();
  gravarJson('diagnostico.json', diag);
  log('Concluído', JSON.stringify(diag.contagens));
  return { indice, direita, resumoVot };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  executar().catch(e => { erro('geral', e); try { gravarJson('diagnostico.json', diag); } catch (er) {} process.exit(1); });
}
