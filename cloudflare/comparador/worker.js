// Comparador de textos: API pública usada pela página comparador.html do site.
// Guarda pedidos e PDFs enviados no bucket privado do R2 (prefixo comparador/); quem processa é o robô
// robo/comparador/fila.py (workflow "Comparador"). A busca de proposições é feita no navegador, direto nas APIs da Câmara e do Senado.
//
// GET  /api/lista                 comparações prontas (comparador/indice.json)
// GET  /api/comparacao?id=…       uma comparação pronta
// GET  /api/pedido?id=…           situação de um pedido (fila, processando, pronta, erro)
// GET  /api/cota                  se esta conexão ainda pode pedir uma comparação nova neste mês
// PUT  /api/envio?sha=…           envio de um PDF (corpo = o arquivo); devolve a referência arquivo:<sha256>
// POST /api/comparar              cria o pedido {a:{ref,…}, b:{ref,…}, titulo, proposicao}
//
// Limite: uma comparação nova por mês por IP (o IP é guardado só como hash com sal). Abrir comparações prontas
// e pedir uma comparação que já existe não contam. Há também um teto mensal geral (LIMITE_GLOBAL_MES).

const P = 'comparador/';
const ORIGENS = ['https://exterminadores.com.br', 'https://www.exterminadores.com.br', 'https://jamesgorgen.github.io'];
const MAX_PDF = 15 * 1024 * 1024;

function cors(req) {
  const o = req.headers.get('origin') || '';
  return {
    'access-control-allow-origin': ORIGENS.includes(o) ? o : '*',
    'access-control-allow-methods': 'GET, POST, PUT, OPTIONS',
    'access-control-allow-headers': 'content-type',
    'access-control-max-age': '86400', 'vary': 'origin',
  };
}
const json = (req, obj, status = 200, cache = 'no-store') => new Response(JSON.stringify(obj), {
  status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': cache, 'x-robots-tag': 'noindex', ...cors(req) },
});
const erro = (req, msg, status = 400, extra = {}) => json(req, { erro: msg, ...extra }, status);

const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
const sha256 = async s => hex(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)));
const limpa = (s, n) => String(s == null ? '' : s).replace(/[\u0000-\u001f<>]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, n);

// mês no horário de Brasília (UTC-3)
function mes() { const d = new Date(Date.now() - 3 * 3600e3); return d.toISOString().slice(0, 7); }
function proximoMes() { const [a, m] = mes().split('-').map(Number); return m === 12 ? `${a + 1}-01-01` : `${a}-${String(m + 1).padStart(2, '0')}-01`; }

async function sal(env) {
  const o = await env.R2.get(P + 'config/sal');
  if (o) return o.text();
  const s = hex(crypto.getRandomValues(new Uint8Array(32)));
  await env.R2.put(P + 'config/sal', s);
  return s;
}
async function chaveCota(req, env) {
  const ip = req.headers.get('cf-connecting-ip') || 'sem-ip';
  return `cota/${mes()}/${(await sha256((await sal(env)) + '|' + ip)).slice(0, 32)}`;
}
async function cotaLivre(req, env) {
  const k = await chaveCota(req, env);
  const usada = await env.R2.head(P + k);
  return { k, livre: !usada };
}
async function totalMes(env) {
  let n = 0, cursor;
  do {
    const r = await env.R2.list({ prefix: `${P}cota/${mes()}/`, cursor, limit: 1000 });
    n += r.objects.length; cursor = r.truncated ? r.cursor : undefined;
  } while (cursor);
  return n;
}

const REF = /^(camara:\d{1,9}|senado:\d{1,12}:[0-9a-f-]{36}|arquivo:[0-9a-f]{64})$/;
const ID = /^[0-9a-f]{16}$/;

function lado(x) {
  if (!x || typeof x !== 'object' || !REF.test(String(x.ref || ''))) return null;
  return { ref: String(x.ref), nome: limpa(x.nome, 120), autor: limpa(x.autor, 120), data: limpa(x.data, 10) };
}

async function comparar(req, env) {
  let corpo;
  try { corpo = await req.json(); } catch { return erro(req, 'Pedido inválido.'); }
  const a = lado(corpo.a), b = lado(corpo.b);
  if (!a || !b) return erro(req, 'Escolha duas versões válidas.');
  if (a.ref === b.ref) return erro(req, 'Escolha duas versões diferentes.');
  for (const x of [a, b]) {
    if (x.ref.startsWith('arquivo:') && !(await env.R2.head(`${P}envios/${x.ref.slice(8)}.pdf`))) return erro(req, 'Um dos PDFs não chegou. Envie de novo.');
  }
  const id = (await sha256(`${a.ref}|${b.ref}`)).slice(0, 16);
  // já existe? não conta para o limite
  if (await env.R2.head(`${P}resultados/${id}.json`)) return json(req, { id, estado: 'pronta', existente: true });
  const antigo = await env.R2.get(`${P}pedidos/${id}.json`);
  if (antigo) {
    const p = await antigo.json();
    if (p.estado === 'fila' || p.estado === 'processando') return json(req, { id, estado: p.estado, existente: true });
    if (p.estado === 'removida') return erro(req, 'Esta comparação foi retirada da plataforma pela equipe.', 410);
  }
  const { k, livre } = await cotaLivre(req, env);
  if (!livre) return erro(req, 'Você já usou a sua comparação gratuita deste mês. As comparações prontas continuam abertas.', 429, { renova: proximoMes() });
  if ((await totalMes(env)) >= Number(env.LIMITE_GLOBAL_MES || 300)) return erro(req, 'O limite de comparações novas deste mês foi atingido. Tente no mês que vem.', 429, { renova: proximoMes() });
  const agora = new Date().toISOString().slice(0, 19) + '+00:00';
  await env.R2.put(P + k, JSON.stringify({ id, criado: agora }));
  const pedido = { id, estado: 'fila', criado: agora, atualizado: agora, origem: 'site', a, b, titulo: limpa(corpo.titulo, 140), proposicao: limpa(corpo.proposicao, 60), tentativas: 0, cota: k };
  await env.R2.put(`${P}pedidos/${id}.json`, JSON.stringify(pedido), { httpMetadata: { contentType: 'application/json' } });
  return json(req, { id, estado: 'fila' }, 201);
}

async function envio(req, env, url) {
  const sha = url.searchParams.get('sha') || '';
  if (!/^[0-9a-f]{64}$/.test(sha)) return erro(req, 'Envio inválido.');
  const tam = Number(req.headers.get('content-length') || 0);
  if (!tam) return erro(req, 'Arquivo vazio.');
  if (tam > MAX_PDF) return erro(req, 'O PDF passa de 15 MB.', 413);
  const chave = `${P}envios/${sha}.pdf`;
  if (await env.R2.head(chave)) return json(req, { ref: 'arquivo:' + sha });
  const { livre } = await cotaLivre(req, env);
  if (!livre) return erro(req, 'Você já usou a sua comparação gratuita deste mês.', 429, { renova: proximoMes() });
  await env.R2.put(chave, req.body, { httpMetadata: { contentType: 'application/pdf' } });
  return json(req, { ref: 'arquivo:' + sha }, 201);
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors(req) });
    const o = req.headers.get('origin');
    if ((req.method === 'POST' || req.method === 'PUT') && o && !ORIGENS.includes(o)) return erro(req, 'Origem não autorizada.', 403);
    try {
      if (req.method === 'GET' && url.pathname === '/api/lista') {
        const r = await env.R2.get(P + 'indice.json');
        return new Response(r ? r.body : '{"itens":[]}', { headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'public, max-age=60', ...cors(req) } });
      }
      if (req.method === 'GET' && url.pathname === '/api/comparacao') {
        const id = url.searchParams.get('id') || '';
        if (!ID.test(id)) return erro(req, 'Identificador inválido.');
        const r = await env.R2.get(`${P}resultados/${id}.json`);
        if (!r) return erro(req, 'Comparação não encontrada.', 404);
        return new Response(r.body, { headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'public, max-age=300', ...cors(req) } });
      }
      if (req.method === 'GET' && url.pathname === '/api/pedido') {
        const id = url.searchParams.get('id') || '';
        if (!ID.test(id)) return erro(req, 'Identificador inválido.');
        const r = await env.R2.get(`${P}pedidos/${id}.json`);
        if (!r) return erro(req, 'Pedido não encontrado.', 404);
        const p = await r.json();
        return json(req, { id, estado: p.estado, erro: p.erro || null, criado: p.criado, atualizado: p.atualizado, titulo: p.titulo || p.proposicao || '' });
      }
      if (req.method === 'GET' && url.pathname === '/api/cota') {
        const { livre } = await cotaLivre(req, env);
        return json(req, { disponivel: livre, renova: proximoMes() });
      }
      if (req.method === 'PUT' && url.pathname === '/api/envio') return envio(req, env, url);
      if (req.method === 'POST' && url.pathname === '/api/comparar') return comparar(req, env);
      return erro(req, 'Não encontrado.', 404);
    } catch (e) {
      return erro(req, 'Erro interno. Tente de novo em instantes.', 500);
    }
  },
};
