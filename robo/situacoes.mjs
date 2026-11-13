// Situação atual de cada proposição acompanhada (em tramitação, aprovada numa Casa, virou lei ou arquivada).
//
// Câmara: arquivos anuais de proposições dos Dados Abertos, que trazem o último status de cada uma.
// Quando uma proposição não está nesses arquivos, a ficha dela é lida pela API.
// Senado: lista de processos por período de apresentação, com a situação atual.
//
// Grava dados/situacoes.json. Não usa IA.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const DADOS = process.env.DADOS || path.join(RAIZ, 'dados');
const API_CAMARA = 'https://dadosabertos.camara.leg.br/api/v2';
const ARQ_CAMARA = a => `https://dadosabertos.camara.leg.br/arquivos/proposicoes/json/proposicoes-${a}.json`;
const API_SENADO = 'https://legis.senado.leg.br/dadosabertos/processo';
const TIPOS = ['PL', 'PLP', 'PEC', 'PDL', 'MPV'];
const ANOS = [2023, 2024, 2025, 2026].filter(a => a <= new Date().getUTCFullYear());
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
const espera = ms => new Promise(r => setTimeout(r, ms));

async function pegar(url, tentativas = 4, tempo = 60000) {
  for (let t = 1; ; t++) {
    try {
      const r = await fetch(url, { headers: { accept: 'application/json', 'user-agent': 'exterminadores-do-futuro (observatório; contato@exterminadores.com.br)' }, signal: AbortSignal.timeout(tempo) });
      if (r.status === 404) return null;
      if (r.ok) return await r.json();
      if (t >= tentativas) throw new Error('http ' + r.status);
    } catch (e) { if (t >= tentativas) throw e; }
    await espera(2000 * t * t);
  }
}

// Categoria a partir do texto da situação.
export function categoria(desc) {
  const d = String(desc || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  if (!d.trim()) return '';
  if (/norma juridica|transformad[ao] em (lei|norma)|lei n/.test(d)) return 'lei';
  if (/arquivad|retirad|prejudicad|rejeitad|devolvid|perda de eficacia|vigencia encerrada|tramitacao encerrada|nao conhecid|inadmitid/.test(d)) return 'arquivada';
  if (/remetid[ao] a|aguardando apreciacao pelo senado|aguardando apreciacao pela camara|aguardando sancao|enviad[ao] a sancao|remessa a sancao|a sancao|aprovad|aguardando promulgacao|promulgad|vetad|veto|transformad[ao] no|recebid[ao] do senado|retorno a camara|enviad[ao] ao senado|encaminhad[ao] ao senado|camara revisora|autografos|redacao final/.test(d)) return 'aprovada';
  return 'tramitando';
}

const achar = (o, chave) => {
  if (!o || typeof o !== 'object') return undefined;
  if (chave in o) return o[chave];
  for (const v of Object.values(o)) { const r = achar(v, chave); if (r !== undefined) return r; }
  return undefined;
};

async function situacoesCamara(itens) {
  const porId = new Map(itens.filter(it => it.k.includes('C') && it.i).map(it => [String(it.i), it.c]));
  const out = {};
  for (const a of ANOS) {
    try {
      const j = await pegar(ARQ_CAMARA(a), 3, 300000);
      const lista = (j && (j.dados || j)) || [];
      if (lista[0]) log(`  arquivo ${a}: ${lista.length} proposições; campos do status: ${Object.keys(lista[0].ultimoStatus || {}).join(', ') || Object.keys(lista[0]).filter(k => /status/i.test(k)).join(', ')}`);
      for (const p of lista) {
        const c = porId.get(String(p.id)); if (!c) continue;
        const st = p.ultimoStatus || {};
        const desc = st.descricaoSituacao || p.ultimoStatus_descricaoSituacao || '';
        const tram = st.descricaoTramitacao || p.ultimoStatus_descricaoTramitacao || '';
        out[c] = { s: desc || tram, d: String(st.dataHora || p.ultimoStatus_dataHora || '').slice(0, 10) };
      }
    } catch (e) { log(`  arquivo ${a} indisponível (${e.message}); as fichas serão lidas pela API`); }
  }
  // O que faltou (proposições de anos fora dos arquivos ou arquivo indisponível): ficha a ficha, em paralelo.
  const faltam = [...porId.entries()].filter(([, c]) => !out[c] || !out[c].s);
  log(`  Câmara: ${Object.keys(out).length} pelos arquivos, ${faltam.length} pela API`);
  let k = 0, feitas = 0;
  await Promise.all(Array.from({ length: 8 }, async () => {
    while (k < faltam.length) {
      const [id, c] = faltam[k++];
      try {
        const j = await pegar(`${API_CAMARA}/proposicoes/${id}`);
        const st = j && j.dados && j.dados.statusProposicao;
        if (st) out[c] = { s: st.descricaoSituacao || st.descricaoTramitacao || '', d: String(st.dataHora || '').slice(0, 10) };
      } catch (e) {}
      if (++feitas % 2000 === 0) log(`    ${feitas} de ${faltam.length}`);
    }
  }));
  return out;
}

async function situacoesSenado(itens) {
  const queremos = new Set(itens.filter(it => it.k.includes('S')).map(it => it.c));
  const out = {};
  const hoje = new Date().toISOString().slice(0, 10);
  const janelas = [];
  for (let a = `${ANOS[0]}-01-01`; a <= hoje;) {
    const fim = new Date(Date.UTC(+a.slice(0, 4), +a.slice(5, 7), 0)).toISOString().slice(0, 10);
    janelas.push([a, fim < hoje ? fim : hoje]);
    a = new Date(Date.parse(fim) + 86400000).toISOString().slice(0, 10);
  }
  let falhas = 0;
  for (const [ini, fim] of janelas) {
    for (const tipo of TIPOS) {
      const url = `${API_SENADO}?sigla=${tipo}&dataInicioApresentacao=${ini}&dataFimApresentacao=${fim}`;
      let lista;
      try { const j = await pegar(url); lista = Array.isArray(j) ? j : (achar(j, 'processo') || achar(j, 'Processo') || []); if (!Array.isArray(lista)) lista = [lista]; }
      catch (e) { falhas++; continue; }
      for (const d of lista) {
        const m = /^(\S+)\s+(\d+)\/(\d{4})/.exec(String(achar(d, 'identificacao') || ''));
        if (!m) continue;
        const c = `${m[1]} ${parseInt(m[2], 10)}/${m[3]}`;
        if (!queremos.has(c)) continue;
        out[c] = { s: String(achar(d, 'situacaoAtual') || ''), d: String(achar(d, 'dataUltimaAtualizacao') || '').slice(0, 10) };
      }
    }
  }
  log(`  Senado: ${Object.keys(out).length} de ${queremos.size}, ${falhas} consultas com falha`);
  return out;
}

async function principal() {
  const itens = [];
  for (const a of ANOS) { try { itens.push(...JSON.parse(fs.readFileSync(path.join(DADOS, `proposicoes-${a}.json`), 'utf8')).itens); } catch (e) {} }
  log(`Situações de ${itens.length} proposições`);
  const cam = await situacoesCamara(itens);
  const sen = await situacoesSenado(itens);
  // Proposição que passou pelas duas Casas: vale a situação mais adiantada.
  const LETRA = { '': '', tramitando: 't', aprovada: 'p', lei: 'l', arquivada: 'a' };
  const ordem = { '': 0, tramitando: 1, arquivada: 2, aprovada: 3, lei: 4 };
  const descs = [], idx = new Map(), saida = {};
  const cont = { tramitando: 0, aprovada: 0, lei: 0, arquivada: 0, '': 0 };
  for (const it of itens) {
    const cands = [cam[it.c], sen[it.c]].filter(Boolean).map(x => ({ ...x, cat: categoria(x.s) }));
    if (!cands.length) { cont['']++; continue; }
    cands.sort((a, b) => ordem[b.cat] - ordem[a.cat]);
    const x = cands[0];
    if (!idx.has(x.s)) { idx.set(x.s, descs.length); descs.push(x.s); }
    saida[it.c] = [LETRA[x.cat], idx.get(x.s), x.d];
    cont[x.cat]++;
  }
  const lidas = Object.keys(saida).length;
  if (lidas < itens.length * 0.8) { log(`Leitura incompleta (${lidas} de ${itens.length}); arquivo anterior mantido.`); process.exitCode = 1; return; }
  fs.writeFileSync(path.join(DADOS, 'situacoes.json'), JSON.stringify({ gerado: new Date().toISOString(),
    legenda: { t: 'em tramitação', p: 'aprovada em ao menos uma Casa', l: 'virou lei', a: 'arquivada, retirada ou prejudicada' },
    descricoes: descs, itens: saida }));
  log(`Concluído: ${lidas} situações. ${JSON.stringify(cont)}`);
  // As situações mais comuns de cada categoria, para conferir a regra.
  const freq = new Map();
  for (const v of Object.values(saida)) { const k2 = v[0] + ' | ' + descs[v[1]]; freq.set(k2, (freq.get(k2) || 0) + 1); }
  for (const [k2, n] of [...freq.entries()].sort((a, b) => b[1] - a[1]).slice(0, 60)) log(`  ${n}\t${k2}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  principal().catch(e => { console.error(e); process.exit(1); });
}
