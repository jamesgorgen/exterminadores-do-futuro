// Relatorias da Câmara dos Deputados.
//
// A Câmara não tem uma consulta pronta de relatorias. Cada designação aparece nas tramitações da proposição,
// com o tipo "Designação de Relator(a)" e o endereço do deputado designado (uriUltimoRelator).
// Este script lista as proposições que tramitaram num período e lê as tramitações de cada uma.
//
// Primeira execução (ou COMPLETO=sim): percorre todas as proposições com tramitação desde 2023.
// Depois: só as que tramitaram nos últimos dias, substituindo as relatorias delas.
//
// Grava dados/relatorias-camara.json. Não usa IA.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const DADOS = process.env.DADOS || path.join(RAIZ, 'dados');
const ARQ = path.join(DADOS, 'relatorias-camara.json');
const PASTA = path.join(DADOS, 'relatorias-camara');
const API = 'https://dadosabertos.camara.leg.br/api/v2';
const INICIO = process.env.INICIO_REL || '2023-02-01';
const TIPOS = ['PL', 'PLP', 'PEC', 'PDL', 'MPV'];
const HOJE = new Date().toISOString().slice(0, 10);
const PARALELO = +(process.env.PARALELO || 8);
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
const espera = ms => new Promise(r => setTimeout(r, ms));
const diaMais = (d, n) => new Date(Date.parse(d) + n * 86400000).toISOString().slice(0, 10);

let falhas = 0;
async function pegar(url, tentativas = 5) {
  for (let t = 1; ; t++) {
    try {
      const r = await fetch(url, { headers: { accept: 'application/json', 'user-agent': 'exterminadores-do-futuro (observatório)' }, signal: AbortSignal.timeout(60000) });
      if (r.status === 404) return null;
      if (r.ok) return await r.json();
      if (t >= tentativas || (r.status < 500 && r.status !== 429)) throw new Error('http ' + r.status);
    } catch (e) { if (t >= tentativas) { falhas++; throw e; } }
    await espera(1500 * t * t);
  }
}

// Proposições com tramitação no período, de todos os tipos acompanhados.
async function listar(ini, fim) {
  const out = new Map();
  for (const tipo of TIPOS) {
    let url = `${API}/proposicoes?siglaTipo=${tipo}&dataInicio=${ini}&dataFim=${fim}&itens=100&ordem=ASC&ordenarPor=id`;
    while (url) {
      const j = await pegar(url).catch(e => { log('  falha ao listar', tipo, ini, e.message); return null; });
      if (!j) break;
      for (const p of j.dados || []) out.set(p.id, { id: p.id, c: `${p.siglaTipo} ${p.numero}/${p.ano}`, e: String(p.ementa || '').slice(0, 400) });
      const prox = (j.links || []).find(l => l.rel === 'next');
      url = prox ? prox.href : '';
    }
  }
  return out;
}

const RE_DEP = /Dep(?:utad[oa]|\.)\s+([^(,]+?)\s*\(([^)\/-]+)[-\/]([A-Z]{2})\)/;
const idDe = uri => { const m = /deputados\/(\d+)/.exec(String(uri || '')); return m ? m[1] : ''; };

// Relatorias de uma proposição, a partir das tramitações.
export function relatoriasDe(prop, tram) {
  const lista = [...(tram || [])].sort((a, b) => (a.sequencia || 0) - (b.sequencia || 0) || String(a.dataHora).localeCompare(String(b.dataHora)));
  if (!lista.length) return [];
  const ultima = lista[lista.length - 1];
  const atualDep = idDe(ultima.uriUltimoRelator), atualOrg = ultima.siglaOrgao;
  const out = [];
  lista.forEach((t, i) => {
    const desc = String(t.descricaoTramitacao || ''), desp = String(t.despacho || '');
    const designacao = String(t.codTipoTramitacao) === '320' || /designa[çc][ãa]o de relator/i.test(desc) || /^\s*designad[oa] relator/i.test(desp);
    if (!designacao) return;
    const di = String(t.dataHora || '').slice(0, 10);
    if (di < INICIO) return;
    const dep = idDe(t.uriUltimoRelator);
    const m = RE_DEP.exec(desp);
    if (!dep && !m) return;
    // Parecer do mesmo relator no mesmo órgão, depois da designação.
    const parecer = lista.slice(i + 1).find(x => x.siglaOrgao === t.siglaOrgao && /parecer do\(a\) relator|parecer do relator/i.test(`${x.descricaoTramitacao} ${x.despacho}`) && (!dep || idDe(x.uriUltimoRelator) === dep));
    // Nova designação no mesmo órgão encerra esta.
    const substituida = lista.slice(i + 1).some(x => x.siglaOrgao === t.siglaOrgao && String(x.codTipoTramitacao) === '320' && idDe(x.uriUltimoRelator) !== dep);
    out.push({
      c: prop.c, k: 'C', r: dep ? 'C' + dep : '', n: m ? m[1].trim() : '', s: m ? m[2].trim() : '', uf: m ? m[3] : '',
      cm: t.siglaOrgao || '', di, pa: parecer ? String(parecer.dataHora).slice(0, 10) : undefined,
      at: dep && dep === atualDep && t.siglaOrgao === atualOrg && !substituida ? 1 : 0,
      sb: substituida ? 1 : undefined, i: prop.id, e: prop.e || undefined
    });
  });
  return out;
}

async function emParalelo(itens, fn, n) {
  let k = 0, feitos = 0;
  await Promise.all(Array.from({ length: n }, async () => {
    while (k < itens.length) { const x = itens[k++]; await fn(x); if (++feitos % 1000 === 0) log(`  ${feitos} de ${itens.length}`); }
  }));
}

function gravar(porId, ate) {
  const itens = [...porId.values()].flat().filter(r => r.r).sort((a, b) => (b.di || '').localeCompare(a.di || ''));
  const gerado = new Date().toISOString(), fonte = 'Câmara dos Deputados, Dados Abertos, tramitações das proposições';
  fs.writeFileSync(ARQ, JSON.stringify({ gerado, fonte, ate, itens }));
  // Um arquivo pequeno por deputado, lido pelo site quando o perfil é aberto.
  const porDep = new Map();
  for (const r of itens) { const l = porDep.get(r.r) || []; l.push(r); porDep.set(r.r, l); }
  fs.rmSync(PASTA, { recursive: true, force: true }); fs.mkdirSync(PASTA, { recursive: true });
  for (const [k, l] of porDep) fs.writeFileSync(path.join(PASTA, k + '.json'), JSON.stringify({ gerado, fonte, itens: l }));
  return itens.length;
}

async function principal() {
  let antes = null; try { antes = JSON.parse(fs.readFileSync(ARQ, 'utf8')); } catch (e) {}
  const completo = process.env.COMPLETO === 'sim' || !antes;
  const porId = new Map();
  if (!completo) for (const r of antes.itens || []) { const l = porId.get(r.i) || []; l.push(r); porId.set(r.i, l); }
  const ini = completo ? INICIO : diaMais(antes.ate || HOJE, -3);
  log(`Relatorias da Câmara, ${completo ? 'carga completa' : 'atualização'} desde ${ini}`);

  // Janelas mensais para listar as proposições.
  const props = new Map();
  for (let a = ini; a <= HOJE;) {
    const fimMes = new Date(Date.UTC(+a.slice(0, 4), +a.slice(5, 7), 0)).toISOString().slice(0, 10);
    const b = fimMes < HOJE ? fimMes : HOJE;
    const achadas = await listar(a, b);
    for (const [id, p] of achadas) props.set(id, p);
    log(`  ${a} a ${b}: ${achadas.size} proposições (total ${props.size})`);
    a = diaMais(b, 1);
  }

  const lista = [...props.values()];
  let lidas = 0;
  await emParalelo(lista, async p => {
    const j = await pegar(`${API}/proposicoes/${p.id}/tramitacoes`).catch(() => null);
    if (!j) return;
    porId.set(p.id, relatoriasDe(p, j.dados || []));
    if (++lidas % 5000 === 0) gravar(porId, HOJE); // ponto de salvamento na carga longa
  }, PARALELO);

  if (completo && lidas < lista.length * 0.9) { log(`Leitura incompleta (${lidas} de ${lista.length}); arquivo anterior mantido.`); if (antes) return; }
  const n = gravar(porId, HOJE);
  log(`Concluído: ${lidas} proposições lidas, ${n} relatorias, ${falhas} falhas de rede.`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  principal().catch(e => { console.error(e); process.exit(1); });
}
