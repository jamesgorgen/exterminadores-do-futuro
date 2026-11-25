// Dados do governo federal que não estão na coleta principal, para a seção Governo do balanço.
//
// 1. Medidas provisórias editadas desde 2023 (API da Câmara, onde a MP começa a tramitar no Congresso) e a situação
//    de cada uma: virou lei, perdeu a eficácia (caducou), foi rejeitada, aprovada e em sanção, ou ainda em vigor.
// 2. Orientação do líder do governo nas votações nominais do plenário do Senado (a da Câmara já vem com as
//    votações). O Senado publica as orientações por sequencial da votação; a lista de votações traz o sequencial e
//    o código usado na base do observatório (S:<código>).
//
// 3. Líderes do governo na Câmara e no Senado em cada período, para usar o voto do líder nas votações em que o
//    governo não registrou orientação. Câmara: /legislaturas/57/lideres (bancada "Governo na CD"). Câmara e Senado:
//    composição atual das lideranças no serviço do Senado (/composicao/lideranca, tipo de unidade "G"). O serviço só
//    traz quem está no cargo hoje; o líder anterior no Senado (Jaques Wagner, de fevereiro de 2023 a 24/6/2026, quando
//    deixou o cargo) fica registrado abaixo, a partir do noticiário da troca (Agência Senado, Congresso em Foco).
//
// Grava dados/governo-fontes.json. Não usa IA.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const DADOS = process.env.DADOS || path.join(RAIZ, 'dados');
const CAM = 'https://dadosabertos.camara.leg.br/api/v2';
const SEN = 'https://legis.senado.leg.br/dadosabertos';
const INICIO = '2023-02-01';
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
const espera = ms => new Promise(r => setTimeout(r, ms));
const norm = s => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

async function pegar(url, tentativas = 4) {
  for (let t = 1; ; t++) {
    try {
      const r = await fetch(url, { headers: { accept: 'application/json', 'user-agent': 'exterminadores-do-futuro (observatório; contato@exterminadores.com.br)' }, signal: AbortSignal.timeout(60000) });
      if (r.status === 404) return null;
      if (r.ok) return await r.json();
      if (t >= tentativas) throw new Error('http ' + r.status);
    } catch (e) { if (t >= tentativas) throw e; }
    await espera(1500 * t * t);
  }
}

// Situação de uma MP a partir da descrição e do despacho do último status.
export function situacaoMp(desc, despacho) {
  const d = norm(desc), p = norm(despacho);
  if (/norma juridica|transformad[ao] em lei/.test(d)) return 'lei';
  if (/perda de eficacia|perdeu a eficacia|vigencia encerrada|eficacia encerrada|caducad|termino (de|do) prazo para edicao de decreto legislativo/.test(d + ' ' + p)) return 'caducou';
  if (/rejeitad|nao conhecid|inadmitid/.test(d)) return 'rejeitada';
  if (/aguardando sancao|remetid[ao] a sancao|enviad[ao] a sancao|aguardando promulgacao|vetad|aguardando apreciacao pelo senado/.test(d)) return 'aprovada';
  if (/arquivad|prejudicad|devolvid|revogad/.test(d)) return 'caducou';
  return 'vigor';
}

async function medidasProvisorias() {
  const lista = [];
  for (let pg = 1; pg < 20; pg++) {
    const j = await pegar(`${CAM}/proposicoes?siglaTipo=MPV&dataApresentacaoInicio=2023-01-01&itens=100&pagina=${pg}&ordem=ASC&ordenarPor=id`);
    const d = (j && j.dados) || []; lista.push(...d);
    if (d.length < 100) break;
  }
  const out = []; let k = 0;
  await Promise.all(Array.from({ length: 6 }, async () => {
    while (k < lista.length) {
      const p = lista[k++];
      try {
        const s = ((await pegar(`${CAM}/proposicoes/${p.id}`)) || {}).dados.statusProposicao || {};
        out.push({ c: `MPV ${p.numero}/${p.ano}`, i: p.id, d: String(p.dataApresentacao || '').slice(0, 10), e: String(p.ementa || '').split('NOVA EMENTA')[0].trim().slice(0, 300),
          s: situacaoMp(s.descricaoSituacao, s.despacho), sd: s.descricaoSituacao || '', dt: String(s.dataHora || '').slice(0, 10) });
      } catch (e) { log('  MP sem situação:', p.numero, p.ano, e.message); }
    }
  }));
  out.sort((a, b) => a.d.localeCompare(b.d));
  log(`  ${out.length} medidas provisórias de ${lista.length}`);
  return out;
}

function janelas(ini, fim) {
  const r = [];
  for (let a = ini; a <= fim;) {
    const f = new Date(Date.UTC(+a.slice(0, 4), +a.slice(5, 7), 0)).toISOString().slice(0, 10);
    r.push([a, f < fim ? f : fim]); a = new Date(Date.parse(f) + 864e5).toISOString().slice(0, 10);
  }
  return r;
}

async function orientacaoSenado() {
  const hoje = new Date().toISOString().slice(0, 10);
  const porSeq = new Map(), codDeSeq = new Map(); let falhas = 0;
  for (const [a, b] of janelas(INICIO, hoje)) {
    try {
      const o = await pegar(`${SEN}/plenario/votacao/orientacaoBancada/${a.replace(/-/g, '')}/${b.replace(/-/g, '')}`);
      for (const v of (o && o.votacoes) || []) {
        const g = (v.orientacoesLideranca || []).find(x => /^governo$/i.test(String(x.partido || '').trim()));
        const t = norm(g && g.voto);
        const pos = t.startsWith('sim') ? 'S' : t.startsWith('nao') ? 'N' : t.startsWith('libera') || t.startsWith('livre') ? 'L' : t.startsWith('obstru') ? 'O' : '';
        if (pos) porSeq.set(String(v.sequencialVotacao), pos);
      }
      const vs = await pegar(`${SEN}/votacao?dataInicio=${a}&dataFim=${b}`);
      for (const v of Array.isArray(vs) ? vs : []) if (v.sequencialVotacao && v.codigoSessaoVotacao) codDeSeq.set(String(v.sequencialVotacao), String(v.codigoSessaoVotacao));
    } catch (e) { falhas++; }
  }
  const out = {};
  for (const [seq, pos] of porSeq) { const c = codDeSeq.get(seq); if (c) out['S:' + c] = pos; }
  log(`  Senado: orientação do governo em ${Object.keys(out).length} votações (${porSeq.size} lidas, ${falhas} meses com falha)`);
  return out;
}

const LIDERES_ANTERIORES = {
  S: [{ c: 'S581', n: 'Jaques Wagner', ini: '2023-02-01', fim: '2026-06-24', fonte: 'Noticiário da troca na liderança (25/6/2026): Wagner deixou o cargo em 24/6/2026' }]
};
async function lideres() {
  const out = { C: [], S: [] };
  const l = ((await pegar(`${CAM}/legislaturas/57/lideres`)) || {}).dados || [];
  for (const x of l) if (x.titulo === 'Líder' && /governo/i.test((x.bancada && (x.bancada.tipo || x.bancada.nome)) || ''))
    out.C.push({ c: 'C' + x.parlamentar.id, n: x.parlamentar.nome, ini: String(x.dataInicio || '').slice(0, 10), fim: String(x.dataFim || '').slice(0, 10), fonte: 'API da Câmara, líderes da 57ª legislatura' });
  const comp = (await pegar(`${SEN}/composicao/lideranca`)) || [];
  for (const x of Array.isArray(comp) ? comp : []) {
    if (x.siglaTipoUnidadeLideranca !== 'G' || x.siglaTipoLideranca !== 'L') continue;
    const ini = String(x.dataDesignacao || '').slice(0, 10);
    if (x.casa === 'CD' && x.codigoDeputado && !out.C.some(y => y.c === 'C' + x.codigoDeputado && y.ini === ini)) out.C.push({ c: 'C' + x.codigoDeputado, n: x.nomeParlamentar, ini, fim: '', fonte: 'Serviço de lideranças do Senado (composição atual)' });
    if (x.casa === 'SF') out.S.push({ c: 'S' + x.codigoParlamentar, n: x.nomeParlamentar, ini, fim: '', fonte: 'Serviço de lideranças do Senado (composição atual)' });
  }
  out.S.push(...LIDERES_ANTERIORES.S);
  for (const k of ['C', 'S']) out[k].sort((a, b) => a.ini.localeCompare(b.ini));
  // Um líder sem data de fim termina na véspera do início do seguinte.
  for (const k of ['C', 'S']) out[k].forEach((x, i, a) => { if (!x.fim && a[i + 1]) x.fim = new Date(Date.parse(a[i + 1].ini) - 864e5).toISOString().slice(0, 10); });
  log(`  líderes do governo: Câmara ${out.C.map(x => `${x.n} (${x.ini} a ${x.fim || 'hoje'})`).join(', ')}; Senado ${out.S.map(x => `${x.n} (${x.ini} a ${x.fim || 'hoje'})`).join(', ')}`);
  return out;
}

async function principal() {
  log('Governo: medidas provisórias e orientação no Senado');
  const anterior = (() => { try { return JSON.parse(fs.readFileSync(path.join(DADOS, 'governo-fontes.json'), 'utf8')); } catch (e) { return {}; } })();
  let mpv = [], oriS = {}, lid = anterior.lideres || { C: [], S: [] };
  try { const l = await lideres(); if (l.C.length && l.S.length) lid = l; } catch (e) { log('  líderes indisponíveis:', e.message); }
  try { mpv = await medidasProvisorias(); } catch (e) { log('  MPs indisponíveis:', e.message); }
  try { oriS = await orientacaoSenado(); } catch (e) { log('  orientações do Senado indisponíveis:', e.message); }
  // Leitura falha ou muito menor que a anterior: mantém a parte anterior.
  if (anterior.mpv && mpv.length < anterior.mpv.length * 0.9) { log('  MPs: leitura incompleta, mantida a anterior'); mpv = anterior.mpv; }
  if (anterior.orientacaoSenado && Object.keys(oriS).length < Object.keys(anterior.orientacaoSenado).length * 0.9) { log('  Senado: leitura incompleta, mantida a anterior'); oriS = anterior.orientacaoSenado; }
  fs.writeFileSync(path.join(DADOS, 'governo-fontes.json'), JSON.stringify({ gerado: new Date().toISOString(), mpv, orientacaoSenado: oriS, lideres: lid }));
  log('Concluído');
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) principal().catch(e => { console.error(e); process.exit(1); });
